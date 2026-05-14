"""
Endpoints de diagnóstico — Monitoreo de errores y estado del sistema
"""
from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

LOGS_DIR = Path(__file__).parent.parent / "logs"


@router.get("/errors/summary")
def error_summary(minutes: int = 60):
    """Retorna resumen de errores últimos N minutos."""
    from silent_notifier import notifier
    return notifier.get_summary(minutes)


@router.get("/errors/recent")
def recent_errors(limit: int = 10):
    """Retorna últimos N errores registrados."""
    error_log = LOGS_DIR / "errors.jsonl"
    if not error_log.exists():
        return {"errors": []}

    errors = []
    try:
        with open(error_log, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        errors.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        errors.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"errors": errors[:limit], "total": len(errors)}

    except Exception as e:
        return {"error": str(e), "errors": []}


@router.get("/notifications/log")
def notification_log(limit: int = 20):
    """Retorna log de notificaciones silenciosas."""
    notif_log = LOGS_DIR / "notifications.log"
    if not notif_log.exists():
        return {"notifications": []}

    notifications = []
    try:
        with open(notif_log, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        notifications.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        notifications.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"notifications": notifications[:limit], "total": len(notifications)}

    except Exception as e:
        return {"error": str(e), "notifications": []}


@router.get("/status")
def system_status():
    """Estado general del sistema."""
    from db import SessionLocal
    from models import Presupuesto

    db = SessionLocal()
    try:
        total_presupuestos = db.query(Presupuesto).count()
        templates = db.query(Presupuesto).filter(Presupuesto.es_template == True).count()

        return {
            "status": "ok",
            "database": {
                "total_presupuestos": total_presupuestos,
                "templates": templates
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
