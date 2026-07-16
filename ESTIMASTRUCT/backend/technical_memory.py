"""
Technical Memory — Almacenamiento en SQLite para logs, contextos y datos históricos
"""
import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

MEMORY_DB = Path(__file__).parent / "technical_memory.db"


def init_memory_db():
    """Inicializa esquema de Technical Memory."""
    conn = sqlite3.connect(MEMORY_DB)
    cursor = conn.cursor()

    # Tabla de eventos (logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT NOT NULL,
        source TEXT,
        message TEXT,
        context_json TEXT,
        severity TEXT DEFAULT 'INFO',
        hash TEXT UNIQUE,
        indexed INTEGER DEFAULT 0,
        compressed INTEGER DEFAULT 0
    )
    """)

    # Índices para eventos
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_timestamp
    ON events(timestamp DESC)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_severity
    ON events(severity)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_hash
    ON events(hash)
    """)

    # Tabla de contextos (snapshots del estado)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contexts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        context_key TEXT NOT NULL UNIQUE,
        context_value TEXT,
        expires_at DATETIME,
        accessed_count INTEGER DEFAULT 0,
        last_accessed DATETIME,
        compressed INTEGER DEFAULT 0
    )
    """)

    # Índices para contextos
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_contexts_key
    ON contexts(context_key)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_contexts_expires
    ON contexts(expires_at)
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_contexts_accessed
    ON contexts(last_accessed DESC)
    """)

    # Tabla de métricas agregadas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        metric_name TEXT NOT NULL,
        metric_value REAL,
        tags_json TEXT,
        aggregation_window TEXT
    )
    """)

    # Índices para métricas
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_metrics_name
    ON metrics(metric_name, timestamp DESC)
    """)

    # Tabla de linaje de cambios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS change_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        operation TEXT,
        before_json TEXT,
        after_json TEXT,
        user_context TEXT
    )
    """)

    # Índices para change_log
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_changelog_entity
    ON change_log(entity_type, entity_id, timestamp DESC)
    """)

    # Tabla de índice incremental
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incremental_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        indexed_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        table_name TEXT NOT NULL,
        last_id INTEGER,
        record_count INTEGER,
        status TEXT DEFAULT 'ACTIVE'
    )
    """)

    conn.commit()
    conn.close()


class TechnicalMemory:
    """Gestor de memoria técnica en SQLite."""

    def __init__(self):
        init_memory_db()

    def _get_hash(self, data: str) -> str:
        """Genera hash único para deduplicación."""
        return hashlib.md5(data.encode()).hexdigest()

    # ─── EVENTOS ──────────────────────────────────────────────────────────

    def log_event(
        self,
        event_type: str,
        message: str,
        source: str = "",
        context: Optional[Dict] = None,
        severity: str = "INFO"
    ) -> int:
        """Registra evento con contexto."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        context_json = json.dumps(context or {})
        event_hash = self._get_hash(f"{event_type}:{message}:{datetime.utcnow().isoformat()}")

        try:
            cursor.execute("""
            INSERT INTO events (event_type, source, message, context_json, severity, hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (event_type, source, message, context_json, severity, event_hash))

            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return -1
        finally:
            conn.close()

    def get_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
        minutes: int = 60
    ) -> List[Dict]:
        """Recupera eventos recientes."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        cutoff = datetime.utcnow() - timedelta(minutes=minutes)

        query = "SELECT * FROM events WHERE timestamp > ? AND indexed = 0"
        params = [cutoff.isoformat()]

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    # ─── CONTEXTOS ────────────────────────────────────────────────────────

    def set_context(
        self,
        key: str,
        value: Any,
        ttl_minutes: Optional[int] = None
    ) -> bool:
        """Guarda contexto con TTL opcional."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        value_json = json.dumps(value)
        expires_at = None
        if ttl_minutes:
            expires_at = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).isoformat()

        try:
            cursor.execute("""
            INSERT OR REPLACE INTO contexts (context_key, context_value, expires_at)
            VALUES (?, ?, ?)
            """, (key, value_json, expires_at))

            conn.commit()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    def get_context(self, key: str) -> Optional[Any]:
        """Recupera contexto y actualiza accessed_count."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        now = datetime.utcnow()
        cursor.execute("""
        SELECT context_value, expires_at FROM contexts
        WHERE context_key = ?
        """, (key,))

        row = cursor.fetchone()

        if row and (not row[1] or datetime.fromisoformat(row[1]) > now):
            cursor.execute("""
            UPDATE contexts
            SET accessed_count = accessed_count + 1, last_accessed = CURRENT_TIMESTAMP
            WHERE context_key = ?
            """, (key,))
            conn.commit()
            conn.close()

            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]

        if row and row[1] and datetime.fromisoformat(row[1]) <= now:
            cursor.execute("DELETE FROM contexts WHERE context_key = ?", (key,))
            conn.commit()

        conn.close()
        return None

    def cleanup_expired_contexts(self) -> int:
        """Limpia contextos expirados."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        cursor.execute("""
        DELETE FROM contexts
        WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
        """)

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted

    # ─── INDEXACIÓN INCREMENTAL ───────────────────────────────────────────

    def index_events(self, batch_size: int = 1000) -> Dict[str, Any]:
        """Indexa eventos no procesados incrementalmente."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT COUNT(*) FROM events WHERE indexed = 0
        """)
        total_pending = cursor.fetchone()[0]

        if total_pending == 0:
            conn.close()
            return {"indexed": 0, "pending": 0}

        # Indexar en batches
        cursor.execute("""
        UPDATE events SET indexed = 1
        WHERE id IN (
            SELECT id FROM events WHERE indexed = 0 LIMIT ?
        )
        """, (batch_size,))

        indexed = cursor.rowcount
        conn.commit()

        # Registrar progreso
        cursor.execute("""
        INSERT INTO incremental_index (table_name, last_id, record_count)
        SELECT 'events', COALESCE(MAX(id), 0), COUNT(*) FROM events
        WHERE indexed = 1
        """)
        conn.commit()
        conn.close()

        return {
            "indexed": indexed,
            "pending": total_pending - indexed,
            "batch_size": batch_size
        }

    # ─── COMPRESIÓN Y LIMPIEZA ────────────────────────────────────────────

    def compress_old_events(self, days: int = 7) -> int:
        """Marca eventos antiguos como comprimidos (no borrar)."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute("""
        UPDATE events SET compressed = 1
        WHERE timestamp < ? AND compressed = 0
        """, (cutoff,))

        compressed = cursor.rowcount
        conn.commit()
        conn.close()

        return compressed

    def get_memory_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas de la memoria técnica."""
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()

        stats = {}

        cursor.execute("SELECT COUNT(*) FROM events")
        stats["total_events"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM events WHERE indexed = 0")
        stats["pending_events"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM events WHERE compressed = 1")
        stats["compressed_events"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM contexts")
        stats["total_contexts"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM contexts WHERE expires_at IS NOT NULL")
        stats["ttl_contexts"] = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(accessed_count) FROM contexts")
        sum_accessed = cursor.fetchone()[0]
        stats["total_context_accesses"] = sum_accessed or 0

        cursor.execute("SELECT COUNT(*) FROM change_log")
        stats["total_changes"] = cursor.fetchone()[0]

        # Tamaño de BD
        db_size = MEMORY_DB.stat().st_size if MEMORY_DB.exists() else 0
        stats["database_size_mb"] = db_size / (1024 * 1024)

        conn.close()

        return stats

    def vacuum(self) -> bool:
        """Compacta BD después de limpieza."""
        try:
            conn = sqlite3.connect(MEMORY_DB)
            conn.execute("VACUUM")
            conn.close()
            return True
        except Exception:
            return False


# Instancia global
memory = TechnicalMemory()
