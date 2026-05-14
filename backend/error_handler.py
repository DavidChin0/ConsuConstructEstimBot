"""
Gestor centralizado de errores — Registro JSON + Notificaciones silenciosas
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
ERROR_LOG = LOG_DIR / "errors.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("estimbot")


class EstimError(Exception):
    """Excepción base personalizada."""
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(EstimError):
    """Error de validación de datos."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "VALIDATION_ERROR", 400, details)


class NotFoundError(EstimError):
    """Recurso no encontrado."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "NOT_FOUND", 404, details)


class ConflictError(EstimError):
    """Conflicto en operación (ej: duplicado)."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "CONFLICT", 409, details)


class DatabaseError(EstimError):
    """Error en operación de BD."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "DATABASE_ERROR", 500, details)


def log_error(
    error: Exception,
    request_path: str = "",
    request_method: str = "",
    user_context: Optional[Dict] = None
) -> Dict[str, Any]:
    """Registra error en JSON y retorna metadata."""
    timestamp = datetime.utcnow().isoformat()

    if isinstance(error, EstimError):
        status_code = error.status_code
        error_code = error.error_code
        message = error.message
        details = error.details
    else:
        status_code = 500
        error_code = error.__class__.__name__
        message = str(error)
        details = {}

    error_record = {
        "timestamp": timestamp,
        "error_code": error_code,
        "status_code": status_code,
        "message": message,
        "request": {
            "path": request_path,
            "method": request_method
        },
        "details": details,
        "user_context": user_context or {}
    }

    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps(error_record, ensure_ascii=False) + "\n")

    logger.error(
        f"{error_code} | {message}",
        extra={"error_record": error_record}
    )

    return error_record


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Manejador para HTTPException (FastAPI built-in)."""
    error_record = log_error(
        Exception(exc.detail),
        request.url.path,
        request.method,
        {"status_code": exc.status_code}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "HTTP_ERROR",
            "message": exc.detail,
            "timestamp": error_record["timestamp"]
        }
    )


async def estim_exception_handler(request: Request, exc: EstimError):
    """Manejador para EstimError personalizado."""
    error_record = log_error(exc, request.url.path, request.method)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "timestamp": error_record["timestamp"]
        }
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """Manejador genérico para excepciones no capturadas."""
    error_record = log_error(exc, request.url.path, request.method)
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "Error interno del servidor",
            "timestamp": error_record["timestamp"]
        }
    )


def register_exception_handlers(app):
    """Registra todos los manejadores en la app FastAPI."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(EstimError, estim_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
