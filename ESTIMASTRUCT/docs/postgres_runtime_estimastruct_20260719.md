> [!CONTEXT]
> Runtime PostgreSQL primario de EstimaStruct con compatibilidad explícita de snapshot SQLite.

# EstimaStruct — PostgreSQL primario + SQLite de compatibilidad

## Estado al 2026-07-19

- BD primaria soportada y verificada: `PostgreSQL 16`
- BD legacy todavía disponible: `C:\EstimaStruct\data\estimacion.db`
- Snapshot de compatibilidad: export/import `.db` SQLite desde `/db/export-zip` y `/db/import-zip`
- UI intacta: sigue abriendo desde el repo con `ESTIMASTRUCT/app.py` y hablando same-origin al backend

## Variables canónicas

- `ESTIMASTRUCT_DATABASE_URL`
- `ESTIMASTRUCT_AUTO_CREATE_SCHEMA`
- `ESTIMASTRUCT_CANONICAL_ROOT`
- `ESTIMASTRUCT_UI_DB` solo para compatibilidad de dashboard legacy

## Launchers

- `START_UNICA.ps1`
  - default seguro
  - puede arrancar con SQLite o PostgreSQL según `ESTIMASTRUCT_DATABASE_URL`
- `START_POSTGRES_UNICA.ps1`
  - wrapper local para esta máquina
  - lee `D:\Secrets\postgres_credentials.txt`
  - apunta a `postgresql+psycopg://postgres@127.0.0.1:5432/estimastruct`

## Migración operativa

- Script CLI:
  - `python -m backend.scripts_runner.migrate_sqlite_to_postgres --sqlite C:\EstimaStruct\data\estimacion.db`
- Helper interno:
  - `backend/db_transfer.py`

## Verificación ejecutada el 2026-07-19

- Migración SQLite → PostgreSQL ejecutada sobre la BD `estimastruct`
- Conteos verificados post-migración:
  - `presupuesto = 6`
  - `partida = 1137`
  - `insumo_partida = 7340`
- Runtime verificado:
  - `GET /health` backend = `healthy`
  - UI Flask = `200`
  - `GET /presupuestos` = `6` obras
  - `GET /db/export-zip` genera snapshot SQLite válido
  - `POST /db/import-zip?confirm=true` reinyecta el snapshot sobre PostgreSQL sin perder conteos

## Enlaces semánticos

- Pipeline EstimBot: `D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\estimbot\reference\pipeline_estimbot_actual.md`
- Proyecto EstimBot en vault: `D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\estimbot\README.md`
- Runbook general PostgreSQL: `D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\postgres-migration\postgres_migration_runbook.md`

## Regla actual

PostgreSQL puede ser la verdad primaria de EstimaStruct.

SQLite ya no es requisito para operar el core, pero sigue siendo formato de compatibilidad para:

- backup
- export
- import
- handoff local
