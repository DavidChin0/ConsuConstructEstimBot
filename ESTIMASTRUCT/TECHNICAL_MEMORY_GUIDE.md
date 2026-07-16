# Technical Memory — Base de Datos SQLite para Contextos y Logs

## Descripción General

Sistema de almacenamiento en SQLite para:
- **Logs de eventos** — Auditoría completa de operaciones
- **Contextos** — Snapshots del estado con TTL
- **Métricas** — Agregaciones numéricas
- **Historial de cambios** — Linaje de modificaciones

## Arquitectura

### Base de Datos

**Archivo:** `backend/technical_memory.db` (creado automáticamente)

### Esquema

#### 1. Tabla `events` — Registro de eventos

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    event_type TEXT,              -- "INFO", "ERROR", "DEBUG", "AUDIT"
    source TEXT,                  -- módulo/router origen
    message TEXT,                 -- descripción
    context_json TEXT,            -- contexto adicional (JSON)
    severity TEXT,                -- "INFO", "WARNING", "ERROR", "CRITICAL"
    hash TEXT UNIQUE,             -- deduplicación
    indexed INTEGER,              -- 0 = pendiente, 1 = indexado
    compressed INTEGER            -- 0 = activo, 1 = comprimido
)

-- Índices
idx_events_timestamp   -- búsqueda por tiempo
idx_events_type        -- búsqueda por tipo
idx_events_severity    -- búsqueda por severidad
idx_events_hash        -- deduplicación
```

#### 2. Tabla `contexts` — Snapshots de estado

```sql
CREATE TABLE contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    context_key TEXT UNIQUE,      -- "user:123", "project:abc", etc.
    context_value TEXT,           -- JSON serializado
    expires_at DATETIME,          -- TTL (NULL = sin expiración)
    accessed_count INTEGER,       -- contador de accesos
    last_accessed DATETIME,       -- último acceso
    compressed INTEGER            -- marcado para compresión
)

-- Índices
idx_contexts_key       -- búsqueda por clave
idx_contexts_expires   -- limpieza de expirados
idx_contexts_accessed  -- uso frecuente
```

#### 3. Tabla `metrics` — Datos numéricos agregados

```sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    metric_name TEXT,             -- "requests_per_minute", "error_rate", etc.
    metric_value REAL,
    tags_json TEXT,               -- tags adicionales
    aggregation_window TEXT       -- "5m", "1h", "1d"
)

-- Índices
idx_metrics_name       -- búsqueda por métrica
```

#### 4. Tabla `change_log` — Auditoría de cambios

```sql
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME,
    entity_type TEXT,             -- "presupuesto", "partida", etc.
    entity_id TEXT,               -- ID de la entidad
    operation TEXT,               -- "CREATE", "UPDATE", "DELETE"
    before_json TEXT,             -- estado anterior
    after_json TEXT,              -- estado nuevo
    user_context TEXT             -- quién/qué lo cambió
)

-- Índices
idx_changelog_entity   -- búsqueda por entidad
```

#### 5. Tabla `incremental_index` — Progreso de indexación

```sql
CREATE TABLE incremental_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indexed_date DATETIME,
    table_name TEXT,              -- tabla indexada
    last_id INTEGER,              -- último ID procesado
    record_count INTEGER,         -- registros procesados
    status TEXT                   -- "ACTIVE", "PAUSED"
)
```

## Uso

### 1. Registro de Eventos

```python
from technical_memory import memory

# Evento simple
memory.log_event(
    event_type="AUDIT",
    message="Presupuesto creado",
    source="presupuestos.router",
    severity="INFO",
    context={"presupuesto_id": "123", "user": "admin"}
)

# Evento de error
memory.log_event(
    event_type="ERROR",
    message="Falló cálculo de precios",
    source="calculos.router",
    severity="ERROR",
    context={"partida_id": "456", "error": "ValueError"}
)
```

### 2. Contextos (Snapshots)

```python
# Guardar contexto sin expiración
memory.set_context(
    key="presupuesto:123:state",
    value={
        "nombre": "Proyecto A",
        "cliente": "Cliente X",
        "total": 50000.00
    }
)

# Guardar contexto con TTL (5 minutos)
memory.set_context(
    key="cache:calculations",
    value={"precios": {...}},
    ttl_minutes=5
)

# Recuperar contexto (y registra acceso)
datos = memory.get_context("presupuesto:123:state")
print(datos["total"])
```

### 3. Estadísticas

```python
# Obtener estadísticas completas
stats = memory.get_memory_stats()
print(f"Total eventos: {stats['total_events']}")
print(f"Eventos pendientes: {stats['pending_events']}")
print(f"Tamaño BD: {stats['database_size_mb']:.2f} MB")
```

## API HTTP

### GET /memory/events

Recupera eventos recientes.

**Query params:**
- `event_type` (opt) — filtrar por tipo
- `severity` (opt) — "INFO", "WARNING", "ERROR", "CRITICAL"
- `limit` (opt, default=100) — máx 500
- `minutes` (opt, default=60) — últimos N minutos

```bash
curl "http://localhost:8000/memory/events?severity=ERROR&limit=50"
```

### GET /memory/contexts

Lista contextos almacenados.

```bash
curl "http://localhost:8000/memory/contexts"
```

### GET /memory/contexts/{key}

Recupera contexto específico.

```bash
curl "http://localhost:8000/memory/contexts/presupuesto:123:state"
```

### POST /memory/contexts/{key}

Establece contexto.

```bash
curl -X POST "http://localhost:8000/memory/contexts/cache:mykey" \
  -H "Content-Type: application/json" \
  -d '{"value": {"data": "test"}}'
```

### GET /memory/stats

Estadísticas completas de la BD.

```bash
curl "http://localhost:8000/memory/stats"
```

Response:
```json
{
  "total_events": 5432,
  "pending_events": 123,
  "compressed_events": 1000,
  "total_contexts": 45,
  "ttl_contexts": 12,
  "total_context_accesses": 28934,
  "total_changes": 892,
  "database_size_mb": 2.45
}
```

### POST /memory/index

Indexa eventos pendientes (incremental).

**Query params:**
- `batch_size` (opt, default=1000, max=10000)

```bash
curl -X POST "http://localhost:8000/memory/index?batch_size=2000"
```

Response:
```json
{
  "success": true,
  "indexing_result": {
    "indexed": 2000,
    "pending": 3432,
    "batch_size": 2000
  }
}
```

### POST /memory/compress

Marca eventos antiguos como comprimidos.

**Query params:**
- `days` (opt, default=7, max=90)

```bash
curl -X POST "http://localhost:8000/memory/compress?days=30"
```

### POST /memory/cleanup

Elimina contextos expirados.

```bash
curl -X POST "http://localhost:8000/memory/cleanup"
```

### POST /memory/vacuum

Compacta la BD (elimina espacios muertos).

```bash
curl -X POST "http://localhost:8000/memory/vacuum"
```

## Flujo de Indexación Incremental

```
Evento nuevo
    ↓
INSERT INTO events ... (indexed=0)
    ↓
POST /memory/index (batch_size=1000)
    ↓
UPDATE events SET indexed=1 LIMIT 1000
    ↓
INSERT INTO incremental_index (record_count=1000)
    ↓
Siguiente batch (si hay pending)
```

## Compresión y Limpieza

### Estrategia

1. **Active Zone** (últimos 7 días) — indexados, accesibles, búsquedas rápidas
2. **Archive Zone** (7-90 días) — comprimidos, accesibles pero lentos
3. **Purge Zone** (>90 días) — eliminados

### Operaciones de Mantenimiento

```bash
# Indexar pendientes (diario)
curl -X POST http://localhost:8000/memory/index?batch_size=5000

# Comprimir eventos > 7 días (semanal)
curl -X POST http://localhost:8000/memory/compress?days=7

# Limpiar contextos expirados (horario)
curl -X POST http://localhost:8000/memory/cleanup

# Compactar BD (semanal)
curl -X POST http://localhost:8000/memory/vacuum
```

## Ejemplos de Uso Completo

### Rastrear cambios de presupuesto

```python
from technical_memory import memory

# Al crear presupuesto
memory.log_event(
    event_type="AUDIT",
    message="Presupuesto creado",
    source="presupuestos",
    context={
        "presupuesto_id": "p123",
        "nombre": "Proyecto A",
        "cliente": "Cliente X"
    }
)

# Almacenar snapshot
memory.set_context(
    key="presupuesto:p123",
    value=presupuesto_data
)

# Al modificar
memory.log_event(
    event_type="AUDIT",
    message="Presupuesto modificado",
    source="presupuestos",
    context={
        "presupuesto_id": "p123",
        "cambios": ["nombre", "cliente"]
    }
)
```

### Caché de cálculos

```python
# Recuperar de caché o calcular
cache_key = "cache:precios:v1.0"
precios = memory.get_context(cache_key)

if not precios:
    precios = calcular_precios()
    memory.set_context(cache_key, precios, ttl_minutes=30)
```

### Monitoreo de errores

```python
# Buscar errores del último día
errors = memory.get_events(
    severity="ERROR",
    limit=100,
    minutes=1440  # 24 horas
)

for error in errors:
    print(f"{error['timestamp']} — {error['message']}")
```

## Rendimiento

### Tamaños típicos

- **100K eventos**: ~5-10 MB
- **1K contextos**: ~1-2 MB
- **Indexación**: ~1000 registros/segundo

### Optimización

1. **Indexación incremental** — procesar en batches (no bloquea)
2. **Compresión** — marcación sin eliminación (reversible)
3. **Limpieza** — solo contextos expirados (automático)
4. **Vacuum** — después de limpieza masiva

## Archivos Creados

- ✅ `backend/technical_memory.py` — gestor principal
- ✅ `backend/routers/memory.py` — API endpoints
- ✅ `TECHNICAL_MEMORY_GUIDE.md` — este documento

## Próximas Mejoras

- [ ] Replicación a S3 para backup
- [ ] Búsqueda full-text (FTS5)
- [ ] Métricas Prometheus
- [ ] Dashboard de memoria
- [ ] Compresión ZSTD de eventos antiguos
