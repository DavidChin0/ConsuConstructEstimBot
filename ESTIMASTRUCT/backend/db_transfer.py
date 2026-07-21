"""
Helpers de transferencia/export entre la BD primaria actual y snapshots SQLite.

Objetivo:
- PostgreSQL puede ser la verdad primaria.
- EstimaStruct sigue pudiendo exportar/importar snapshots SQLite compatibles
  con el flujo historico.
"""
import os
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select, text

from backend.config import CONFIG
from backend.db import engine
from backend.models import Base

CORE_TABLES = [t.name for t in Base.metadata.sorted_tables]
SQLITE_HEADER = b"SQLite format 3\x00"


def sqlite_url_for(path: str) -> str:
    return "sqlite:///" + path.replace("\\", "/")


def current_db_is_sqlite() -> bool:
    return CONFIG.DB_IS_SQLITE


def sqlite_backup_file(source_path: str, dest_path: str) -> None:
    src = sqlite3.connect(source_path)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def checkpoint_sqlite_file(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def sqlite_table_counts(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        existing = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts = {}
        for table_name in CORE_TABLES:
            counts[table_name] = (
                conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                if table_name in existing else None
            )
        return counts
    finally:
        conn.close()


def sqlite_alembic_version(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "alembic_version" not in tables:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def current_table_counts() -> dict:
    with engine.connect() as conn:
        counts = {}
        for table in Base.metadata.sorted_tables:
            counts[table.name] = conn.execute(
                select(text("count(*)")).select_from(table)
            ).scalar_one()
        return counts


def current_alembic_version():
    with engine.connect() as conn:
        try:
            return conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        except Exception:
            return None


def export_current_database_to_sqlite(dest_path: str) -> None:
    if current_db_is_sqlite():
        sqlite_backup_file(CONFIG.DB_PATH, dest_path)
        return

    sqlite_engine = create_engine(sqlite_url_for(dest_path))
    try:
        Base.metadata.create_all(bind=sqlite_engine)
        with engine.connect() as src, sqlite_engine.begin() as dst:
            for table in Base.metadata.sorted_tables:
                rows = src.execute(select(table)).mappings().all()
                if rows:
                    dst.execute(table.insert(), [dict(r) for r in rows])

            version = current_alembic_version()
            if version:
                dst.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
                dst.execute(text("DELETE FROM alembic_version"))
                dst.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                    {"version_num": version},
                )
    finally:
        sqlite_engine.dispose()


def validate_sqlite_snapshot(db_path: str) -> None:
    with open(db_path, "rb") as fh:
        if fh.read(16) != SQLITE_HEADER:
            raise ValueError("El .db no tiene un header SQLite format 3 valido.")

    conn = sqlite3.connect(db_path)
    try:
        existing = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = [table_name for table_name in CORE_TABLES if table_name not in existing]
        if missing:
            raise ValueError(
                "El .db importado no tiene las tablas nucleo: " + ", ".join(missing)
            )
        quick = conn.execute("PRAGMA quick_check").fetchone()
        if not quick or quick[0] != "ok":
            raise ValueError(f"PRAGMA quick_check fallo en el .db importado: {quick}")
    finally:
        conn.close()


def import_sqlite_snapshot_into_primary(db_path: str) -> None:
    if current_db_is_sqlite():
        raise RuntimeError("Este helper aplica solo cuando la BD primaria no es SQLite.")

    snapshot_engine = create_engine(sqlite_url_for(db_path))
    try:
        Base.metadata.create_all(bind=engine)
        with snapshot_engine.connect() as src, engine.begin() as dst:
            for table in reversed(Base.metadata.sorted_tables):
                dst.execute(table.delete())

            for table in Base.metadata.sorted_tables:
                rows = src.execute(select(table)).mappings().all()
                if rows:
                    dst.execute(table.insert(), [dict(r) for r in rows])

            version = sqlite_alembic_version(db_path)
            if version:
                dst.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS alembic_version "
                        "(version_num VARCHAR(32) NOT NULL)"
                    )
                )
                dst.execute(text("DELETE FROM alembic_version"))
                dst.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                    {"version_num": version},
                )
    finally:
        snapshot_engine.dispose()


def remove_sqlite_sidecars(db_path: str) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = db_path + suffix
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
            except OSError:
                pass


def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
