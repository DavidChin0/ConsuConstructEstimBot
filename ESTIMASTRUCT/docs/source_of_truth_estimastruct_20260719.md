> [!CONTEXT]
> Fuente viva canónica de EstimaStruct al 2026-07-19. Este documento consolida la verdad operativa del sistema a partir de código real, RAG y documentación auditada.

> [!WARNING]
> **DEPRECADO 2026-07-21.** Estado actual vive en [`docs/architecture.md`](architecture.md).
> Secciones cubiertas: §1 Context, §2 Goal, §3 Containers, §5 Principios.
> Este archivo es registro histórico — no actualizar.

# EstimaStruct — Source of Truth 2026-07-19

## 1. Qué documento manda

> ⚠️ **2026-07-21:** `docs/architecture.md` es ahora #1 — este doc es histórico.

Desde el 2026-07-19, la jerarquía viva de verdad para EstimaStruct queda así:

1. Código real del repo `D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\`
2. Este documento: `docs/source_of_truth_estimastruct_20260719.md`
3. `docs/manual_mega_operativo_estimastruct_20260719.md`
4. `docs/postgres_runtime_estimastruct_20260719.md`
5. `CHANGELOG.md`
6. Auditorías y manuales viejos solo como contexto, no como contrato principal

## 2. Qué es EstimaStruct

EstimaStruct no es solo una UI ni solo un costeador.

Es el producto de presupuestos del ecosistema ConsuConstruct que junta:

- presupuesto CSI por capítulos, partidas e insumos
- importación de cantidades desde Revit
- generación de keynotes para Revit
- auditoría CSI contra Revit
- diseño estructural de concreto
- revisión/import de acero ETABS
- conexiones de acero
- cronograma
- exportes XLSX/PDF
- publicación al portal
- runtime dual PostgreSQL primario + SQLite de compatibilidad

## 3. Topología real

### 3.1 Procesos

- `backend/main.py`
  - FastAPI
  - puerto normal: `8002`
  - verdad del core de negocio
- `ESTIMASTRUCT/app.py`
  - Flask
  - puerto normal: `5000`
  - sirve HTML/CSS/JS y hace proxy same-origin a FastAPI por `"/__api__/*"`

### 3.2 Persistencia real

- BD primaria soportada y ya verificada:
  - PostgreSQL 16 local
  - base `estimastruct`
- BD de compatibilidad:
  - `C:\EstimaStruct\data\estimacion.db`
  - se usa para export/import/snapshot
- BD legacy de dashboard UI:
  - `C:\EstimaStruct\data\estimastruct.db`
  - ya no gobierna la operación del producto

## 4. Regla canónica de datos

### 4.1 Llave maestra

La llave maestra de EstimaStruct es `CSI`.

Reglas:

- `Partida.clave_csi` manda el costeo y el cruce con catálogo
- `DisenoElemento.csi` manda en diseño estructural
- `ConexionAcero.csi` manda en conexiones
- `type_mark` es secundario
- `Type Mark` no puede sustituir `CSI` como identidad del sistema

### 4.2 Fuente única de precio

La fuente única de cálculo de precio es:

- `backend/services/pricing.py`

Contrato:

- `costo_base = costo_mo + costo_ma + unitario_matriz`
- `precio_unitario = costo_base * (1 + sobrecosto/100)`
- `total = cantidad * precio_unitario`

Si otro archivo redefine esto inline, eso es deuda o riesgo.

## 5. Mapa real de módulos

### 5.1 Módulos visibles en UI

El dropdown `#sel-modulo` en `ESTIMASTRUCT/templates/index.html` hoy expone:

- `diseno` = Diseño de concreto
- `acero` = Acero
- `conexion` = Conexión acero
- `etabs` = ETABS / sismo

Fuera del dropdown pero parte del producto:

- presupuestos / partidas / insumos
- bases de datos
- exportes
- cronograma
- portal publish
- scripts Revit

### 5.2 Routers vivos

FastAPI incluye hoy estos routers en `backend/main.py`:

- `presupuestos`
- `partidas`
- `recursos`
- `calculos`
- `export`
- `insumos`
- `scripts`
- `bases`
- `updater`
- `diagnostics`
- `memory`
- `diseno_estructural`
- `sismo`
- `acero_diseno`
- `conexion_acero`
- `miembro_acero`
- `portal_publish`
- `cronograma`
- `export_pdf`
- `preview_pdf`
- `db_backup`

## 6. Semántica canónica con Revit MCP

### 6.1 Qué sí es Revit MCP para EstimaStruct

Revit MCP es la capa de control y extracción sobre el modelo Revit.

Para EstimaStruct, su rol canónico es:

- leer tipos, instancias, materiales y keynotes
- producir dumps auditables
- apoyar auditoría CSI
- permitir aplicación guiada de cambios sobre keynotes/materiales cuando el flujo lo requiera

### 6.2 Qué no es Revit MCP para EstimaStruct

Revit MCP no es:

- la fuente de verdad del catálogo
- la fuente de verdad del precio
- la fuente de verdad del presupuesto
- el lugar donde se decide la semántica de una partida

La autoridad semántica vive en EstimaStruct y su catálogo CSI.

### 6.3 Contrato semántico EstimaStruct ↔ Revit MCP

Contrato correcto:

1. EstimaStruct define el catálogo CSI, descripciones y matrices.
2. `generate_keynotes.py` emite el `keynotes.txt` desde ese catálogo.
3. Revit usa ese archivo para etiquetar.
4. Revit MCP audita lo que existe de verdad en el modelo.
5. `audit_keynotes.py` compara modelo vs catálogo.
6. El resultado regresa a EstimaStruct como auditoría, no como nueva autoridad.

Resumen:

- EstimaStruct manda la semántica.
- Revit/Revit MCP reflejan y verifican.
- El presupuesto no debe depender de una semántica nacida en Revit.

### 6.4 Contrato operativo con pyRevit / schedules

Contrato correcto:

1. Revit / pyRevit exportan schedules
2. EstimaStruct importa cantidades
3. EstimaStruct recalcula costo
4. EstimaStruct exporta presupuesto e insumos

Esto vive hoy en:

- `backend/scripts_runner/import_quantities.py`
- `backend/routers/scripts.py`

## 7. Módulos y su función real

### 7.1 Presupuesto base

Núcleo del sistema:

- obras
- capítulos
- partidas
- insumos
- recursos
- cálculo de costos

Archivos clave:

- `backend/models.py`
- `backend/routers/presupuestos.py`
- `backend/routers/partidas.py`
- `backend/routers/insumos.py`
- `backend/routers/recursos.py`
- `backend/services/pricing.py`

### 7.2 Bases de datos

Editor/auditor de matrices y versiones de catálogo.

Archivos clave:

- `backend/routers/bases.py`
- `frontend/js/bases-drawer.js`
- `development/Template2_Updated/`

### 7.3 Scripts Revit

Puente operativo con el mundo BIM.

Hoy cubre:

- generar keynotes
- listar CSVs exportados
- importar cantidades
- correr auditoría CSI

Archivos clave:

- `backend/routers/scripts.py`
- `backend/scripts_runner/generate_keynotes.py`
- `backend/scripts_runner/import_quantities.py`
- `backend/scripts_runner/audit_keynotes.py`
- `backend/scripts_runner/run_audit_pipeline.py`

### 7.4 Diseño estructural concreto

Módulo stateful de elementos, casos, resultados y memorias.

Archivos clave:

- `backend/routers/diseno_estructural.py`
- `backend/calculo_estructural.py`

### 7.5 Acero

Módulo de import y revisión de miembros de acero desde ETABS, con generación opcional de partidas Div 05 ya existente en el código.

Archivos clave:

- `backend/routers/acero_diseno.py`
- `backend/calculo_miembro_acero.py`
- `backend/services/etabs_parse.py`
- `backend/acero_ficha.py`
- `backend/perfiles_acero.py`

### 7.6 Conexión acero

Módulo de conexiones §J, catálogo, memoria rápida, persistencia y puente parcial con ETABS/pyRevit.

Archivos clave:

- `backend/routers/conexion_acero.py`
- `backend/calculo_conexion_acero.py`

### 7.7 ETABS / sismo

Módulo de contexto sísmico CHOC-08 y export/import del espectro/validaciones.

Archivos clave:

- `backend/routers/sismo.py`
- `backend/calculo_sismico_choc08.py`
- `backend/etabs_procedimiento.py`

### 7.8 Cronograma

Genera y exporta el Gantt desde las partidas y overrides de personal.

Archivos clave:

- `backend/routers/cronograma.py`
- `backend/cronograma.py`

### 7.9 PDFs y portal

- `backend/routers/export_pdf.py`
- `backend/routers/preview_pdf.py`
- `backend/routers/portal_publish.py`

### 7.10 Runtime y backups

- `backend/config.py`
- `backend/db.py`
- `backend/db_transfer.py`
- `backend/routers/db_backup.py`
- `backend/scripts_runner/migrate_sqlite_to_postgres.py`
- `START_UNICA.ps1`
- `START_POSTGRES_UNICA.ps1`

## 8. Qué documentos pasan a satélite

Estos documentos siguen sirviendo, pero no mandan como contrato principal:

- `MANUAL_ESTIMASTRUCT.md`
- `MANUAL_USUARIO.md`
- `ARQUITECTURA_Y_FLUJO.md`
- `docs/auditoria_arquitectura_20260712.md`

Uso correcto:

- manuales viejos = contexto histórico/táctico
- auditorías = evidencia y hallazgos
- este documento = contrato vivo

## 9. Riesgos vivos que no desaparecen por documentar

- existe deuda de lógica duplicada fuera de `pricing.py`
- hay routers grandes, especialmente `diseno_estructural.py`
- no hay red de tests seria para el core financiero/estructural
- `allow_origins=["*"]` sigue abierto en local
- el puente Revit MCP sigue dependiendo de flujo asistido, no 100% cerrado

## 10. Regla final

Si un cambio futuro toca semántica, integración Revit, pricing, runtime o módulos, primero se actualiza este documento y luego el manual operativo.
