> [!CONTEXT]
> **[HISTORICO 2026-07-19]** Documento maestro previo a la source of truth nueva. Varias afirmaciones aquí quedaron superadas por el runtime PostgreSQL primario, el proxy Flask `__api__`, la expansión de módulos y la consolidación documental nueva. Se conserva como antecedente de razonamiento. Ver `docs/source_of_truth_estimastruct_20260719.md` y `docs/manual_mega_operativo_estimastruct_20260719.md`.

# EstimaStruct — Arquitectura, Flujo de Trabajo y Plan de Consolidación

> **ESTADO:** histórico de consolidación. No usar como contrato principal vigente.

> **Documento maestro / contrato.** Define una sola vez cómo funciona EstimaStruct hoy,
> el flujo end-to-end intencionado, y el plan de cambios aprobado.
> Base: auditoría completa del código (backend + frontend + pyRevit + docs del vault), 2026-06-01.
> Fuente de verdad operativa = `estimacion.db`. Fuente de verdad del flujo = este documento + `vault/03 Automation Projects/`.

---

## 0. Principios (no negociables)

1. **EstimaStruct es la verdad operativa.** Revit aporta cantidades + clasificación; ETABS aporta demanda; ProposalBot consume. Ninguno es la verdad, solo alimentan.
2. **El código CSI (`clave_csi`) es la LLAVE MAESTRA.** Une ficha ↔ keynote Revit ↔ cantidad ↔ partida ↔ propuesta. Es el ÚNICO identificador que cruza todos los mundos. `type_mark` es etiqueta secundaria, nunca llave.
3. **Toda ficha se respalda con insumos.** Una ficha (partida) sin insumos no es válida. Los insumos salen de la base curada (`Template2_Updated/fichas_v1.X.json`) o del catálogo de Recursos.
4. **Métrico unificado** en ingeniería: kgf, cm, t, t·m. (El módulo Soldadura legacy es imperial kips/ksi — a deprecar.)
5. **Hoja estilo Mathcad:** cada fórmula visible = símbolo := fórmula = sustitución numérica = resultado, en notación real (KaTeX). El cálculo debe ser auditable a mano. Calcar la norma/fuente, no inventar pasos.
6. **Archivos ETABS/Revit = read-only.** EstimaStruct importa (exportar-y-pegar / CSV), no escribe en ellos. Import automático de geometría futuro = Revit, no ETABS.

---

## 1. Arquitectura

### Stack
- **Backend:** FastAPI (`main.py`) + SQLAlchemy ORM (`models.py`) sobre **SQLite** (`backend/estimacion.db`, `db.py`). 14 routers. Sin Alembic: `Base.metadata.create_all` crea tablas; las columnas aditivas dependen de `migrate_*.py` manuales.
- **Frontend:** vanilla JS (`frontend/js/app.js`, ~5600 líneas) servido por **Flask** (`ESTIMASTRUCT/app.py`, :5000, plantilla `templates/index.html`). KaTeX vendorizado local. `ASSET_VERSION = mtime(app.js)` al arrancar → reiniciar Flask tras editar para bustear cache.
- **Backend FastAPI** en :8002.

### Dos modelos de datos (conviven)
**(A) Presupuesto clásico (raíz de costo):**
```
Presupuesto → ConfigPresupuesto(1:1, sobrecosto)
            → Capitulo (por división CSI)
              → Partida (clave_csi, cantidad, precios)
                → InsumoPartida (cantidad × costo_unit)
                  → Recurso (catálogo de precios)
```
Costo: insumos → `costo_mo`/`costo_ma` → `costo_base = MO+MA+matriz` → `precio_unitario = base×(1+sobrecosto/100)` → `total = cantidad×PU`.
Origen de partidas: fichas JSON (`from-template`) o Revit (`revit_q × factor_e × factor_f`).

**(B) Ingeniería (diseño estructural):**
```
DisenoElemento (geometría/perfil, material_tipo CONCRETO|ACERO)
  → CasoDiseno (cargas por combinación, origen MANUAL|ETABS)
    → ResultadoDiseno (As / φRn / DC / takeoff)
```
Motores PUROS sin ORM (`calculo_*.py`). Patrón 4 capas: **Request(Pydantic) → Router → Motor puro → Resultado**.

### Puente A↔B (la unión)
El motor calcula takeoff → `ResultadoDiseno` → `POST /diseno/casos/{cid}/generar-partidas` crea partidas CSI con cantidades reales. Concreto → Div 03; acero → Div 05.

---

## 2. Mapa de módulos

### Frontend (5 módulos, dropdown `#sel-modulo`, exigen presupuesto activo)

| Módulo | id | Hace | Persiste | Partida | Estado |
|--------|-----|------|----------|---------|--------|
| **Diseño** | `#diseno-view` | Concreto ACI 318-19 (viga/columna) + Hoja Mathcad. *(import acero LRFD vive aquí — a mover)* | ✅ | ✅ Div 03 | El más completo |
| **Acero** | `#acero-view` | Calculadora miembro LRFD §D-H (stateless). *Título dice "Puente ETABS Div 05" pero ya no importa* | ❌ | ❌ | A consolidar |
| **Conexión** | `#conexion-view` | Conexiones §J completo, métrico, con insumos de ficha | ❌ | ❌ | A cerrar E2E |
| ~~**Soldadura**~~ | ~~`#soldadura-view`~~ | **ELIMINADO (R7)** — subsumido por Conexión §J | — | — | Borrado físico con backup |
| **ETABS** | `#etabs-view` | Espectro sísmico CHOC-08 (concreto) | contexto | — | OK *(nombre choca con Acero)* |

### Backend — motores y routers clave

| Componente | CSI | Estado |
|-----------|-----|--------|
| `calculo_estructural.py` (ACI 318-19, hub de helpers LaTeX) | 03 | ACTIVO |
| `calculo_miembro_acero.py` (LRFD §D-H) | 05 | ACTIVO |
| `calculo_conexion_acero.py` (LRFD §J completo) | 05 | ACTIVO |
| `calculo_soldadura.py` (§J2 filete imperial) | 05 | **DUPLICADO** |
| `calculo_sismico_choc08.py` | sismo | ACTIVO |
| `perfiles_acero.py` (TABLA_W, PERFILES_ACERO, PERNOS, ACEROS) | 05 | ACTIVO (fuente única) |
| `acero_ficha.py` (perfil→ficha, conexion_ficha, insumos_ficha, parser ETABS acero) | 05 | ACTIVO |
| `seccion_ficha.py` (sección→ficha concreto, parser ETABS concreto) | 03 | ACTIVO |
| `etabs_procedimiento.py` (procedimiento + parser sísmico) | 03/05 | ACTIVO |
| `routers/diseno_estructural.py` (concreto + sismo + 4 puentes ETABS) | 03/04/sismo | ACTIVO (2097 líneas) |
| `routers/miembro_acero.py`, `routers/conexion_acero.py` | 05 | ACTIVO (stateless) |
| `routers/soldadura_estructural.py` | 05 | **DUPLICADO** |
| `routers/scripts.py` (keynotes + import quantities Revit) | todas | ACTIVO |
| `scripts_runner/generate_keynotes.py`, `import_quantities.py` | todas | ACTIVO |

---

## 3. Pipeline end-to-end (la visión)

```
[1] ESTIMASTRUCT (verdad): obra + fichas (Div 03/04/05) + insumos. Cada ficha = un CSI único.
        │  CSI = llave maestra
        ▼
[2] REVIT + pyRevit: modela BIM
        ├─ EstimaStruct genera RevitKeynotes_*.txt (generate_keynotes.py)
        ├─ Revit carga el TXT → Autotag Keynotes taggea por CSI válido (omite lo que no está)
        ├─ Exportar Keynotes (auditoría) → confirma familia↔CSI
        └─ Exportar Schedules → schedules_*.csv (cantidades por CSI)
        ▼
[3] ETABS (análisis sísmico CHOC-08): cada elemento entra como sección con material/dim/refuerzo
    REALES de su ficha; mampostería Div 04 = carga Super Dead. Espectro CHOC-08 User Defined,
    modal ≥90%, combos, escalar cortante, derivas ≤1/200.
        ▼
[4] IMPORT A ESTIMASTRUCT (read-only): export ETABS (Base Reactions/Modal/Story Drifts/fuerzas
    por combo) → parser tolerante → autollena sismo + crea DisenoElemento + CasoDiseno
    (mapeo sección/perfil → ficha CSI).
        ▼
[5] REVISIÓN DE DISEÑO (Hoja Mathcad): motor ACI (concreto Div 03) + motor LRFD §D-H
    (miembros acero Div 05) revisan, calculan combo gobernante, takeoff. Fórmulas auditables.
        ▼
[6] CONEXIONES VÍA CSI: por par (perfil_col, perfil_viga) + fuerzas de nudo ETABS → resuelve
    ficha CV/VV/CX/placa-base, verifica §J (J2/J3/J4/J8), cuenta piezas.   ◄── GAP: no construido E2E
        ▼
[7] GENERAR PARTIDAS: cada elemento/caso/conexión vuelca cantidades a partidas por CSI
    (Div 03: concreto m³, encofrado m², acero kg · Div 05: perfil mL, conexión pza, soldadura mL).
        ▼
[8] PROPOSALBOT consume el presupuesto cuantificado + planos → propuesta.
```

### Flujo Revit/pyRevit/keynotes (CICLO ya productivo)
- **Genera keynotes:** `generate_keynotes.py` → `RevitKeynotes_<obra>_<fecha>.txt` (Latin-1, TAB, CRLF, sin BOM). Sec.1 divisiones, Sec.2 partidas CSI. Disparado por Dev Menu "Paso 2".
- **Revit:** carga TXT como Keynote Table; `Autotag Keynotes` (pyRevit) taggea por CSI válido; `Exportar Keynotes` (pyRevit) audita familia↔CSI (CSV de revisión manual).
- **Schedules:** `Exportar Schedules` (pyRevit) → `schedules_*.csv` (bloques `###`, columna Keynote+cantidad).
- **Import:** `import_quantities.py` parsea CSV, agrega por CSI normalizado, `ceil`, escribe `revit_q`/`cantidad`, recalcula con sobrecosto. Dev Menu "Paso 4".
- **Join = solo CSI.** OmniClass/Assembly existen en BD pero NO se cruzan en runtime.
- ⚠️ La extensión pyRevit productiva (7 botones) vive en `%APPDATA%/pyRevit` **fuera del repo** (riesgo de drift).

### Flujo ETABS
`etabs_procedimiento.py` codifica el manual de 15 pasos (CHOC-08 + ACI/AISC). `parse_export_etabs()` (tolerante CSV/TSV/xlsx) autollena W/T/V_din/deriva. `import-etabs-concreto` / `import-etabs-acero-fuerzas` mapean sección→ficha→caso→motor. **No hay API CSI OAPI live** — el flujo real es exportar-y-pegar.

---

## 4. Estado actual vs diseñado (divergencias)

| Diseñado (vault) | Construido | Divergencia |
|------------------|-----------|-------------|
| Concreto ACI 318-19 + sismo CHOC-08 + import ETABS | ✅ casi completo | Torsión usa 318-71; columna sin P-M-M biaxial real |
| Miembros acero LRFD §D-H | ✅ | HSS sin §E/§F; faltan auditar tf/tw |
| Conexiones §J con persistencia + partidas Div 05 + import fuerzas-nudo | ⚠️ solo calculadora stateless | **Paso 6 NO construido E2E** |
| Conexiones ABSORBE soldadura (métrico, cierra 12 gaps) | ❌ | 2 motores de soldadura coexisten |
| Keynotes + import quantities Revit | ✅ productivo | OmniClass/Assembly desconectados |

---

## 5. PLAN DE CONSOLIDACIÓN APROBADO

Decisiones del Director (2026-06-01). **Orden: documento (este) → luego código.**

> **ESTADO DE IMPLEMENTACIÓN (2026-06-01):**
> - **Fase 1 ✅** — este documento + `MANUAL_USUARIO.md`.
> - **Fase 2 ✅** — Acero consolidado: módulo `#acero-view` con 3 vistas (Calculadora §D-H · Importar ETABS · Cómo se usa) + lista elementos + `POST /diseno/{pid}/acero-generar-partidas` (Div 05 mL). Import movido FUERA de Diseño-concreto; Diseño filtrado a CONCRETO; título corregido.
> - **Fase 3 ✅ (ligero)** — Conexión escribe al presupuesto: `POST /diseno/{pid}/conexion-generar-partida` (partida Div 05 pza con insumos de ficha CV/VV/CX). Botón en la card de ficha. Demanda manual (Vu/Nu/Mu) en el calculador. Cantidades masivas siguen por Revit C10.
> - **Fase 4 ✅ (completada en R7)** — Soldadura primero ocultada del dropdown (`<option hidden>`), luego **borrada físicamente** (R7) con backup de BD previo. Router/motor/tabla/modelo/vista eliminados.
> - **R1 ✅ HSS §E3/§F7/§G4** — las 3 columnas HSS (C-1..C-3) ahora se verifican (compresión E3 · flexión F7 sin LTB con FLB · cortante G4). Props HSS cerradas en `perfiles_acero.props_seccion`. Pendiente solo: pandeo local E7 de paredes esbeltas (aviso).
> - **R2 ✅ Placa base §J8** — tipo `PLACA_BASE` en el calculador de Conexión: aplastamiento del concreto `φPp=0.65·0.85·f'c·A1·√(A2/A1)≤0.65·1.7·f'c·A1` (estado `aplastamiento_concreto`) + espesor de placa por voladizo DG-1 `tp=l·√(2·fp/(0.90·Fy))`, l=max(m,n,n'). 5 pasos narrados en la Hoja (§J8). Inputs `P_u, f'c, B, N, A2` vienen de ETABS pero quedan **editables como variables** (B,N,A2=0 → deriva del perfil columna). Verificado HTTP: Pu=80t DC=0.475 cumple · Pu=200t DC=1.19 no-cumple.
> - **R3 ✅ Router acero stateful separado** — los 4 endpoints de acero que tocan BD (`import-etabs-acero`, `import-etabs-acero-fuerzas`, `acero-generar-partidas`, `conexion-generar-partida`) salieron de `diseno_estructural.py` (2258→1772 líneas) a **`routers/acero_diseno.py`** (prefix `/diseno`, **mismos paths** → frontend intacto). Los helpers compartidos (`_correr_caso_acero`, `_marcar_gobierna_acero`, `_perfil_acero_valido`, `_get_o_crear_capitulo`, `_crear_o_actualizar_partida`, `_es_xlsx`, `_decode_bytes`) viven en `diseno_estructural` (los usan también `/casos/{cid}/calcular` y `/memoria`) y se importan: unidireccional, sin ciclo. Verificado: `import main` OK, 4 rutas registradas, 404 funcional en pid bogus.
> - **R4 ✅ Import masivo fuerzas-nudo ETABS→conexión** — `POST /conexion-acero/import-etabs-fuerzas` (stateless). Parsea la tabla de fuerzas de ETABS (`member,P,V2,M2,M3,Combo`, coma/tab) y por cada nudo toma la **envolvente de DC** sobre todas las combinaciones. Dos modos: (a) sin specs → envolvente de fuerzas por nudo (Vu/Mu/P máx + combo); (b) con specs `[{member,tipo,perfil_viga,perfil_columna,…}]` → corre `calcular_conexion` por combo, devuelve DC/estado_gob/cumple gobernante. Frontend: 3ª vista del módulo Conexión "📥 Importar ETABS (lote)" — pega tabla + perfiles plantilla → tipo auto por heurística (P domina→placa base · M→momento · resto→cortante) → tabla DC ordenada con sobre-esforzados resaltados. Verificado HTTP: B1 VC_MOMENTO CV-3 DC=0.79 cumple · C1 PLACA_BASE §J8 DC=0.475 cumple. **Sin nuevas tablas** (no requiere R5).
> - **R5 ✅ Persistencia de conexión (3 tablas)** — `conexion_acero` / `conexion_caso` / `conexion_resultado` (espejan DisenoElemento/Caso/Resultado; `migrate_conexion.py` idempotente, create_all aditivo). CRUD persistido en `routers/conexion_acero.py`: `POST/GET /conexion-acero/{pid}/conexiones` · `GET/PUT/DELETE /conexion-acero/conexiones/{cid}` · `POST .../recalcular`. Cada caso corre §J (`_correr_conexion_caso`) y persiste estado_gob/φRn/DC/cumple/estados_json/j8_json; gobernante = max DC. Frontend: botón "💾 Guardar conexión" en el cálculo + 5ª vista "📂 Guardadas" (lista DC/cumple + borrar). Verificado ciclo CRUD completo (create 2 casos→envolvente · PUT recompute · delete cascade). Falta opcional: persistir lote/placas masivos + link a partida.
> - **R7 ✅ Borrado físico de Soldadura** — eliminado el módulo legacy (subsumido por Conexión §J). Backend: borrados `routers/soldadura_estructural.py` + `calculo_soldadura.py`, removida clase `MatrizSoldaduraConexion`, **DROP TABLE `soldadura_conexion`** (backup `estimacion.db.bak_R7_20260602` previo), desregistrado en `main.py`, limpiado `audit_db.py`. Frontend: removidas 443 líneas de `app.js` (módulo + Hoja soldadura) + 202 de `index.html` (`#soldadura-view` + modal + option). Conservadas las refs de **dominio §J2** (weld dentro de Conexión: `L_soldadura_cm`, "Soldadura §J2"). Verificado: backend UP 0 rutas soldadura · `node --check` OK · sin llamadas colgantes.
> - **Pendiente (roadmap):** R6 OmniClass/Assembly.

### Fase 1 — Documento maestro ✅ (este archivo)

### Fase 2 — Consolidar módulo Acero (consolidación completa)
El módulo **Acero (`#acero-view`)** se vuelve el ÚNICO hogar del acero:
1. **Mover** el botón import-acero (`#btn-diseno-import-acero`) FUERA del sidebar de Diseño-concreto → al módulo Acero.
2. **Reubicar** el endpoint `import-etabs-acero-fuerzas` (hoy en `diseno_estructural.py`, router de concreto) + helpers (`_acero_caso_dicts`, `_correr_caso_acero`, `_marcar_gobierna_acero`, `_perfil_acero_valido`) → router de acero.
3. **Unificar** las 3 caras del acero en el módulo: (a) calculadora miembro stateless, (b) import+persistencia ETABS, (c) puente a partidas Div 05 (recuperar el endpoint huérfano `import-etabs-acero` perfil→ficha→partidas).
4. **Filtrar** elementos `material_tipo=ACERO` para que NO se listen revueltos con concreto.
5. **Arreglar** el título del panel (ya no es "Puente ETABS Div 05" a secas) + **añadir tab "Cómo se usa"** (patrón skill `estimastruct-modulo`).
6. **Limpiar** código muerto: `importarAceroEtabs`/`renderAceroResult` (reusar o eliminar).

### Fase 3 — Cerrar Conexiones end-to-end (gap #1)
Construir lo que `plan_modulo_conexiones_acero_aisc_lrfd.md` ya diseñó:
1. **Persistencia:** 3 tablas (`conexion_elemento`/`caso_conexion`/`resultado_conexion`) o reusar patrón existente.
2. **Generar partidas Div 05** por CSI: conexión pza (CV/VV/CX con insumos) + soldadura mL + placa pza.
3. **Import de fuerzas de nudo ETABS** (Vu/Nu/Mu por combo) → demanda real de la conexión (hoy se teclea, default Vu=0 → chequeo trivial).
4. **Placa base §J8** (aplastamiento concreto + espesor).

### Fase 4 — Deprecar Soldadura (portar primero, luego borrar)
1. Portar a Conexiones el **modelo de costo por metro** de Soldadura (peso electrodo, HH) + el **sync automático** desde partidas de acero.
2. **Migrar** datos de `soldadura_conexion` (presupuestos vivos).
3. **Borrar** Soldadura: `routers/soldadura_estructural.py`, `calculo_soldadura.py`, tabla `MatrizSoldaduraConexion`, vista `#soldadura-view`, option del dropdown, ramas en `setModuloActivo`/`patchClose`. (Ningún otro módulo los importa → sin cadena rota.)

---

## 6. Convenciones / reglas

- **CSI llave maestra.** Claves sintéticas ETABS (`ETABS-ACERO:member`) son trazabilidad, NO CSI reales — separar conceptualmente.
- **Métrico** en todo motor nuevo. Soldadura imperial = legacy.
- **Fichas con insumos** siempre (base curada `fichas_v1.X.json`).
- **Fuente única de perfiles** = `perfiles_acero.py` (TABLA_W exacto; geometría aproximada solo fallback).
- **Migraciones:** SQLite + `create_all`; columnas aditivas → `migrate_*.py` manual (correr tras editar `models.py`).
- **Servers:** matar TODOS los `python.exe` colgados antes de arrancar uno (zombies dejan ASSET_VERSION viejo). Flask :5000 + backend :8002.

---

## 7. Roadmap de gaps (post-consolidación)

**🔴 Bloqueantes:** Conexiones E2E (Fase 3) · Soldadura absorbida (Fase 4) · fuerzas de nudo ETABS→conexiones.
**🟠 Arquitectura:** acero separado de concreto (Fase 2) · costo repartido en 3 módulos → unificar fuente · Alembic / migraciones automáticas.
**🟡 Motores:** ~~HSS §E/§F (R1 ✅)~~ · ~~placa base §J8 (R2 ✅)~~ · columna concreto P-M-M biaxial · torsión 318-19 · choque normas 318-14 vs 318-19 · pandeo local E7 paredes esbeltas HSS.
**🟢 Integración:** OmniClass/Assembly al flujo · consolidar pyRevit `EstimBot.extension` en el repo · import quantities modo "merge" vs "replace" · reporte diff keynotes (TXT vs modelo).

---

*Mantener este documento como contrato. Actualizar al cerrar cada fase. Cambios con `#contract/proposal` exigen verificar consistencia EstimaStruct ↔ ProposalBot.*
