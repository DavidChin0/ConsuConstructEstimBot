"""
Configuracion centralizada de rutas — EstimaStruct.

FASE 0: DB_PATH saca la BD viva de OneDrive (evita corrupcion por sync).
Los demas paths quedan listos para migrar los routers en FASE 1
(hoy varios estan hardcodeados con r"D:\OneDrive\...").

Todos overridables por variable de entorno.
"""
import os
from pathlib import Path
from sqlalchemy.engine import make_url

_BACKEND = Path(__file__).resolve().parent


def _default_database_url() -> str:
    """Canon ADR-018 (2026-10-04, backend unico): Postgres `estimastruct` es la
    UNICA fuente. Si ESTIMASTRUCT_DATABASE_URL no viene del launcher
    (START_POSTGRES_UNICA.ps1) — p.ej. uvicorn lanzado por estimastruct_backend_ensure
    o a mano — se arma desde D:\\Secrets\\postgres_credentials.txt en vez de caer
    en silencio a la SQLite legacy vacia. SQLite solo con ESTIMASTRUCT_ALLOW_SQLITE=1."""
    if os.getenv("ESTIMASTRUCT_ALLOW_SQLITE", "").strip() == "1":
        return "sqlite:///" + os.getenv("ESTIMA_DB_PATH", r"D:\EstimaStruct\data\estimacion.db").replace("\\", "/")
    from urllib.parse import quote_plus
    secret = Path(os.getenv("ESTIMASTRUCT_PG_SECRET_FILE", r"D:\Secrets\postgres_credentials.txt"))
    kv = {}
    for line in secret.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    if not kv.get("password"):
        raise RuntimeError(f"EstimaStruct: sin password en {secret}; canon = Postgres estimastruct")
    role = kv.get("role") or "postgres"
    return f"postgresql+psycopg://{role}:{quote_plus(kv['password'])}@127.0.0.1:5432/estimastruct"


class CONFIG:
    PROJECT_ROOT = _BACKEND.parent
    PROJECT_NAME = "EstimaStruct"
    RELEASE_VERSION = "v1.3"
    VERSIONED_DB_PATH = PROJECT_ROOT / "data" / "v1.3" / "estimacion.db"  # legacy; canon = Postgres
    CANONICAL_ROOT = os.getenv("ESTIMASTRUCT_CANONICAL_ROOT", str(PROJECT_ROOT))

    # BD viva FUERA de OneDrive (FASE 0). Local NTFS => WAL seguro.
    # FASE 0b (2026-08-17): movida de C:\EstimaStruct a D:\EstimaStruct para
    # sobrevivir la reinstalacion minimalista de Windows (C: se wipea, D: no).
    DB_PATH     = os.getenv("ESTIMA_DB_PATH",     r"D:\EstimaStruct\data\estimacion.db")
    DATABASE_URL = os.getenv("ESTIMASTRUCT_DATABASE_URL") or _default_database_url()
    DATABASE_DIALECT = make_url(DATABASE_URL).get_backend_name()
    DB_IS_SQLITE = DATABASE_DIALECT == "sqlite"
    AUTO_CREATE_SCHEMA = os.getenv(
        "ESTIMASTRUCT_AUTO_CREATE_SCHEMA",
        "true" if DB_IS_SQLITE else "false",
    ).strip().lower() in {"1", "true", "yes", "on"}
    UI_COMPAT_DB_PATH = os.getenv("ESTIMASTRUCT_UI_DB", r"D:\EstimaStruct\data\estimastruct.db")
    SQLITE_EXPORT_NAME = os.getenv("ESTIMASTRUCT_SQLITE_EXPORT_NAME", "estimacion.db")

    # Valor "para el Banco" por obra (info hardcodeada de EstimaStruct; se
    # persiste al generar el PDF banco y luego migrara al Supabase del cliente).
    VALORES_BANCO_JSON = os.getenv(
        "ESTIMA_VALORES_BANCO_JSON",
        os.path.join(os.path.dirname(os.getenv("ESTIMA_DB_PATH", r"D:\EstimaStruct\data\estimacion.db")),
                     "valores_banco.json"))

    # Catalogos / archivos maestros (migracion de routers => FASE 1)
    FICHAS_DIR  = os.getenv("ESTIMA_FICHAS_DIR",  str(_BACKEND.parent / "development" / "Template2_Updated"))
    UPDATER_DIR = os.getenv("ESTIMA_UPDATER_DIR", r"D:\OneDrive\Bots\Estimbot\MasterFiles\Updater")
    OPUS_XLSX   = os.getenv("ESTIMA_OPUS_XLSX",   r"D:\OneDrive\Bots\Estimbot\MasterFiles\BaseDatosOpus2026.xlsx")
    EXPORTS_DIR = os.getenv("ESTIMA_EXPORTS_DIR", r"D:\OneDrive\Bots\Estimbot\EXPORTS")
    SCHEDULES_DIR = os.getenv("ESTIMA_SCHEDULES_DIR", os.path.join(EXPORTS_DIR, "S5_schedules"))
    KEYNOTES_DIR  = os.getenv("ESTIMA_KEYNOTES_DIR",  os.path.join(EXPORTS_DIR, "S1_keynotes"))

    # Locales al backend (file-relative, ya robustos)
    LOGS_DIR    = _BACKEND / "logs"
    MEMORY_DB   = _BACKEND / "technical_memory.db"
