# Sistema Centralizado de Gestión de Errores — EstimBot

## Descripción General

Sistema unificado de captura, registro y monitoreo de errores para:
- **Backend (FastAPI)** — `backend/error_handler.py`
- **Frontend (Flask)** — `ESTIMASTRUCT/error_handler.py`

Registra todos los errores en formato JSON e implementa notificaciones silenciosas sin interrumpir el flujo.

## Arquitectura

### 1. Error Handler (Captura)

#### FastAPI (`backend/error_handler.py`)
- `EstimError` — Excepción base personalizada
- Subclases: `ValidationError`, `NotFoundError`, `ConflictError`, `DatabaseError`
- Exception handlers registrados automáticamente en `main.py`

#### Flask (`ESTIMASTRUCT/error_handler.py`)
- `log_error()` — Registra error en JSON
- `@handle_errors` — Decorador para endpoints
- `register_error_handlers(app)` — Registra handlers globales (404, 500)

### 2. Silent Notifier (Notificaciones)

**Archivo:** `backend/silent_notifier.py`

Monitor en hilo separado que:
- ✓ Lee `logs/errors.jsonl` incrementalmente
- ✓ Dispara handlers sin bloquear
- ✓ Genera resumen de errores (últimos N minutos)
- ✓ Mantiene historial en memoria

**Handlers disponibles:**
```python
notifier.subscribe(notify_file("notifications.log"))      # Archivo
notifier.subscribe(notify_slack(webhook_url))              # Slack (future)
notifier.subscribe(notify_memory(max_size=100))            # Memoria
```

### 3. Logging JSON

**Ubicación:** `logs/errors.jsonl` (una línea por error)

**Formato:**
```json
{
  "timestamp": "2026-05-12T14:23:45.123456",
  "error_code": "VALIDATION_ERROR",
  "status_code": 400,
  "message": "Valor inválido para cantidad",
  "request": {
    "path": "/presupuestos/123/partidas",
    "method": "POST"
  },
  "details": {
    "field": "cantidad",
    "expected": "número positivo"
  },
  "user_context": {}
}
```

## Uso

### Backend (FastAPI)

#### Capturar error personalizado:
```python
from error_handler import ValidationError

@router.post("/presupuestos")
def crear_presupuesto(data: PresupuestoIn):
    if not data.nombre:
        raise ValidationError("Nombre requerido", {"field": "nombre"})
    # ...
```

#### Error automático (404, BD, etc):
```python
from db import get_db
from models import Presupuesto
from error_handler import NotFoundError

@router.get("/presupuestos/{pid}")
def get_presupuesto(pid: str, db: Session = Depends(get_db)):
    obra = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not obra:
        raise NotFoundError(f"Presupuesto {pid} no encontrado")
    return obra
```

### Frontend (Flask)

#### Decorador en endpoint:
```python
from error_handler import handle_errors

@app.route('/api/matrices')
@handle_errors
def api_matrices():
    # Errores capturados automáticamente
    # ValueError → 400 VALIDATION_ERROR
    # FileNotFoundError → 404 NOT_FOUND
    # Exception → 500 INTERNAL_ERROR
    return jsonify(matrices)
```

#### Log manual:
```python
from error_handler import log_error

try:
    # operación
except Exception as e:
    log_error(str(e), "CUSTOM_ERROR", 500, {"context": "info"})
```

## Endpoints de Monitoreo

### FastAPI

```bash
# Resumen de errores (últimos 60 min)
GET http://localhost:8000/diagnostics/errors/summary?minutes=60

# Errores recientes
GET http://localhost:8000/diagnostics/errors/recent?limit=10

# Log de notificaciones
GET http://localhost:8000/diagnostics/notifications/log?limit=20

# Estado del sistema
GET http://localhost:8000/diagnostics/status
```

### Flask

```bash
# Resumen
GET http://localhost:5000/api/errors/summary

# Errores recientes
GET http://localhost:5000/api/errors

# Estado del sistema
GET http://localhost:5000/api/status

# Dashboard interactivo
GET http://localhost:5000/monitoring
```

## Dashboard

Interfaz web en **`http://localhost:5000/monitoring`**:
- Actualiza cada 5s
- Muestra estado del sistema
- Lista errores recientes
- Resumen por tipo de error

## Flujo de Datos

```
Excepción en request
    ↓
error_handler → log_error() → errors.jsonl
    ↓
silent_notifier (cada 30s)
    ↓
Handler 1: notify_file() → notifications.log
Handler 2: notify_memory() → memoria
Handler 3: notify_slack() (future)
    ↓
Endpoints de diagnóstico
    ↓
Dashboard + JSON API
```

## Configuración

### Intervalo de monitoreo
```python
# backend/main.py
from silent_notifier import notifier
notifier = SilentNotifier(check_interval=30)  # segundos
```

### Handlers registrados
```python
# backend/main.py
notifier.subscribe(notify_file("notifications.log"))
notifier.subscribe(notify_memory(max_size=100))
# notifier.subscribe(notify_slack("https://hooks.slack.com/..."))
```

## Testing

### Generar error de prueba (FastAPI):
```bash
curl -X POST http://localhost:8000/presupuestos \
  -H "Content-Type: application/json" \
  -d '{"nombre": ""}'
```

### Generar error de prueba (Flask):
```bash
curl http://localhost:5000/api/matriz/99999
```

### Ver logs:
```bash
# Errores
cat logs/errors.jsonl | tail -5 | jq .

# Notificaciones
cat logs/notifications.log | tail -5 | jq .
```

## Mejoras Futuras

- [ ] Integración Slack
- [ ] Alertas por treshold (ej: 10 errores en 5 min)
- [ ] Métricas Prometheus
- [ ] Muestreo automático (sampling)
- [ ] Rotación de logs

## Archivos Modificados/Creados

**Backend:**
- ✅ `backend/error_handler.py` (nuevo)
- ✅ `backend/silent_notifier.py` (nuevo)
- ✅ `backend/routers/diagnostics.py` (nuevo)
- ✅ `backend/main.py` (integrado)

**Frontend:**
- ✅ `ESTIMASTRUCT/error_handler.py` (nuevo)
- ✅ `ESTIMASTRUCT/app.py` (integrado)
- ✅ `ESTIMASTRUCT/templates/monitoring.html` (nuevo)

**Documentación:**
- ✅ `ERROR_HANDLING_GUIDE.md` (este archivo)
