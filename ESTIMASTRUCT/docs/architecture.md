# Architecture — EstimaStruct

> **Estado:** production local · **BD canónica = PostgreSQL `estimastruct` (127.0.0.1:5432), ver ADR-014 (2026-08-15) que revierte ADR-013** · la SQLite versionada `estimacion.db` conserva hoy los precios v1.3 reales; su reconciliación hacia Postgres está *diseñada, no ejecutada* (goal-21070/21071, gateada a OK David) · migración SaaS declarada (CASE-SAAS-001).
> **Regla:** este archivo manda. CHANGELOG = historial temporal.

---

## 1. Overview

EstimaStruct es una app web local para elaborar presupuestos de construcción (Honduras, HNL) sobre un catálogo de fichas CSI MasterFormat con costos históricos (MO, Materiales, Sub-matrices OPUS) y overhead configurable. Integra diseño estructural (concreto CHOC-08 / acero LRFD), takeoff cuantitativo desde Revit/ETABS y export a PDF, Excel y Portal Supabase. Reemplaza hojas Excel manuales por un pipeline reproducible ficha → partida → capítulo → presupuesto con trazabilidad de fórmulas y auditoría de precios.

---

## 2. C4 Model

### 2.1 System Context

```
                    ┌────────────────────┐
                    │  Director / Cliente│
                    └──────────┬─────────┘
                               │ HTTP :5000
                    ┌──────────▼─────────┐
                    │    EstimaStruct    │
                    │   (localhost app)  │
                    └──┬───────┬─────┬───┘
                       │       │     │
              ┌────────▼─┐ ┌───▼──┐ ┌▼────────────┐
              │ Revit MCP │ │ ETABS│ │ Supabase    │
              │ HTTP :8001│ │ CSV  │ │ Portal      │
              │→ NamedPipe│ │      │ │             │
              │ →Revit    │ │      │ │             │
              └───────────┘ └──────┘ └─────────────┘
```

### 2.2 Container Diagram

```
Browser (Chromium)
      │  HTML/JS (KaTeX, Babylon viewer)
      ▼
[Flask UI :5000]                        [FastAPI Backend :8002]
  ESTIMASTRUCT/app.py    ──proxy──►     backend/main.py
  templates/ + frontend/                24+ routers
                                          │
                     ┌────────────────────┼──────────────────┐
                     ▼                    ▼                  ▼
              [Postgres :5432]     [Template2_Updated]  [revit-mcp-stdio HTTP :8001
              estimastruct DB      fichas_v1.3.json      → NamedPipe \\.\pipe\revit-mcp
                                                          → pyRevit / Revit] · ETABS
                     ▲
                     │ export ZIP / import ZIP
              [SQLite legacy]
              C:\EstimaStruct\data\estimacion.db (compat, no primario)
```

### 2.3 Component Diagram — Backend

```
backend/
├── main.py               FastAPI app, lifespan, CORS, router mount
├── db.py + models.py     SQLAlchemy 2.0 ORM + declarative Base
├── config.py             CONFIG dataclass (env-overridable paths)
├── services/
│   ├── pricing.py        FUENTE ÚNICA calc_base / precio_unitario / rebucket_insumos
│   ├── pricing_memoria.py    narra pricing.py (memoria_pricing) — Auditoría de Fórmulas, 2026-07-27
│   ├── calculos_memoria.py   narra routers/calculos.py (memoria_calculos_presupuesto), expone bug doble sobrecosto
│   ├── mamposteria_memoria.py    MOTOR takeoff_mamposteria + memoria (TMS 402-16) — reemplazó 2 constantes mágicas, 2026-07-27
│   ├── export_pdf_memoria.py     MOTOR prorrateo_banco + memoria — factor bancario, residuo, margen implícito (2026-07-31) ⚠ pend. aprobación Director
│   ├── partidas_memoria.py       MOTOR takeoff_cantidad + memoria — ceil + _safe_factor (0→1, negativos), advertencias[] (2026-07-31)
│   ├── cronograma_memoria.py     narra cronograma.py — cascada de 4 fuentes + offsets de fase (2026-07-31)
│   ├── perfiles_memoria.py       narra perfiles_acero.props_seccion — expone `fuente` tabla/derivada/hss (2026-07-31)
│   ├── unidades_memoria.py       narra seccion_ficha.factores_unidad — fallback silencioso a kgf (2026-07-31)
│   ├── predimensionar_memoria.py narra calculo_estructural.predimensionar — heurística ≠ ACI 318 (2026-07-31)
│   ├── acero_ficha_memoria.py    narra acero_ficha.agregar_por_ficha — regla dual⇒COLUMNA, envolvente D/C (2026-07-31)
│   ├── partidas_bridge.py
│   ├── etabs_parse.py
│   └── mcp_http.py       cliente HTTP contra Revit MCP :8100
├── routers/              (endpoints — 24 archivos)
│   ├── presupuestos.py   CRUD obras + from-template + duplicar
│   ├── partidas.py       CRUD partidas + cantidad/revit-q/factores
│   ├── insumos.py        CRUD insumos → recalc bucketing 3-vías
│   ├── recursos.py       catálogo maestro precios
│   ├── calculos.py       recalcular presupuesto + reporte
│   ├── bases.py          BaseDatosOpus xlsx bridge
│   ├── diseno_estructural.py + acero_diseno.py + sismo.py + conexion_acero.py + miembro_acero.py
│   ├── cronograma.py     Gantt overrides (n_esp, n_ay)
│   ├── export.py + export_pdf.py + preview_pdf.py
│   ├── portal_publish.py POST → Supabase REST
│   ├── revit_mcp.py      inject IronPython, import quantities, keynotes
│   ├── db_backup.py      export/import ZIP (portable Postgres↔SQLite)
│   ├── auditoria_formulas.py  Auditoría de Fórmulas — 14 dominios narrados (2026-07-27 pricing/calculos/mampostería · 2026-07-31 los 7 ciegos restantes)
│   └── memory.py / diagnostics.py / updater.py / scripts.py
└── calculo_*.py          motores puros (sísmico CHOC-08, acero LRFD, conexiones §J)
```

---

## 3. Data Model

Todas las PKs son UUID `String(36)`. Money `Numeric(14, 4)`, cuantizado ROUND_HALF_UP en `services/pricing.py`.

### 3.1 Núcleo presupuestal

```
presupuesto (id, nombre, cliente, fecha, moneda, es_template, created_at)
    ├── config_presupuesto (1:1)  sobrecosto%, admin%, utilidad%, imprevistos%, iva%, template_version
    ├── contexto_sismico    (1:1)  CHOC-08: zona, suelo, Rw, hn, w_t, espectro_json
    └── capitulo (1:N, orden)      clave CSI div ("03"), nombre
            └── partida (1:N, orden)
                    ├── clave_csi ("03 31 00.1"), descripcion, unidad, cantidad
                    ├── costo_mo, costo_ma, unitario_matriz  →  costo_base
                    ├── precio_unitario = base × (1 + sobrecosto/100)
                    ├── total = cantidad × precio_unitario
                    ├── revit_q, factor_e, factor_f, color_tipo
                    ├── es_formula, formula_ref, type_mark, omniclass_num, assembly_num
                    └── insumo_partida (1:N)
                            ├── recurso_id → recurso (FK opcional, SET NULL)
                            ├── tipo ∈ {MATERIAL, MANO_OBRA, HERRAMIENTA, EQUIPO, FLETE, SUBCONTRATO, DISEÑO}
                            └── cantidad, costo_unit, total

recurso (id, clave UNIQUE, descripcion, unidad, tipo, precio_unitario, ultima_actualizacion)
```

### 3.2 Diseño estructural (Div 03/05 CSI)

```
diseno_elemento (id, presupuesto_id FK, csi, type_mark, tipo, material_tipo,
                 geometría b/d/bp/t/lx/ly, fc, fy, longitud_m,
                 perfil_acero, acero_grado)
    └── caso_diseno (1:N)  nombre, gobierna, origen(MANUAL|ETABS), combo_etabs
                            mu_tm, vu_t, tu_tm, nu_t, pu_t, mu_xx_tm, mu_yy_tm
                            lu_cm, k_x/y, bd_x/y, cm_x/y
            └── resultado_diseno (1:1)  pb, pmax, as_cm2, av_cm2, at_cm2,
                                        concreto_m3, encofrado_m2, acero_kg, estribos_kg,
                                        acero_estado_gob, acero_phi_rn_gob, acero_dc,
                                        partida_{concreto|acero|encofrado}_id → partida

conexion_acero (id, presupuesto_id FK, csi, tipo_conexion, perfil_viga/columna,
                t_placa, perno_grado/d/n, w_filete, L_soldadura, B/N_placa, A2)
    └── conexion_caso → conexion_resultado (estado_gob, phi_rn_gob, DC, j8_json §J8)

cronograma_override (id, presupuesto_id, partida_id UNIQUE, n_esp, n_ay)
```

Cascades: borrar presupuesto → cascada a config/capitulo/contexto_sismico/diseno_elemento/conexion_acero/cronograma_override. Partidas eliminadas → `SET NULL` en `insumo_partida.recurso_id` y `resultado_diseno.partida_*_id`.

---

## 4. Estimating Flow

Pipeline ficha → partida → presupuesto:

**Paso 1 — Load template.** `POST /presupuestos/from-template` con `template_version`. `_load_fichas_from_json()` lee `development/Template2_Updated/{v1.0|v1.1|v1.2|v1.3}/fichas/fichas_{v}.live.json` (fallback a `.json`). v1.2 vigente, v1.3 en curso.

**Paso 2 — Instanciar capítulos/partidas.** Cada ficha JSON crea `Partida` con `clave_csi`, `unidad`, `costo_mo`, `costo_ma`, `unitario_matriz` (sub-matriz OPUS) e `InsumoPartida[]`. Capítulos agrupan por `clave_csi[:2]` con etiqueta de `DIVISIONES_CSI` (00 Preliminares … 33 Site Utils).

**Paso 3 — Bucketing 3-vías (fuente única `services/pricing.rebucket_insumos`):**

$$
\text{costo\_mo}=\!\!\sum_{i:\text{MANO\_OBRA}}\!\!i.\text{total},\quad
\text{costo\_ma}=\!\!\sum_{i:\text{MATERIAL}}\!\!i.\text{total},\quad
\text{unitario\_matriz}=\!\!\sum_{i:\notin\{MO,MA\}}\!\!i.\text{total}
$$

Todo `SUBCONTRATO|FLETE|EQUIPO|HERRAMIENTA|DISEÑO` va a `unitario_matriz`. Bug histórico (bucketing 2-vías en `calculos.py`) resuelto 2026-07-03 forzando llamada única a `rebucket_insumos()`.

**Paso 4 — Costo base y PU:**

$$
\text{costo\_base}=\text{MO}+\text{MA}+\text{matriz},\qquad
\text{PU}=\text{base}\times\!\left(1+\tfrac{\text{sobrecosto}\,\%}{100}\right),\qquad
\text{total}=\text{cantidad}\times\text{PU}
$$

Aritmética en `Decimal(str(x))` (evita drift float), cuantizada a 4 dp `ROUND_HALF_UP` en boundaries de escritura (fix 2026-07-12).

**Paso 5 — Quantity takeoff.** Cantidades se ingresan:
- Manual: `PATCH /partidas/{pid}/cantidad`.
- Revit: `POST /revit-mcp/obras/{pid}/import-quantities` bombea `revit_q` bruto; UI aplica `cantidad = revit_q * factor_e * factor_f` (color amarillo = fórmula editable, verde/azul/rosa = origen).
- Diseño estructural: `resultado_diseno.{concreto_m3, acero_kg, encofrado_m2}` linkea a partida via `partida_concreto_id / partida_acero_id / partida_encofrado_id`.

**Paso 6 — Recálculo global.** `POST /presupuestos/{pid}/calcular` recorre partidas, aplica bucketing + PU con `config.sobrecosto`, escribe `costo_base / precio_unitario / total`. Reporte agregado en `GET /presupuestos/{pid}/reporte`.

**Paso 7 — Overhead proyecto.** Config: `administracion + utilidad + imprevistos + otros_factor` sobre subtotal partidas; `iva` (default 15%) al final. Export PDF (`export_pdf.py`) usa membrete ConsuConstruct + `reportlab`.

**Paso 8 — Cronograma.** `CronogramaOverride.n_esp/n_ay` recalcula duración: rendimiento MO diario × cuadrillas paralelas → Gantt (`cronograma.py`).

**Clasificación CSI.** `csi_utils.infer_csi()` valida `NN NN NN[.N]` y mapea a división `DIVISIONES_CSI` en `models.py`. Fichas nuevas via `POST /partidas/nueva-actividad` sin CSI arrancan en capítulo "00".

---

## 5. API Design

FastAPI 0.111 + Pydantic 2.7. Sin autenticación (localhost only). CORS `*`. Prefijos por router.

### 5.1 Endpoints clave

| Verb | Path | Descripción |
|------|------|-------------|
| GET  | `/` `/health` | liveness |
| GET  | `/presupuestos` | lista |
| POST | `/presupuestos` | crear vacío |
| POST | `/presupuestos/from-template` | crear desde `template_version` |
| GET  | `/presupuestos/{pid}` | detalle + capítulos + partidas + insumos (joinedload) |
| PATCH| `/presupuestos/{pid}/sobrecosto` | actualiza y dispara recálculo |
| POST | `/presupuestos/{pid}/duplicar` | clonar completo |
| DELETE| `/presupuestos/{pid}` | cascade |
| POST | `/presupuestos/{pid}/calcular` | recálculo global |
| GET  | `/presupuestos/{pid}/reporte` | subtotales por capítulo + overhead |
| POST | `/presupuestos/{pid}/reasignar-capitulos` | re-agrupa por CSI actual |
| GET  | `/capitulos/{cid}/partidas` | lista ordenada natural CSI |
| POST | `/capitulos/{cid}/partidas` | alta manual |
| PATCH| `/partidas/{pid}/cantidad` \| `/revit-q` \| `/factores` \| `/unidad` \| `/descripcion` \| `/clave-csi` \| `/type-mark` \| `/color` | edición granular |
| POST | `/partidas/nueva-actividad` | ficha ad-hoc |
| GET/POST/PUT/DELETE | `/insumos/*` | CRUD insumo con rebucket auto |
| GET/POST | `/recursos/*` | catálogo maestro |
| GET  | `/diseno/*` `/sismo/*` `/conexion/*` `/miembro-acero/*` | motores estructurales |
| GET/POST | `/auditoria/resumen` \| `/auditoria/pricing/*` \| `/auditoria/calculos/{pid}/memoria` \| `/auditoria/mamposteria/memoria-rapida` | Auditoría de Fórmulas (2026-07-27) — narra pricing.py + calculos.py + mampostería |
| GET/POST | `/auditoria/banco/*` \| `/cantidad/*` \| `/cronograma/*` \| `/perfil/*` \| `/unidades/*` \| `/predimensionar/*` \| `/acero-ficha/*` | Auditoría de Fórmulas tanda 2 (2026-07-31) — los 7 módulos ciegos restantes. Todos read-only; `/banco/{pid}/memoria` NO persiste `valor_banco` (a diferencia del export real) |
| GET  | `/cronograma/{pid}` `/export-cronograma/{pid}` | Gantt |
| GET  | `/export/{pid}` `/export-pdf/{pid}` `/preview-pdf/{pid}` `/export-pdf-html/{pid}` | outputs |
| GET  | `/db/export-zip` \| POST `/db/import-zip` | backup portable |
| POST | `/presupuestos/{pid}/publish-supabase` | portal público |
| GET/POST | `/revit-mcp/*` | 11 endpoints puente Revit MCP |
| GET/POST | `/bases/*` `/updater/*` `/scripts/*` `/memory/*` `/diagnostics/*` | soporte |

### 5.2 Patrón request/response

Body Pydantic (`PartidaIn`, `ConfigIn`, `FromTemplateIn`, `RevitQIn`, `FactoresIn`). Respuestas JSON directas desde ORM (SQLAlchemy → dict manual, no Pydantic response_model). Errores: `HTTPException(400|404|500)` interceptados por `error_handler.register_exception_handlers()`.

### 5.3 Auth

Ninguna. Backend escucha solo en `127.0.0.1:8002`, frontend Flask en `127.0.0.1:5000`. Supabase publish usa `SUPABASE_SECRET_KEY` env (no en git). SaaS futuro (CASE-SAAS-001) planifica JWT/OAuth2 + OWASP Top 10.

---

## 6. Tech Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.x, FastAPI 0.111, Uvicorn 0.29 (standard) |
| ORM | SQLAlchemy 2.0.30, Alembic 1.18 (migraciones) |
| Validación | Pydantic 2.7.1 |
| DB canónica (fuente de verdad) | PostgreSQL 16 `estimastruct` (127.0.0.1:5432), driver `psycopg[binary]>=3.2` — catálogo/precios/recursos (ADR-014, 2026-08-15, revierte ADR-013) |
| DB SQLite versionada (v1.3) | `estimacion.db` — hoy tiene los precios v1.3 reales; reconciliación hacia Postgres *diseñada, no ejecutada* (goal-21070/21071, gate OK David) |
| DB legacy | SQLite `estimastruct.db` (dashboard UI viejo) |
| Frontend UI | Flask 3.1.3 (Jinja2), JS vanilla modular (`core.js`, `app.js`, `tabla-render.js`, `bases-drawer.js`, `calculo-estructural.js`, `db-backup.js`) |
| Fórmulas | KaTeX vendorizado en `frontend/vendor/` |
| 3D Viewer | Babylon.js (`frontend/viewer/`) — GLB desde Revit |
| PDF | ReportLab 4.5.1 + Chromium headless (`export_pdf.py`, `preview_pdf.py`) |
| XLSX | openpyxl 3.1.2, xlrd 2.0.1 (BaseDatosOpus2026.xlsx) |
| Integraciones | Revit MCP HTTP :8100 (IronPython inject), ETABS CSV parse, Supabase REST |
| Runtime local | `D:\LLM\python\python.exe`, Windows 11, PowerShell launcher |

---

## 7. ADRs

**ADR-001: Postgres primario, SQLite compat.** — ✅ **VIGENTE.** (Fue revertida por ADR-013 el 2026-08-15 07:22; ADR-014 el mismo día 08:42 revirtió esa reversión y restauró Postgres como BD canónica de EstimaStruct v1.3+.)
- Decisión: `postgresql+psycopg://postgres@127.0.0.1:5432/estimastruct` primario desde 2026-07-20; SQLite `C:\EstimaStruct\data\estimacion.db` queda como formato de export/import ZIP y para dashboard UI legacy.
- Rationale: concurrencia real (Flask + FastAPI + MCP + scripts), integridad transaccional, migraciones Alembic, path a RDS en SaaS.
- Trade-offs: sysreq extra (servicio pg local), setup credenciales (`D:\Secrets\postgres_credentials.txt`), doble código path (`DB_IS_SQLITE`).

**ADR-002: FastAPI + Flask separados.**
- Decisión: backend puro API (FastAPI :8002); UI Flask :5000 sirve templates y proxya al API.
- Rationale: separar SPA-like JS/JSON API de la capa de plantillas server-rendered; permite reemplazar Flask por Next/Vite sin tocar backend.
- Trade-offs: dos procesos, dos puertos, launcher PowerShell coordina ambos; latencia cross-process irrelevante en localhost.

**ADR-003: `services/pricing.py` como fuente única.**
- Decisión: `calc_base / precio_unitario / rebucket_insumos` viven solo aquí; ningún router recomputa.
- Rationale: bug 2026-07-03 (bucketing duplicado 2-vías vs 3-vías) demostró coste de duplicar lógica.
- Trade-offs: acoplamiento fuerte — todo router de escritura debe importarlo.

**ADR-004: `Decimal(str(x))` + ROUND_HALF_UP a 4 dp.**
- Decisión: money interno como Decimal, cuantización en boundaries de escritura (fix 2026-07-12).
- Rationale: eliminar drift float en re-cálculos sucesivos y alinear con columnas `Numeric(14,4)`.
- Trade-offs: mini-deltas ≤0.0001 vs snapshots pre-fix al recalcular.

**ADR-005: Fichas como JSON versionado en `development/Template2_Updated/`.**
- Decisión: `fichas_{version}.live.json` (edición en curso) con fallback `fichas_{version}.json`; versiones v1.0/v1.1/v1.2/v1.3.
- Rationale: templates auditables por git, comparables entre versiones, no acoplados a la BD viva.
- Trade-offs: bootstrap by-copy (no by-reference); cambios al catálogo maestro no propagan a presupuestos ya instanciados.

**ADR-006: CSI MasterFormat como clave maestra.**
- Decisión: `clave_csi` (`NN NN NN[.N]`) es identificador primario de partida y de `diseno_elemento`.
- Rationale: interoperabilidad con Revit keynotes, OmniClass, Assembly Codes; agrupación por división estándar industria.
- Trade-offs: rigidez de nomenclatura; ficha nueva sin CSI cae en cap "00".

**ADR-007 / ADR-008 / ADR-009: CASE-SAAS-001 (2026-07-22).**
- Decisión: migración a SaaS FastAPI+RDS en AWS ECS/Lambda; AI Tooling Layer con CAG en git (`backend/cag/`), Anthropic API (claude-sonnet-4-6 / claude-opus-4-7), MCP STDIO `estimastruct-mcp`, Skill full-system, MCP STDIO Revit (46+ tools) y ETABS, IronPython scripts `pyrevit/scripts/`.
- Rationale: cliente único → multi-tenant SaaS; agentes IA como interfaz primaria; OWASP Top 10.
- Trade-offs: reescritura de auth, feature-flags multi-tenant, coste API LLM, complejidad MCP STDIO.

**ADR-010: Expansión de scope CASE-SAAS-001 — MCP público, PDF→CAD, PDF→3D (2026-07-27).**
- Decisión: se amplía el scope de CASE-SAAS-001 con tres iniciativas nuevas, y se reordena la ejecución en 9 fases con dependencias duras. Detalle completo en `docs/roadmap_case_saas_001_scope_v2.md`.
  1. **MCP público para LLMs externos** — superficie comercial distinta del `estimastruct-mcp` interno (12 tools STDIO, 2026-07-26). Transporte HTTP/SSE (STDIO no sirve para acceso remoto multi-tenant), auth por API key o OAuth por tenant, rate limiting y billing por uso. Superficie v1 **solo lectura + cálculo dry-run**: las 3 tools de escritura del MCP interno no se exponen, porque el servidor no exige aprobación por sí mismo — ese gate lo pone hoy el cliente MCP local, garantía que no existe con un agente de terceros.
  2. **PDF→CAD→estimación** — extracción de geometría y cantidades desde plano PDF, mapeo a fichas CSI. MVP acotado a **PDF vectorial**; escaneado queda como fase aparte con go/no-go tras medir precisión. Escribe a `partida.revit_q`, reusando el flujo de takeoff existente (no se crea flujo nuevo de presupuesto).
  3. **PDF→3D vía Meshy** — pipeline PDF→imagen→Meshy→GLB al viewer Babylon existente. Requiere secret nuevo `MESHY_API_KEY`.
- Rationale: el MCP público es la única de las tres que convierte capacidad existente en superficie vendible del SaaS. PDF→CAD es el único item del roadmap que abre mercado **no-BIM** (adopción BIM baja en LATAM debilita el diferenciador Revit para el prospecto promedio). PDF→3D es diferenciador de demo/pitch, no capacidad de ingeniería.
- Trade-offs:
  - **Orden no negociable `F0 → F1 → F2 → F4`**: exponer el MCP público antes de auth y multi-tenancy sería publicar una API que devuelve todas las obras de todos los clientes. Hoy hay 0 de 144 endpoints con autenticación y CORS `["*"]`.
  - **F0 (estabilización) bloquea todo**: 0 tests en el repo sobre un motor de dinero que ya tuvo un bug de doble conteo en producción (2026-07-03), y una sola migración Alembic (`606c3f3a7b6b_baseline`) que impide provisionar una RDS limpia.
  - **PDF→3D introduce riesgo de credibilidad**: una malla generada por IA no tiene identidad por elemento ni fidelidad dimensional, a diferencia del pipeline Revit→IFC→GLB (248/248 elementos matcheados). Mezclarlas sin distinción visual permitiría confundir dato BIM real con generación aproximada. Mitigación obligatoria: modo separado, marca visual permanente, y bloqueo funcional — un mesh Meshy no alimenta `revit_q` ni ninguna cantidad.
  - **PDF→CAD introduce riesgo financiero**: una cantidad mal extraída es dinero mal presupuestado con apariencia de automatización confiable. Revisión humana obligatoria antes de aceptar cantidades.
  - **Costo variable nuevo**: Meshy cobra por generación y el LLM por token — ambos requieren cuota/rate-limiting por tenant (F1/F8), no son costo fijo.
  - **Timeline realista**: cadena crítica del SaaS vendible (F0→F1→F2→F4) = 14-19 semanas; scope completo de las 9 fases = 7-9 meses para un operador. Los ítems nuevos (2) y (3) son features desde cero, no gaps a cerrar.
- Correcciones al estado documentado, verificadas contra código 2026-07-27: `§5.1` dice "11 endpoints puente Revit MCP" — hay **17** rutas en `routers/revit_mcp.py`. El import ETABS no es "solo combos de concreto" — son **5 endpoints** (concreto, acero ×2, conexiones, sismo); el gap real es que todos son upload de archivo unidireccional, sin conexión viva ni escritura de vuelta.

**ADR-013: Reversión de ADR-001 — la SQLite versionada en el repo es la BD canónica, no Postgres (2026-08-15).** — ⚠ **REVERTIDA por ADR-014 (2026-08-15 08:42 CST, goal-21069).** Esta decisión quedó SIN EFECTO: la migración de datos nunca se ejecutó (el director estaba apagado), aunque este ADR sí alcanzó a escribirse en el doc. Se conserva el texto abajo por trazabilidad; el canon vigente lo manda ADR-014.
- Decisión (David, 2026-08-15 07:22 CST): **Postgres NO es ni será la base de datos canónica de EstimaStruct.** La fuente de verdad de datos (catálogo de fichas, precios, recursos) es la **SQLite versionada en el repo** — v1.3 actual, próxima v1.4. Se consolida v1.3 como canónica. Esto **revierte ADR-001** (Postgres primario desde 2026-07-20) y el `source_of_truth_estimastruct_20260719` que lo declaraba "BD primaria verificada".
- Contexto que forzó la reversión — split-brain real (ver `memory/estimastruct-split-brain-sqlite-postgres`): los updates de precios v1.3 (goal-21062, 16 recursos) se escribieron **solo** en la SQLite `estimacion.db`; la BD Postgres `estimastruct` quedó stale desde abril 2026. Con Postgres declarado "primario" pero SQLite recibiendo los cambios reales, la fuente que el backend servía dependía del launcher (`START_POSTGRES_UNICA.ps1` vs arranque directo), no de una decisión explícita — dos tablas `recurso` divergentes sin dueño claro. Versionar la SQLite en git le da lo mismo que ADR-005 ya da a las fichas JSON: auditable por git, diffeable entre versiones, reproducible.
- Implicaciones:
  - Todo cambio de datos canónicos (precios, recursos, catálogo) se hace **sobre la SQLite versionada** y se commitea a git. **Nunca directo a Postgres.**
  - Postgres pasa de "fuente de verdad" a rol de runtime/deployment (copia de trabajo). El rationale original de ADR-001 (concurrencia transaccional, path a RDS) sigue siendo válido *como motor de ejecución*, no como canon de datos.
  - **Pendiente de reconciliación (NO cubierto por este ADR — requiere OK David):** decidir si el deployment sigue levantando Postgres hidratado desde la SQLite canónica, o si se colapsa a SQLite directo. Hasta resolverlo, §8 sigue describiendo el arranque Postgres real vigente; ese Postgres es copia, no canon.
  - §2.2 (diagrama container, "SQLite legacy / no primario"), §6 (tabla "DB primaria = PostgreSQL") y §8.3 (`ESTIMASTRUCT_DATABASE_URL`) quedan como descripción del **runtime**, no del canon. La jerarquía de verdad la manda este ADR.
- Trade-offs: la SQLite versionada no da concurrencia transaccional real; mientras el runtime siga en Postgres se mantiene el doble code-path `DB_IS_SQLITE`. La ganancia — datos canónicos auditables por git y fin del split-brain silencioso — pesa más para un producto de un solo operador con catálogo versionado por diseño.
- **Gate operativo:** este ADR queda documentado ANTES de escribir la v1.4. Ninguna escritura de datos canónicos ocurre sin pasar primero por la SQLite versionada.

**ADR-014: Reversión de ADR-013 — Postgres SÍ es la BD canónica de EstimaStruct v1.3+ (2026-08-15 08:42 CST, goal-21069).**
- Decisión final (David, 2026-08-15 08:42 CST): **ADR-013 (SQLite-canónica) queda sin efecto.** La base de datos canónica de EstimaStruct v1.3+ es **PostgreSQL `estimastruct` (127.0.0.1:5432)**. Se restaura ADR-001 como decisión vigente. El rationale de ADR-013 (auditar por git, evitar split-brain silencioso) se atiende de otra forma: versionando la SQLite como *export/snapshot* y migrando su contenido a Postgres, no invirtiendo la jerarquía de canon.
- Por qué la reversión fue limpia: la migración de datos de ADR-013 **nunca corrió** — el director estaba apagado cuando se aprobó, así que no se movió ningún dato ni se escribió la v1.4 sobre SQLite. Lo único que quedó fue el texto del ADR en este doc (header §6, tabla §6, footer §9), corregido por este ADR-014. No hay estado de datos que deshacer.
- Estado real de los datos (lo que este ADR NO resuelve): hoy la SQLite `estimacion.db` tiene los precios v1.3 reales (16 recursos promovidos 31-jul, goal-21062) y la Postgres `estimastruct` sigue **stale desde abril 2026** — el split-brain de goal-21062 sigue vivo. Declarar Postgres canónico **no lo sincroniza solo**.
- Trabajo pendiente (delegado, NO ejecutado aquí):
  - **goal-21070/21071 — diseño de migración SQLite v1.3 → Postgres canónica:** verificar el split-brain real (¿tiene Postgres MA-038=480 o sigue en precios de abril?), diseñar schema propio + migración controlada sin tocar `rag.chunks` ni datos de otros proyectos (regla 32). Entregable = **solo diseño + ADR para revisión de David**. La migración real a producción está gateada a un **segundo OK explícito de David** (goal-21071). Categoría de riesgo real: no ejecutarla sin ese OK.
  - **Reconciliación de deployment:** decidir si el runtime sigue en Postgres (ya es el canon) o cómo se hidrata — hoy `START_POSTGRES_UNICA.ps1` ya levanta Postgres, que ahora sí es la fuente de verdad, no una copia.
- Gate operativo: mientras Postgres siga stale, **cualquier escritura de datos canónicos (precios/recursos/catálogo) debe ir a Postgres**, y la SQLite v1.3 se trata como snapshot a migrar — no como una segunda fuente de verdad viva. No escribir en dos lados a la vez (eso es lo que creó el split-brain original).

**ADR-015: Migración controlada de precios v1.3 SQLite → Postgres vía UPDATE acotado, no snapshot-replace (2026-08-15 CST, goal-21070 — diseño gateado).** — ⏳ **DISEÑADO, NO EJECUTADO** (gate OK David → goal-21071). Diseño completo + runbook: `docs/migracion_sqlite_v13_postgres_goal21070_20260815.md`.
- Verificación del split-brain (parte 1, hecha): ambas `recurso` tienen las **mismas 367 claves** (0 altas/bajas); divergen **40 precios** (29 `MA-*` + 11 `MO-*`), no 16 — el "16" de goal-21062 fue solo el primer lote del 31-jul; el batch siguió hasta 40. Testigos: Postgres MA-038=195 (abril-21, stale) vs SQLite v1.3 MA-038=480 (31-jul). Postgres nunca recibió el batch del 31-jul (su máx. update es 07-jul, solo altas MA-374..377).
- Decisión de diseño: reconciliar con un **`UPDATE` transaccional acotado a los 40 precios divergentes de `public.recurso`**, con staging en schema efímero `estima_migration`, guardas de aborto (mismas 367 claves + exactamente 40 divergencias) y backup puntual (`pg_dump --table=recurso`) para rollback. La divergencia **no es monótona** (hay precios que suben y bajan) → regla = "SQLite v1.3 sobreescribe Postgres", nunca "tomar el máximo".
- **NO** usar `backend/scripts_runner/migrate_sqlite_to_postgres.py` → `import_sqlite_snapshot_into_primary()`: hace `table.delete()` sobre TODAS las tablas core y re-inserta desde el snapshot — borraría presupuestos/partidas/diseño de Postgres y pisaría `alembic_version`. Es reemplazo total, no reconciliación acotada.
- Regla 32: la migración no toca `rag.chunks`/`arch_chunks`/`csi_embeddings` ni ninguna BD fuera de `estimastruct`. Alcance total = `public.recurso` (UPDATE) + `estima_migration.*` (efímero, dropeado al final).
- Downstream (riesgo real, gate aparte): cambiar 40 precios invalida los totales cacheados de los presupuestos que usan esos recursos → recalcular (`estima_calcular`) por presupuesto, con su propio OK. No es parte automática de la migración.

---

## 8. Deployment & Infrastructure

### 8.1 Servicios requeridos (local)

| Servicio | Puerto | Startup |
|---|---|---|
| PostgreSQL | 5432 | Windows service `postgresql-x64-16` |
| FastAPI backend | 8002 | `uvicorn backend.main:app` |
| Flask UI | 5000 | `python ESTIMASTRUCT/app.py` |
| Revit MCP (opcional) | HTTP :8001 (externo) → Named Pipe `\\.\pipe\revit-mcp` (interno, sin puerto, hacia Revit) | `revit-mcp-stdio` `main_pipe.py --http`, `D:\GitHub\revit-mcp-stdio`, arranque via `POST /revit-mcp/start` |
| Brain (opcional, orquestación agentes) | 8200 | fuera de este repo |

### 8.2 Secuencia de arranque

```
START_POSTGRES_UNICA.ps1   (ÚNICO entry point válido — usa Postgres)
  ├─ git pull origin main --ff-only
  ├─ lee D:\Secrets\postgres_credentials.txt → password
  ├─ export ESTIMASTRUCT_DATABASE_URL=postgresql+psycopg://postgres:$pw@127.0.0.1:5432/estimastruct
  ├─ export ESTIMASTRUCT_AUTO_CREATE_SCHEMA=false   (Alembic maneja schema)
  └─ START_UNICA.ps1
        ├─ Kill-Port 5000 / 8002 (recursivo, incluye multiprocessing spawn)
        ├─ Borra __pycache__ (backend/ + routers/)
        ├─ Verifica deps (fastapi, flask, sqlalchemy, psycopg…)
        ├─ Job "back":  uvicorn backend.main:app --host 127.0.0.1 --port 8002
        └─ Job "front": python ESTIMASTRUCT/app.py
```

**No usar `START_UNICA.ps1` directo** — sin las env vars levanta SQLite legacy.

### 8.3 Env vars

| Var | Default | Rol |
|---|---|---|
| `ESTIMASTRUCT_DATABASE_URL` | `sqlite:///C:/EstimaStruct/data/estimacion.db` | conexión SQLAlchemy |
| `ESTIMASTRUCT_AUTO_CREATE_SCHEMA` | `true` si SQLite, `false` si PG | `Base.metadata.create_all` en lifespan |
| `ESTIMASTRUCT_UI_DB` | `C:\EstimaStruct\data\estimastruct.db` | SQLite dashboard UI legacy (Flask) |
| `ESTIMASTRUCT_API_BASE` | `http://localhost:8002` | Flask → FastAPI proxy |
| `ESTIMA_FICHAS_DIR` | `development/Template2_Updated` | catálogo fichas |
| `ESTIMA_OPUS_XLSX` | `D:\OneDrive\Bots\Estimbot\MasterFiles\BaseDatosOpus2026.xlsx` | BaseDatosOpus |
| `ESTIMA_UPDATER_DIR` | `D:\OneDrive\Bots\Estimbot\MasterFiles\Updater` | updater artefacts |
| `ESTIMA_EXPORTS_DIR` | `D:\OneDrive\Bots\Estimbot\EXPORTS` | S1_keynotes / S5_schedules |
| `SUPABASE_SECRET_KEY` | *(vacío)* | requerido solo para publish-supabase |

### 8.4 Migraciones

Alembic en `backend/alembic/`; `alembic upgrade head` requerido en Postgres (schema no se auto-crea). SQLite tolera `create_all` para dev.

### 8.5 Backup / portabilidad

`GET /db/export-zip` produce dump portable (Postgres → SQLite `estimacion.db` snapshot dentro de ZIP); `POST /db/import-zip` restaura al destino primario. Config en `CONFIG.SQLITE_EXPORT_NAME`.

**ADR-011: Output directory selector para export keynotes (2026-08-02).**
- Decisión: `POST /presupuestos/{pid}/scripts/keynotes` acepta parámetro opcional `output_dir` (JSON body). Si no viene, usa default `CONFIG.KEYNOTES_DIR`. Filenaming automático: `RevitKeynotes_<obra>_<fecha>_v<contador>.txt` (timestamp + contador de versión para no pisar archivos anteriores).
- Scope real: solo `generate_keynotes.py` afectado (204 líneas, script aislado). No toca `export_pdf.py`/`export.py` (ya son browser-side, no backend-side) ni `revit_full_dump_snippet.py` (IronPython hardcodeado, bloqueado, requiere MCP interface futura).
- Rationale: usuario debe elegir dónde guardar los keynotes generados, no recibir una ruta fija del servidor. Timestamp + contador garantiza **idempotencia** (no pisar exports anteriores, historial de cambios in situ).
- Trade-offs: parámetro de router nuevo; nombrado en OUTPUT con timestamp para ser predecible en test; versioning local (no versionamiento en BD), candidato a persistencia futura en tabla de auditoría si se unifica todo bajo control de presupuesto.

**ADR-012: Consolidar scripts IronPython en revit-mcp-stdio + automatización Paso 2 (2026-08-02, implementado — corrección de mecanismo 2026-08-02).**
- Decisión original (draft de sesión de análisis, goal-20178): mover `revit_dump_snippet.py`/`revit_full_dump_snippet.py`/`revit_marks_master.py` a `revit-mcp-stdio` y "registrar cada uno como tool MCP en `tool_manifest.py`". **Corrección al implementar:** `tool_manifest.py` es la tabla 1:1 de rutas HTTP pyRevit ya existentes (`revit_mcp/pipe/tool_registry.py::register_all()` resuelve cada entrada contra un route handler real vía `pyrevit.routes.server.router.get_route_handler` — agregar una entrada sin su route handler correspondiente no falla en registro pero devuelve `route_not_registered` en cada llamada). Los 3 scripts son texto IronPython crudo pensado para `execute_revit_code` (ya en el manifest), no rutas HTTP nuevas — no hay handler que registrar.
- Implementado de verdad: los 3 se movieron a `D:\GitHub\revit-mcp-stdio\revit_mcp\pipe\estimastruct_tools.py` como constantes `DUMP_AUDIT_CODE`/`DUMP_FULL_CODE`/`SET_MARKS_CODE` + funciones `dump_audit_json()`/`dump_full_json()`/`set_marks_master()` que envuelven `revit_mcp.pipe.helpers.execute_code()` (PipeClient directo, ver ADR-001 de revit-mcp-stdio) — mismo patrón que `helpers.py` ya establece para consumidores externos. `backend/routers/scripts.py::run_auditoria()` importa `dump_audit_json` (sys.path insert a revit-mcp-stdio) y lo llama automáticamente antes de `run_audit_pipeline()`; si el pipe falla (Revit ocupado/cerrado), loguea warning y sigue con el `model_audit_raw.json` que ya exista (no hard-fail, mismo criterio best-effort de ADR-001). `backend/routers/revit_mcp.py::_IRONPYTHON_SCRIPTS`/`_read_ironpython_code()` (endpoint manual `/inject/{name}`, sin tocar transporte) ahora lee `dump`/`dump-full`/`marks_master` desde el módulo consolidado en vez de `scripts_runner/`.
- Scope: 3 archivos movidos (211+1002+238 líneas CODE, contenido IronPython sin cambios) + `estimastruct_tools.py` nuevo (revit-mcp-stdio) + 2 archivos editados en EstimaStruct (`routers/scripts.py`, `routers/revit_mcp.py`). NO afecta Python backend (`build_generic_element_schema.py`, `audit_keynotes.py`, `sync_audit_colors.py`, `import_quantities.py` — quedan en EstimaStruct, sin cambios).
- Rationale: (a) Punto único de mantenimiento IronPython Revit. (b) Transporte PipeClient (confiable, ADR-001) en vez de paste manual o del HTTP `:8001` frágil de `mcp_http` para el flujo automatizado. (c) Cierra el gap real de Paso 2: antes `run_auditoria()` exigía correr `revit_dump_snippet` a mano en Revit ANTES de clickear "Auditoría"; ahora el dump se dispara solo.
- Trade-offs: dependencia EstimaStruct → revit-mcp-stdio vía `sys.path.insert` (cross-repo import, no paquete instalado — mismo patrón ya usado por `helpers.py`); `set_marks_master()` requiere `csi_to_codigo.json` fresco (sin cambios, lo genera EstimaStruct); endpoint manual `/revit-mcp/inject/{name}` (routers/revit_mcp.py) sigue en `mcp_http` (HTTP :8001, sin tocar — solo el flujo automatizado de `run_auditoria()` usa el pipe nuevo).
- Verification: `POST /presupuestos/{pid}/scripts/auditoria` dispara `dump_audit_json()` vía pipe, luego `run_audit_pipeline(pid)` sobre el JSON recién escrito — un solo click cierra Paso 2 completo sin pasos manuales en Revit (siempre que Revit esté abierto con el modelo activo).

---

## 9. Known Limitations & Future

**Incompleto / deuda técnica:**
- Sin autenticación ni multi-tenant — solo `127.0.0.1`.
- CORS `allow_origins=["*"]` — aceptable local, no SaaS.
- Respuestas no usan `response_model` Pydantic (dicts manuales) — sin contrato OpenAPI fuerte.
- SQLite legacy `estimastruct.db` aún sirve dashboard UI viejo (distinta de `estimacion.db`, la SQLite v1.3 versionada); consolidarla/retirarla pendiente.
- **Split-brain SQLite v1.3 ↔ Postgres sin resolver (ADR-014/015, 2026-08-15):** el canon es ahora Postgres `estimastruct` (ADR-014 revierte ADR-013), pero hoy la SQLite `estimacion.db` tiene los precios v1.3 reales y Postgres sigue stale desde abril 2026. **Verificado (goal-21070):** divergen **40 precios** (29 `MA-*` + 11 `MO-*`), mismas 367 claves — el "16" de goal-21062 fue solo el primer lote; Postgres MA-038=195 (abril) vs SQLite 480 (31-jul). La migración controlada (UPDATE acotado, no snapshot-replace) está **diseñada, no ejecutada** — ver ADR-015 y `docs/migracion_sqlite_v13_postgres_goal21070_20260815.md`; ejecución gateada a segundo OK de David (goal-21071). Hasta migrar: escribir datos canónicos **solo en Postgres** y tratar la SQLite v1.3 como snapshot a migrar (no como segunda fuente viva).
- Fichas JSON no propagan cambios a presupuestos ya instanciados (by-copy).
- Alembic history debe auditarse vs `Base.metadata` — riesgo drift si `AUTO_CREATE_SCHEMA=true` en Postgres.
- **Cero tests automatizados en el repo** (ni unitarios ni de integración): no existe `tests/`, `pytest.ini` ni CI. Toda validación es manual o por auditoría de snapshots. Es el bloqueo F0 del roadmap CASE-SAAS-001 §scope v2.
- **3/58 assemblies del pipeline dibujar-desde-DB fallan `CompoundStructure not valid` sin causa raíz completa aislada** (`goal-20147`, 2026-08-01): las 2 variantes "Bloque de 4"/6" + Cerámica Baño 2.10m" (Muros) y `ENC-01` (Suelos, con capa `StructuralDeck`). Diagnóstico parcial: al menos una capa `Finish2` traía `espesor_mm=0.0` (Revit exige >0 en cualquier función salvo `Membrane`) — corregido a un mínimo defensivo, pero **incluso a 0.1mm sigue fallando** (confirmado con `IsLayerValid`, aunque la comparación quedó contaminada porque se probó contra el `CompoundStructure` viejo del shell, no concluyente). Hipótesis sin confirmar: el mínimo real de Revit es mayor a 0.1mm (probar 1mm+), o la capa `CC-none` (placeholder de vacío, normalmente excluida del pipeline de auditoría, ver `revit_marks_master.py` `SKIP_NAMES`) no debería llegar como material real a una capa con espesor. Próxima sesión: recrear estos 3 tipos desde cero (no reusar el shell existente, que ya quedó en estado inconsistente) probando MIN_WIDTH_MM=1.0 y excluyendo/fusionando capas `CC-none`.
- **El pipeline dibujar-desde-DB nunca carga `keynotes.txt` en el template nuevo → auditoría sale 0% GREEN aunque el modelo esté bien** (`goal-20147`, 2026-08-01, hallazgo más grave de los tres). Verificado en vivo: `estimastruct_blank_template.rvt` tiene 102 compound elements con CSI correcto seteado directo en `KEYNOTE_PARAM` de cada Type, pero la `KeynoteTable` del proyecto (Manage → Keynoting Settings → archivo .txt) solo trae **8 entradas** — nunca se le apuntó al `.txt` que genera `generate_keynotes.py`. Resultado real corriendo `audit_keynotes.py`: **0 GREEN / 600 RED** de 600 filas — el audit compara TEXTO de keynote (viene de `KeynoteTable`, no del código CSI crudo) contra la descripción del catálogo, y sin tabla cargada no hay texto que comparar. Fix: correr `generate_keynotes.py` para el catálogo activo, y cargar el `.txt` resultante en Keynoting Settings del template ANTES de correr cualquier auditoría — falta un paso explícito en el pipeline (candidato a nuevo paso 5.5 en el flujo, o automatizarlo vía `execute_revit_code` seteando `KeynoteTable.GetKeynoteTable(doc).LoadFrom(path)` o equivalente).
- **`elementos_puntuales` (puertas/ventanas/MEP, 243 tipos) del pipeline dibujar-desde-DB nunca reciben su CSI/marca en el Type real** (2026-08-01): el paso de creación de familias (Fase 1) solo marca `assemblies` (muro/losa/techo/cielo falso) vía `KEYNOTE_PARAM`/`ALL_MODEL_TYPE_MARK`; las familias sueltas cargadas (`LoadFamily`) quedan con el keynote vacío de fábrica (vienen de librería Autodesk/vendor genérica). `revit_marks_master.py` no puede ayudarlas porque solo actúa sobre keynote YA existente — no hay paso que empuje el CSI/marca de `generic_element_schema.json::elementos_puntuales` a los Type reales. Gap real, no falso positivo (confirmado corriendo `revit_marks_master.py` contra `estimastruct_blank_template.rvt`: `door_win: 0`, `type: 0` — nada que marcar porque nada tiene keynote de origen).
- ✔ **[RESUELTO 2026-07-30, commit `0a7cbae`] Doble aplicación de sobrecosto en `/reporte`.** El hallazgo original (2026-07-27, vía `GET /auditoria/calculos/{pid}/memoria`): `/calcular` y `/reporte` llamaban "costo_directo" a dos cosas distintas — `/reporte` sumaba `partida.total` (que YA lleva sobrecosto) y volvía a multiplicar por `factor`. En "Casa StoneRaise" (sc=20%) daba Δ = L.328,435.49 (factor 1.44 = 1.2²). Corregido en `routers/calculos.py:75-92`: `reporte()` calcula `costo_directo` con `calc_base` (misma definición que `/calcular`) y devuelve `total_con_indirectos = Σ partida.total` sin re-aplicar el factor. **Re-verificado en vivo 2026-07-31** contra Postgres: Casa StoneRaise Δ = L.0.01 · CC132 Camilo (sc=25%) Δ = L.0.01 — residuo de redondeo, no doble aplicación.

**Roadmap (CASE-SAAS-001 P0, ADR-007/008/009):**
1. MCP STDIO `estimastruct-mcp` + Skill EstimaStruct full-system (Frente 1, prioridad inmediata).
2. LLM Anthropic API + CAG en `backend/cag/`.
3. ✔ **[RESUELTO 2026-07-30]** MCP Revit `revit-mcp-stdio` (46+ tools, `D:\GitHub\revit-mcp-stdio`) — reemplazó MCP HTTP :8100. Transporte real de dos saltos: EstimaStruct → FastMCP HTTP :8001 (`main_pipe.py --http`) → Windows Named Pipe `\\.\pipe\revit-mcp` (sin puerto TCP, `revit_mcp/pipe/listener.py` + `client.py`, Win32 API) → pyRevit dentro de Revit.exe. `backend/services/mcp_http.py` verificado en vivo contra Revit real.
4. MCP STDIO ETABS `etabs-mcp-stdio`.
5. IronPython scripts en `pyrevit/scripts/`.
6. FastAPI en AWS ECS/Lambda + RDS PG, auth JWT/OAuth2, feature flags multi-tenant.
7. OWASP Top 10 audit + hardening.

**Módulos estructurales — próximos pasos:**
- Módulo acero LRFD stateful ya persiste (R3); pendiente integrar `partida_acero_id` en flujo takeoff automático.
- Conexiones §J R5 persiste; falta UI de auditoría cruzada perfil ↔ conexión.
- ETABS import: extender parser a cargas de piso automáticas (hoy solo combos concreto).

---

*Última actualización: 2026-08-15 (ADR-015 — goal-21070: split-brain verificado = 40 precios divergentes recurso; migración de reconciliación diseñada como UPDATE acotado/transaccional con staging aislado, NO snapshot-replace; diseñada-no-ejecutada, gate OK David → goal-21071. Detalle: docs/migracion_sqlite_v13_postgres_goal21070_20260815.md. Sigue vigente ADR-014: Postgres `estimastruct` canónica de v1.3+). Próxima revisión: al aprobar David la ejecución de goal-21071, o al cerrar Frente 1 de CASE-SAAS-001.*
