"""
Router: Copia de seguridad de la BD viva — export/import ZIP.

100% ADITIVO (ver legacy_scripts/LEGACY.md en la raiz del repo). No reemplaza
ningun router ni endpoint existente.

Seguridad de la copia: usa SIEMPRE la API de backup online de sqlite3
(`sqlite3.Connection.backup()`), nunca un file-copy crudo del .db vivo — esa
API es segura mientras el servidor sigue escribiendo en modo WAL (ver
docs/mapa_sql_inyeccion_bd.md, seccion "advertencias").

Tablas nucleo: derivadas dinamicamente de `Base.metadata` (backend/models.py)
en vez de hardcodearlas — si el modelo cambia, este router se mantiene en
sync solo.
"""
import os
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import text

from backend.config import CONFIG
from backend.db import engine, dispose_engine, SessionLocal
from backend.models import Base

router = APIRouter(prefix="/db", tags=["db-backup"])

# Tablas nucleo REALES (excluye sqlite_stat1/sqlite_sequence, internas de
# SQLite, y alembic_version, que se reporta aparte).
CORE_TABLES = sorted(t.name for t in Base.metadata.tables.values())

SQLITE_HEADER = b"SQLite format 3\x00"
BACKUPS_DIR = Path(r"C:\EstimaStruct\backups")


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _sqlite_backup_to(dest_path: str, source_path: str = None) -> None:
    """Copia segura vía API de backup online de sqlite3.Connection.backup().

    Funciona correctamente aunque el origen este en modo WAL con escrituras
    concurrentes (a diferencia de copiar el archivo .db a mano, que puede
    capturar un estado inconsistente si hay un -wal sin checkpoint).
    """
    src = sqlite3.connect(source_path or CONFIG.DB_PATH)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _checkpoint_current() -> None:
    """PRAGMA wal_checkpoint(TRUNCATE) sobre la BD canonica — vacia y trunca
    el -wal antes de respaldar/reemplazar, para dejar el archivo principal
    con el estado completo y los sidecars -wal/-shm minimos."""
    conn = sqlite3.connect(CONFIG.DB_PATH)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _table_counts(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        counts = {}
        for t in CORE_TABLES:
            counts[t] = (
                conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                if t in existing else None
            )
        return counts
    finally:
        conn.close()


def _alembic_version(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "alembic_version" not in tables:
            return None
        row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────
# TAREA 1 — Export ZIP
# ─────────────────────────────────────────────────────────────────────────

@router.get("/export-zip")
def export_zip():
    """Copia segura de la BD viva -> ZIP descargable (estimacion.db + manifest.json)."""
    if not os.path.exists(CONFIG.DB_PATH):
        raise HTTPException(404, f"BD no encontrada en {CONFIG.DB_PATH}")

    tmp_dir = tempfile.mkdtemp(prefix="estimastruct_export_")
    try:
        tmp_db_path = os.path.join(tmp_dir, "estimacion.db")
        _sqlite_backup_to(tmp_db_path)  # backup API online — nunca file-copy crudo

        manifest = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_db_path": CONFIG.DB_PATH,
            "size_bytes": os.path.getsize(tmp_db_path),
            "alembic_version": _alembic_version(tmp_db_path),
            "table_counts": _table_counts(tmp_db_path),
        }
        manifest_path = os.path.join(tmp_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        tmp_zip_path = os.path.join(tmp_dir, "estimastruct_export.zip")
        with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db_path, arcname="estimacion.db")
            zf.write(manifest_path, arcname="manifest.json")
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    fname = f"estimastruct_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return FileResponse(
        tmp_zip_path,
        media_type="application/zip",
        filename=fname,
        background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True),
    )


# ─────────────────────────────────────────────────────────────────────────
# TAREA 2 — Import ZIP
# ─────────────────────────────────────────────────────────────────────────

@router.post("/import-zip")
async def import_zip(
    file: UploadFile = File(...),
    confirm: bool = Query(False, description="Debe ser true para ejecutar el reemplazo de la BD viva"),
):
    """Reemplaza la BD canonica por el .db contenido en el ZIP subido.

    Todas las validaciones corren ANTES de tocar la BD viva. Si cualquiera
    falla -> HTTP 400 con detalle, BD intacta. Solo si TODO pasa y
    confirm=true se ejecuta el reemplazo (con backup previo automatico).
    """
    if not confirm:
        raise HTTPException(400, "confirm=true es obligatorio: este endpoint reemplaza la BD viva.")

    tmp_dir = tempfile.mkdtemp(prefix="estimastruct_import_")
    try:
        upload_path = os.path.join(tmp_dir, "upload.zip")
        with open(upload_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # (1) ZIP valido
        if not zipfile.is_zipfile(upload_path):
            raise HTTPException(400, "El archivo subido no es un ZIP valido.")

        # (2) Contiene un .db
        with zipfile.ZipFile(upload_path) as zf:
            db_members = [n for n in zf.namelist() if n.lower().endswith(".db")]
            if not db_members:
                raise HTTPException(400, "El ZIP no contiene ningun archivo .db.")
            member = next(
                (n for n in db_members if os.path.basename(n) == "estimacion.db"),
                db_members[0],
            )
            extracted_db_path = os.path.join(tmp_dir, "import_candidate.db")
            with zf.open(member) as src, open(extracted_db_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

        # (3) Header "SQLite format 3"
        with open(extracted_db_path, "rb") as f:
            header = f.read(16)
        if header != SQLITE_HEADER:
            raise HTTPException(400, "El .db del ZIP no tiene un header SQLite format 3 valido.")

        # (4) Tablas nucleo reales presentes + (5) integrity check rapido
        conn = sqlite3.connect(extracted_db_path)
        try:
            existing = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            faltantes = [t for t in CORE_TABLES if t not in existing]
            if faltantes:
                raise HTTPException(
                    400,
                    f"El .db importado no tiene las tablas nucleo: {', '.join(faltantes)}",
                )
            quick = conn.execute("PRAGMA quick_check").fetchone()
            if not quick or quick[0] != "ok":
                raise HTTPException(400, f"PRAGMA quick_check fallo en el .db importado: {quick}")
        finally:
            conn.close()

        counts_before = _table_counts(CONFIG.DB_PATH)

        # ── A partir de aqui se toca la BD viva ──────────────────────────
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = str(BACKUPS_DIR / f"estimacion_pre_import_{ts}.db")

        _checkpoint_current()               # flush WAL de la BD actual
        _sqlite_backup_to(backup_path)      # backup del estado actual (online, seguro)

        dispose_engine()                    # libera pool SQLAlchemy sobre el archivo viejo

        for suffix in ("-wal", "-shm"):     # sidecars huerfanos del archivo que se reemplaza
            sidecar = CONFIG.DB_PATH + suffix
            if os.path.exists(sidecar):
                try:
                    os.remove(sidecar)
                except OSError:
                    pass

        shutil.copyfile(extracted_db_path, CONFIG.DB_PATH)   # reemplazo del archivo canonico

        dispose_engine()                    # fuerza reconexion fresca al archivo nuevo

        # SELECT de sanidad a traves del engine real (mismo camino que get_db())
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()

        counts_after = _table_counts(CONFIG.DB_PATH)

        return {
            "status": "ok",
            "message": "BD reemplazada. Backup previo guardado antes del import.",
            "backup_pre_import": backup_path,
            "alembic_version": _alembic_version(CONFIG.DB_PATH),
            "counts_before": counts_before,
            "counts_after": counts_after,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
