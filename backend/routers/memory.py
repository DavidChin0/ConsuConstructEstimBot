"""
Endpoints para Technical Memory — Acceso a logs, contextos e historial
"""
from fastapi import APIRouter, Query
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from technical_memory import memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/events")
def get_memory_events(
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    minutes: int = Query(60, ge=1)
):
    """Recupera eventos recientes de la memoria técnica."""
    events = memory.get_events(
        event_type=event_type,
        severity=severity,
        limit=limit,
        minutes=minutes
    )
    return {
        "total": len(events),
        "events": events,
        "filters": {
            "event_type": event_type,
            "severity": severity,
            "limit": limit,
            "minutes": minutes
        }
    }


@router.get("/contexts")
def get_all_contexts():
    """Retorna resumen de contextos almacenados."""
    import sqlite3
    from pathlib import Path

    MEMORY_DB = Path(__file__).parent.parent / "technical_memory.db"
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT context_key, accessed_count, last_accessed, expires_at
    FROM contexts
    ORDER BY last_accessed DESC
    LIMIT 50
    """)

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()

    contexts = [dict(zip(columns, row)) for row in rows]

    return {
        "total": len(contexts),
        "contexts": contexts
    }


@router.get("/contexts/{key}")
def get_context(key: str):
    """Recupera un contexto específico."""
    value = memory.get_context(key)

    if value is None:
        return {"error": "Contexto no encontrado", "key": key}, 404

    return {
        "key": key,
        "value": value
    }


@router.post("/contexts/{key}")
def set_context(key: str, value: dict = None):
    """Establece un contexto."""
    if not value:
        return {"error": "value requerido"}, 400

    success = memory.set_context(key, value)

    return {
        "success": success,
        "key": key,
        "message": "Contexto almacenado" if success else "Error al almacenar contexto"
    }


@router.get("/stats")
def get_memory_stats():
    """Retorna estadísticas de la memoria técnica."""
    return memory.get_memory_stats()


@router.post("/index")
def index_events(batch_size: int = Query(1000, ge=100, le=10000)):
    """Indexa eventos pendientes incrementalmente."""
    result = memory.index_events(batch_size=batch_size)

    return {
        "success": True,
        "indexing_result": result,
        "message": f"Indexados {result['indexed']} eventos"
    }


@router.post("/compress")
def compress_events(days: int = Query(7, ge=1, le=90)):
    """Comprime eventos más antiguos que N días."""
    compressed = memory.compress_old_events(days=days)

    return {
        "success": True,
        "compressed": compressed,
        "message": f"Marcados {compressed} eventos como comprimidos"
    }


@router.post("/cleanup")
def cleanup_contexts():
    """Limpia contextos expirados."""
    deleted = memory.cleanup_expired_contexts()

    return {
        "success": True,
        "deleted": deleted,
        "message": f"Eliminados {deleted} contextos expirados"
    }


@router.post("/vacuum")
def vacuum_database():
    """Compacta la base de datos."""
    success = memory.vacuum()

    return {
        "success": success,
        "message": "Base de datos compactada" if success else "Error al compactar"
    }
