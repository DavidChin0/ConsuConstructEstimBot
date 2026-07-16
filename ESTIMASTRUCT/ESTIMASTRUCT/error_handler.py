"""
Error handler para Flask — Log JSON + Notificaciones silenciosas
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import request, jsonify

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG = LOG_DIR / "errors.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("estimastruct")


def log_error(message: str, error_code: str = "UNKNOWN", status_code: int = 500, details: dict = None):
    """Registra error en JSON."""
    timestamp = datetime.utcnow().isoformat()

    error_record = {
        "timestamp": timestamp,
        "error_code": error_code,
        "status_code": status_code,
        "message": message,
        "request": {
            "path": request.path if request else "",
            "method": request.method if request else ""
        },
        "details": details or {}
    }

    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps(error_record, ensure_ascii=False) + "\n")

    logger.error(f"{error_code} | {message}", extra={"error_record": error_record})

    return error_record


def handle_errors(f):
    """Decorador para capturar errores en endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            error_record = log_error(str(e), "VALIDATION_ERROR", 400)
            return jsonify({"error_code": "VALIDATION_ERROR", "message": str(e)}), 400
        except FileNotFoundError as e:
            error_record = log_error(str(e), "NOT_FOUND", 404)
            return jsonify({"error_code": "NOT_FOUND", "message": str(e)}), 404
        except Exception as e:
            error_record = log_error(str(e), "INTERNAL_ERROR", 500)
            return jsonify({"error_code": "INTERNAL_ERROR", "message": "Error interno del servidor"}), 500

    return decorated_function


def register_error_handlers(app):
    """Registra manejadores globales en la app Flask."""

    @app.errorhandler(404)
    def not_found(error):
        error_record = log_error("Recurso no encontrado", "NOT_FOUND", 404)
        return jsonify({"error_code": "NOT_FOUND", "message": "Recurso no encontrado"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        error_record = log_error(str(error), "INTERNAL_ERROR", 500)
        return jsonify({"error_code": "INTERNAL_ERROR", "message": "Error interno del servidor"}), 500
