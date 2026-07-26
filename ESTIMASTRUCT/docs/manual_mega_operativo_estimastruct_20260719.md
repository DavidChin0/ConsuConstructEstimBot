> [!CONTEXT]
> Manual mega operativo de EstimaStruct al 2026-07-19. Describe cómo operar el producto completo desde runtime hasta módulos y flujos Revit/ETABS.

> [!WARNING]
> **DEPRECADO 2026-07-21.** Estado actual vive en [`docs/architecture.md`](architecture.md).
> Secciones cubiertas: §4 Components, §5 Flows.
> Este archivo es registro histórico — no actualizar.

# EstimaStruct — Manual Mega Operativo 2026-07-19

## 1. Antes de tocar nada

Leer en este orden:

1. `docs/source_of_truth_estimastruct_20260719.md`
2. este manual
3. `docs/postgres_runtime_estimastruct_20260719.md`
4. `CHANGELOG.md`

## 2. Arranque del sistema

### 2.1 Modos de arranque

- `START_UNICA.ps1`
  - levanta FastAPI + Flask
  - modo normal del repo
- `START_POSTGRES_UNICA.ps1`
  - levanta el mismo stack contra PostgreSQL local `estimastruct`
  - launcher preferido para el runtime nuevo

### 2.2 Señales de salud

Backend:

- `GET /health` en `:8002` debe devolver `healthy`

Frontend:

- `GET /health` en `:5000` debe devolver `status=OK`
- `GET /` debe responder la UI
- assets `css` y `js` deben cargar en `200`

## 3. Mapa de la UI

### 3.1 Header

Elementos vivos del header:

- nombre de obra activa
- badge de versión template
- sobrecosto
- botón `Actualizar`
- toggle `Cliente/Desarrollador`
- menú `⚙ Menú`
- botón `Cronograma`
- menú `Exportar`
- dropdown `⚙ Módulos`
- botón `+ Nueva Obra`

### 3.2 Modo cliente vs desarrollador

Modo cliente:

- experiencia resumida
- oculta herramientas de mantenimiento

Modo desarrollador:

- expone bases de datos
- expone menú técnico
- expone toggles de auditoría
- expone herramientas de keynotes y cantidades

## 4. Flujo base del producto

### 4.1 Crear o abrir obra

Contrato:

1. crear obra nueva o seleccionar una existente
2. validar versión template y sobrecosto
3. revisar capítulos y partidas iniciales

Backend real:

- `GET /presupuestos`
- `POST /presupuestos`
- `POST /presupuestos/from-template`
- `GET /presupuestos/{pid}`

### 4.2 Editar presupuesto

Operaciones vivas:

- renombrar obra
- ajustar sobrecosto
- recalcular
- duplicar
- reasignar capítulos
- editar cantidades, factores, unidad, descripción, CSI, Type Mark, color

Routers reales:

- `presupuestos.py`
- `partidas.py`
- `calculos.py`

## 5. Módulo bases de datos

### 5.1 Qué hace

Es el editor y auditor del catálogo vivo de matrices.

Permite:

- cambiar versión
- buscar por CSI / Type Mark / descripción
- abrir matriz
- ver insumos
- editar costos
- agregar, duplicar o eliminar matrices
- guardar y sincronizar
- exportar copia ZIP de BD

### 5.2 Qué archivos mandan

- `backend/routers/bases.py`
- `frontend/js/bases-drawer.js`
- `development/Template2_Updated/`

### 5.3 Regla operativa

No usar Revit como fuente de verdad para una matriz.

Si un elemento de Revit no tiene partida clara:

1. resolver primero la ficha CSI en EstimaStruct
2. luego regenerar keynotes o volver a auditar

## 6. Flujo Revit canónico

### 6.1 Flujo correcto

1. EstimaStruct define catálogo y semántica CSI
2. `generate_keynotes.py` genera keynotes para Revit
3. Revit carga el archivo de keynotes
4. pyRevit exporta schedules
5. EstimaStruct importa cantidades
6. Revit MCP audita modelo vs catálogo
7. EstimaStruct emite reporte y corrige catálogo si hace falta

### 6.2 Herramientas vivas

- `POST /presupuestos/{pid}/scripts/keynotes`
- `GET /scripts/schedules-csvs`
- `POST /presupuestos/{pid}/scripts/import-quantities`
- `POST /presupuestos/{pid}/scripts/import-quantities/report`
- `POST /presupuestos/{pid}/scripts/auditoria`

### 6.3 Scripts reales involucrados

- `backend/scripts_runner/generate_keynotes.py`
- `backend/scripts_runner/import_quantities.py`
- `backend/scripts_runner/revit_dump_snippet.py`
- `backend/scripts_runner/audit_keynotes.py`
- `backend/scripts_runner/run_audit_pipeline.py`
- `backend/scripts_runner/generate_audit_xlsx.py`
- `backend/scripts_runner/sync_audit_colors.py`

### 6.4 Semántica con Revit MCP

Revit MCP se usa para:

- inspeccionar
- auditar
- aplicar correcciones guiadas

No se usa para inventar semántica.

La secuencia correcta es:

- catálogo primero
- modelo después
- auditoría al final

## 7. Flujo de cantidades

### 7.1 Entrada

Origen:

- schedules CSV exportados desde pyRevit/Revit

### 7.2 Proceso

1. detectar export disponible
2. importar cantidades sobre la obra activa
3. recalcular partidas afectadas
4. revisar reporte de importación

### 7.3 Resultado

- `revit_q`
- `cantidad`
- `costo_base`
- `precio_unitario`
- `total`

todo queda actualizado desde el core financiero.

## 8. Módulo diseño estructural de concreto

### 8.1 Qué hace

Gestiona:

- elementos Div 03
- casos de carga
- cálculo
- memoria
- import ETABS concreto
- generación de partidas
- resumen del módulo

### 8.2 Endpoints reales

- `GET /diseno/{pid}/elementos`
- `POST /diseno/{pid}/elementos`
- `POST /diseno/{pid}/importar-bases`
- `GET /diseno/elementos/{eid}`
- `PATCH /diseno/elementos/{eid}`
- `DELETE /diseno/elementos/{eid}`
- `POST /diseno/elementos/{eid}/casos`
- `PATCH /diseno/casos/{cid}`
- `DELETE /diseno/casos/{cid}`
- `POST /diseno/casos/{cid}/calcular`
- `GET /diseno/casos/{cid}/resultado`
- `GET /diseno/casos/{cid}/memoria`
- `POST /diseno/memoria-rapida`
- `POST /diseno/{pid}/import-etabs-concreto`
- `POST /diseno/predimensionar`
- `POST /diseno/casos/{cid}/generar-partidas`
- `GET /diseno/{pid}/resumen`
- `POST /diseno/{pid}/mamposteria`

### 8.3 Operación normal

1. abrir módulo `📐 Diseño`
2. cargar o crear elemento
3. definir material y geometría
4. crear caso
5. calcular
6. revisar memoria
7. generar partidas si aplica

## 9. Módulo acero

### 9.1 Qué hace

Recibe y revisa miembros de acero desde ETABS.

Puede:

- importar resumen ETABS
- importar fuerzas
- generar partidas Div 05
- preparar pedestales / placas base

### 9.2 Endpoints reales

- `POST /diseno/{pid}/import-etabs-acero`
- `POST /diseno/{pid}/import-etabs-acero-fuerzas`
- `POST /diseno/{pid}/acero-generar-partidas`
- `POST /diseno/{pid}/conexion-generar-partida`
- `POST /diseno/{pid}/conexion-import-pyrevit-csv`
- `GET /diseno/{pid}/pedestales-base`
- `POST /diseno/{pid}/placas-base-etabs`

### 9.3 Regla operativa

El módulo acero hoy mezcla revisión y generación de partidas en el mismo perímetro. Eso existe de verdad en código, aunque siga siendo un punto de deuda semántica según auditorías.

## 10. Módulo conexión acero

### 10.1 Qué hace

Resuelve conexiones §J con:

- catálogo
- memoria rápida
- persistencia por presupuesto
- import parcial de fuerzas ETABS

### 10.2 Endpoints reales

- `GET /conexion-acero/catalogo`
- `POST /conexion-acero/memoria-rapida`
- `POST /conexion-acero/import-etabs-fuerzas`
- `POST /conexion-acero/{pid}/conexiones`
- `GET /conexion-acero/{pid}/conexiones`
- `GET /conexion-acero/conexiones/{cid}`
- `PUT /conexion-acero/conexiones/{cid}`
- `POST /conexion-acero/conexiones/{cid}/recalcular`
- `DELETE /conexion-acero/conexiones/{cid}`

### 10.3 Relación con pyRevit / Revit MCP

Semántica correcta:

- EstimaStruct decide ficha y costo
- pyRevit/Revit pueden aportar conteos o contexto geométrico
- el presupuesto final vuelve a EstimaStruct

## 11. Módulo ETABS / sismo

### 11.1 Qué hace

Gestiona:

- contexto sísmico CHOC-08
- tablas
- memoria
- espectro CSV
- import ETABS

### 11.2 Endpoints reales

- `GET /diseno/{pid}/sismo`
- `PUT /diseno/{pid}/sismo`
- `GET /diseno/sismo/tablas`
- `POST /diseno/sismo/memoria`
- `POST /diseno/sismo/espectro-csv`
- `GET /diseno/sismo/procedimiento`
- `POST /diseno/sismo/inferir-suelo`
- `POST /diseno/{pid}/sismo/from-estudio-suelo`
- `POST /diseno/sismo/import-etabs`

## 12. Exportes

### 12.1 XLSX

Menú Exportar:

- presupuesto
- insumos necesarios
- auditoría XLSX
- base de datos completa
- cronograma XLSX

Routers:

- `export.py`
- `cronograma.py`

### 12.2 PDF

Soporta:

- PDF con membrete ConsuConstruct
- PDF con membrete banco
- preview HTML / export HTML

Routers:

- `export_pdf.py`
- `preview_pdf.py`

## 13. Portal

### 13.1 Qué hace

Publica la obra al portal Supabase o sincroniza precios.

### 13.2 Endpoints reales

- `POST /presupuestos/{pid}/publish-supabase`
- `POST /presupuestos/{pid}/sync-precios-supabase`

## 14. Cronograma

### 14.1 Qué hace

Calcula el Gantt y permite overrides de personal:

- especialistas
- ayudantes

### 14.2 Endpoints reales

- `GET /presupuestos/{pid}/cronograma`
- `POST /presupuestos/{pid}/cronograma/personal`
- `GET /presupuestos/{pid}/export-cronograma`

## 15. Backups y migración de base

### 15.1 Operaciones vivas

- exportar ZIP de BD
- reinyectar ZIP
- migrar SQLite a PostgreSQL

### 15.2 Endpoints / scripts

- `GET /db/export-zip`
- `POST /db/import-zip`
- `backend/scripts_runner/migrate_sqlite_to_postgres.py`

## 16. Qué revisar cuando algo falla

### 16.1 Si la UI abre pero no carga datos

Revisar:

- Flask en `:5000`
- FastAPI en `:8002`
- proxy `"/__api__"`
- `GET /health` de ambos lados

### 16.2 Si falla pricing

Revisar:

- `backend/services/pricing.py`
- recalculado de partida
- `sobrecosto`

### 16.3 Si falla Revit

Revisar:

- keynotes generados
- export de schedules
- audit dump
- pipeline de auditoría

### 16.4 Si falla PostgreSQL

Revisar:

- `ESTIMASTRUCT_DATABASE_URL`
- `START_POSTGRES_UNICA.ps1`
- `docs/postgres_runtime_estimastruct_20260719.md`

## 17. Qué no hacer

- no usar `Type Mark` como autoridad semántica
- no dejar que Revit mande el catálogo
- no documentar runtime nuevo solo en changelog
- no volver a usar la SQLite UI como cerebro del producto
- no abrir nuevos manuales paralelos sin recablear la source of truth

## 18. Cierre operativo

Si alguien pregunta "cómo funciona EstimaStruct", la respuesta ya no debe salir de cinco archivos distintos.

Debe salir de:

- `docs/source_of_truth_estimastruct_20260719.md`
- este manual
