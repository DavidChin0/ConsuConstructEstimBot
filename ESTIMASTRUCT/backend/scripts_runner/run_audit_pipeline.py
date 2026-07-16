"""Paso 2 del flujo EstimBot: Auditoría CSI completa (Revit vs catálogo V1.2).

Paso 1 es generar keynotes (`generate_keynotes.py`) — genera el .txt que se
carga en Revit. Paso 2 (este módulo) audita el resultado: compara lo que
quedó realmente asignado en Revit contra el catálogo, produce el xlsx
entregable y sincroniza los colores de auditoría en EstimaStruct.

Requiere que el dump de Revit YA esté fresco en
`D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\model_audit_raw.json` — ese dump se
genera corriendo el snippet de `revit_dump_snippet.py` vía MCP
(`execute_revit_code`) dentro de una sesión con Revit abierto. Esta función NO
puede disparar ese paso (necesita acceso vivo a Revit), solo orquesta lo que
sigue después: audit_keynotes.py → generate_audit_xlsx.py → sync_audit_colors.py.

Uso (CLI):
  python run_audit_pipeline.py <obra_id>
"""
import sys
import os
import shutil
import datetime

from backend.scripts_runner.audit_keynotes import audit as run_audit_keynotes
from backend.scripts_runner.generate_audit_xlsx import build as build_xlsx
from backend.scripts_runner.sync_audit_colors import sync as sync_colors, FICHA_PATH, LIVE_PATH

DB_PATH = r"C:\EstimaStruct\data\estimacion.db"


def _backup_before_color_sync():
    """sync_audit_colors pisa color_tipo (destructivo de la semántica previa
    de ese campo) — respaldar catálogo + BD antes de cada corrida, mismo
    patrón manual que se venía haciendo a mano en cada sesión."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backed_up = []
    for path in (FICHA_PATH, LIVE_PATH, DB_PATH):
        if os.path.exists(path):
            dest = f"{path}.bak_auditcolor_{ts}"
            shutil.copy2(path, dest)
            backed_up.append(dest)
    return backed_up


def run_audit_pipeline(obra_id: str) -> dict:
    """Orquesta el Paso 2 completo. Devuelve un dict con el resultado de
    cada sub-paso y la ruta del xlsx final."""
    steps = {}

    try:
        run_audit_keynotes()
        steps["audit_keynotes"] = {"ok": True}
    except Exception as ex:
        steps["audit_keynotes"] = {"ok": False, "error": str(ex)}
        return {"ok": False, "step_failed": "audit_keynotes", "steps": steps}

    try:
        xlsx_path = build_xlsx()
        steps["generate_audit_xlsx"] = {"ok": True, "path": xlsx_path}
    except Exception as ex:
        steps["generate_audit_xlsx"] = {"ok": False, "error": str(ex)}
        return {"ok": False, "step_failed": "generate_audit_xlsx", "steps": steps}

    try:
        backups = _backup_before_color_sync()
        sync_colors(obra_id)
        steps["sync_audit_colors"] = {"ok": True, "backups": backups}
    except Exception as ex:
        steps["sync_audit_colors"] = {"ok": False, "error": str(ex)}
        return {"ok": False, "step_failed": "sync_audit_colors", "steps": steps}

    return {
        "ok": True,
        "xlsx_path": steps["generate_audit_xlsx"]["path"],
        "steps": steps,
        "message": f"Auditoría CSI completa (Paso 2) — xlsx en {steps['generate_audit_xlsx']['path']}",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python run_audit_pipeline.py <obra_id>")
        sys.exit(1)
    res = run_audit_pipeline(sys.argv[1])
    print(res.get("message") or res.get("step_failed"))
    sys.exit(0 if res.get("ok") else 1)
