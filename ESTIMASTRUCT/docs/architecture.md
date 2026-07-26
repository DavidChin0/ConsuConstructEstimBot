# Architecture — EstimaStruct

> **Estado:** production local (Postgres primario desde 2026-07-20) · migración SaaS declarada (CASE-SAAS-001).
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
              │ :8100     │ │ CSV  │ │ Portal      │
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
              [Postgres :5432]     [Template2_Updated]  [MCP HTTP :8100]
              estimastruct DB      fichas_v1.3.json     Revit / ETABS
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
| DB primaria | PostgreSQL 16, driver `psycopg[binary]>=3.2` |
| DB legacy | SQLite (compat export/import, dashboard UI viejo) |
| Frontend UI | Flask 3.1.3 (Jinja2), JS vanilla modular (`core.js`, `app.js`, `tabla-render.js`, `bases-drawer.js`, `calculo-estructural.js`, `db-backup.js`) |
| Fórmulas | KaTeX vendorizado en `frontend/vendor/` |
| 3D Viewer | Babylon.js (`frontend/viewer/`) — GLB desde Revit |
| PDF | ReportLab 4.5.1 + Chromium headless (`export_pdf.py`, `preview_pdf.py`) |
| XLSX | openpyxl 3.1.2, xlrd 2.0.1 (BaseDatosOpus2026.xlsx) |
| Integraciones | Revit MCP HTTP :8100 (IronPython inject), ETABS CSV parse, Supabase REST |
| Runtime local | `D:\LLM\python\python.exe`, Windows 11, PowerShell launcher |

---

## 7. ADRs

**ADR-001: Postgres primario, SQLite compat.**
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

---

## 8. Deployment & Infrastructure

### 8.1 Servicios requeridos (local)

| Servicio | Puerto | Startup |
|---|---|---|
| PostgreSQL | 5432 | Windows service `postgresql-x64-16` |
| FastAPI backend | 8002 | `uvicorn backend.main:app` |
| Flask UI | 5000 | `python ESTIMASTRUCT/app.py` |
| Revit MCP (opcional) | 8100 | `POST /revit-mcp/start` |
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

---

## 9. Known Limitations & Future

**Incompleto / deuda técnica:**
- Sin autenticación ni multi-tenant — solo `127.0.0.1`.
- CORS `allow_origins=["*"]` — aceptable local, no SaaS.
- Respuestas no usan `response_model` Pydantic (dicts manuales) — sin contrato OpenAPI fuerte.
- SQLite legacy `estimastruct.db` aún sirve dashboard UI viejo; consolidar en Postgres pendiente.
- Fichas JSON no propagan cambios a presupuestos ya instanciados (by-copy).
- Alembic history debe auditarse vs `Base.metadata` — riesgo drift si `AUTO_CREATE_SCHEMA=true` en Postgres.
- Sin tests unitarios formales del pipeline pricing (validación por auditoría manual de snapshots).

**Roadmap (CASE-SAAS-001 P0, ADR-007/008/009):**
1. MCP STDIO `estimastruct-mcp` + Skill EstimaStruct full-system (Frente 1, prioridad inmediata).
2. LLM Anthropic API + CAG en `backend/cag/`.
3. MCP STDIO Revit `revit-mcp-stdio` (46+ tools) — reemplaza MCP HTTP.
4. MCP STDIO ETABS `etabs-mcp-stdio`.
5. IronPython scripts en `pyrevit/scripts/`.
6. FastAPI en AWS ECS/Lambda + RDS PG, auth JWT/OAuth2, feature flags multi-tenant.
7. OWASP Top 10 audit + hardening.

**Módulos estructurales — próximos pasos:**
- Módulo acero LRFD stateful ya persiste (R3); pendiente integrar `partida_acero_id` en flujo takeoff automático.
- Conexiones §J R5 persiste; falta UI de auditoría cruzada perfil ↔ conexión.
- ETABS import: extender parser a cargas de piso automáticas (hoy solo combos concreto).

---

*Última actualización: 2026-07-24. Próxima revisión: al cerrar Frente 1 de CASE-SAAS-001.*
