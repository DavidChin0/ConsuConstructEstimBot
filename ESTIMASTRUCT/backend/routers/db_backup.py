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
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import text

from backend.config import CONFIG
from backend.db import dispose_engine, SessionLocal
from backend.db_transfer import (
    CORE_TABLES,
    checkpoint_sqlite_file,
    current_alembic_version,
    current_db_is_sqlite,
    current_table_counts,
    ensure_parent_dir,
    export_current_database_to_sqlite,
    import_sqlite_snapshot_into_primary,
    remove_sqlite_sidecars,
    sqlite_alembic_version,
    sqlite_backup_file,
    sqlite_table_counts,
    validate_sqlite_snapshot,
)

router = APIRouter(prefix="/db", tags=["db-backup"])
BACKUPS_DIR = Path(r"C:\EstimaStruct\backups")


# ─────────────────────────────────────────────────────────────────────────
# TAREA 1 — Export ZIP
# ─────────────────────────────────────────────────────────────────────────

@router.get("/export-zip")
def export_zip():
    """Exporta un snapshot SQLite compatible, aunque la BD primaria sea PostgreSQL."""
    if current_db_is_sqlite() and not os.path.exists(CONFIG.DB_PATH):
        raise HTTPException(404, f"BD no encontrada en {CONFIG.DB_PATH}")

    tmp_dir = tempfile.mkdtemp(prefix="estimastruct_export_")
    try:
        tmp_db_path = os.path.join(tmp_dir, CONFIG.SQLITE_EXPORT_NAME)
        export_current_database_to_sqlite(tmp_db_path)

        manifest = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_db_path": CONFIG.DB_PATH if current_db_is_sqlite() else CONFIG.DATABASE_URL,
            "source_database_dialect": CONFIG.DATABASE_DIALECT,
            "export_format": "sqlite",
            "size_bytes": os.path.getsize(tmp_db_path),
            "alembic_version": sqlite_alembic_version(tmp_db_path),
            "table_counts": sqlite_table_counts(tmp_db_path),
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

        try:
            validate_sqlite_snapshot(extracted_db_path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        counts_before = current_table_counts() if not current_db_is_sqlite() else sqlite_table_counts(CONFIG.DB_PATH)

        # ── A partir de aqui se toca la BD viva ──────────────────────────
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = str(BACKUPS_DIR / f"estimacion_pre_import_{ts}.db")
        ensure_parent_dir(backup_path)

        if current_db_is_sqlite():
            checkpoint_sqlite_file(CONFIG.DB_PATH)     # flush WAL de la BD actual
            sqlite_backup_file(CONFIG.DB_PATH, backup_path)

            dispose_engine()                          # libera pool SQLAlchemy sobre el archivo viejo
            remove_sqlite_sidecars(CONFIG.DB_PATH)
            shutil.copyfile(extracted_db_path, CONFIG.DB_PATH)
            dispose_engine()                          # fuerza reconexion fresca al archivo nuevo
        else:
            export_current_database_to_sqlite(backup_path)
            import_sqlite_snapshot_into_primary(extracted_db_path)
            dispose_engine()

        # SELECT de sanidad a traves del engine real (mismo camino que get_db())
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()

        counts_after = current_table_counts() if not current_db_is_sqlite() else sqlite_table_counts(CONFIG.DB_PATH)

        return {
            "status": "ok",
            "message": "BD reemplazada o reinyectada desde snapshot SQLite. Backup previo guardado antes del import.",
            "backup_pre_import": backup_path,
            "database_dialect": CONFIG.DATABASE_DIALECT,
            "sqlite_snapshot_tables": CORE_TABLES,
            "alembic_version": current_alembic_version() if not current_db_is_sqlite() else sqlite_alembic_version(CONFIG.DB_PATH),
            "counts_before": counts_before,
            "counts_after": counts_after,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
