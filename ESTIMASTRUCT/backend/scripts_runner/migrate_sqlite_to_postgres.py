"""
Migra una snapshot SQLite de EstimaStruct hacia la BD primaria configurada.

Uso:
  python -m backend.scripts_runner.migrate_sqlite_to_postgres --sqlite C:\ruta\estimacion.db

Requisitos:
- ESTIMASTRUCT_DATABASE_URL debe apuntar a PostgreSQL.
- El snapshot SQLite debe cumplir el mismo contrato de tablas nucleo que usa
  el import ZIP de la aplicacion.
"""
import argparse
from pathlib import Path

from backend.config import CONFIG
from backend.db import dispose_engine
from backend.db_transfer import (
    current_alembic_version,
    current_db_is_sqlite,
    current_table_counts,
    import_sqlite_snapshot_into_primary,
    validate_sqlite_snapshot,
)


def main():
    parser = argparse.ArgumentParser(description="Migrar snapshot SQLite de EstimaStruct a PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Ruta al archivo estimacion.db a importar")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite).expanduser()
    if not sqlite_path.exists():
        raise SystemExit(f"No existe el snapshot SQLite: {sqlite_path}")

    if current_db_is_sqlite():
        raise SystemExit(
            "ESTIMASTRUCT_DATABASE_URL sigue apuntando a SQLite. "
            "Configura PostgreSQL antes de correr esta migracion."
        )

    validate_sqlite_snapshot(str(sqlite_path))

    print(f"[migrate] target={CONFIG.DATABASE_URL}")
    print(f"[migrate] source={sqlite_path}")
    print("[migrate] importing snapshot into primary database...")
    import_sqlite_snapshot_into_primary(str(sqlite_path))
    dispose_engine()

    print("[migrate] done")
    print(f"[migrate] alembic={current_alembic_version() or '—'}")
    for table_name, count in current_table_counts().items():
        print(f"[migrate] {table_name}: {count}")


if __name__ == "__main__":
    main()
