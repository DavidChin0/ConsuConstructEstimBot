"""
Configuracion centralizada de rutas — EstimaStruct.

FASE 0: DB_PATH saca la BD viva de OneDrive (evita corrupcion por sync).
Los demas paths quedan listos para migrar los routers en FASE 1
(hoy varios estan hardcodeados con r"D:\OneDrive\...").

Todos overridables por variable de entorno.
"""
import os
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent

class CONFIG:
    # BD viva FUERA de OneDrive (FASE 0). Local NTFS => WAL seguro.
    DB_PATH     = os.getenv("ESTIMA_DB_PATH",     r"C:\EstimaStruct\data\estimacion.db")

    # Valor "para el Banco" por obra (info hardcodeada de EstimaStruct; se
    # persiste al generar el PDF banco y luego migrara al Supabase del cliente).
    VALORES_BANCO_JSON = os.getenv(
        "ESTIMA_VALORES_BANCO_JSON",
        os.path.join(os.path.dirname(os.getenv("ESTIMA_DB_PATH", r"C:\EstimaStruct\data\estimacion.db")),
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
