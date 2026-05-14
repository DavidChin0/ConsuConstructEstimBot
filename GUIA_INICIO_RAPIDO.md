# Guía Rápida — ESTIMASTRUCT

## Inicio en 3 pasos

### 1️⃣ Doble-clic en Desktop → `ESTIMASTRUCT.lnk`

Esto levanta:
- **Frontend** (Flask) en `http://localhost:5000/`
- **Backend** (FastAPI) en `http://localhost:8000/`

Con logs en vivo de ambos servidores.

### 2️⃣ Abrir navegador

```
http://localhost:5000/
```

### 3️⃣ Debería ver:
- Header con obra-titulo, botones (Nueva Obra, Exportar, etc.)
- Sidebar vacío al inicio (espera a crear/cargar proyectos)
- Tabla presupuesto vacía

---

## Si ves "Cargando..." o pantalla vacía

### Problema: "failed to fetch"

**Causa:** Backend no responde

**Soluciones:**

#### Opción A: Verificar que ambos servidores corren
```bash
# En otra terminal, ejecuta:
netstat -ano | findstr ":5000\|:8000"
```

Debería mostrar DOS líneas con `LISTENING`:
- `LISTENING ... 5000` (Flask)
- `LISTENING ... 8000` (FastAPI)

Si no aparecen, el script no se ejecutó correctamente.

#### Opción B: Abrir Developer Console (F12 → Console)

Busca errores como:
- `Failed to fetch from http://localhost:8000`
- `CORS error`
- `Connection refused`

#### Opción C: Probar Backend directamente
```bash
# En navegador:
http://localhost:8000/

# Debería responder:
# {"status":"ok","app":"Estimacion API v1.0"}
```

---

## Cambios automáticos (Hot Reload)

### Frontend (Flask)
- Editar archivos en `D:\OneDrive\Bots\Estimbot\Estimacion\ESTIMASTRUCT\`
- **Se recargan automáticamente** (Flask --reload)

### Backend (FastAPI)
- Editar archivos en `D:\OneDrive\Bots\Estimbot\Estimacion\backend\`
- **Se recargan automáticamente** (uvicorn --reload)

### Base de datos
- **NO se recargan** — cambios en BD requieren reinicio

---

## Estructura

```
ESTIMASTRUCT/
├── templates/
│   └── index.html          ← Frontend HTML
├── app.py                  ← Servidor Flask (5000)
└── estimastruct.db         ← Base de datos SQLite

backend/
├── main.py                 ← Servidor FastAPI (8000)
├── models.py               ← Modelos SQLAlchemy
├── routers/
│   ├── presupuestos.py     ← API /presupuestos
│   ├── partidas.py         ← API /partidas
│   └── ...
└── technical_memory.db     ← Logs y memoria técnica

frontend/
├── js/
│   └── app.js              ← App JavaScript
└── css/
    └── style.css           ← Estilos
```

---

## Datos

**Base de datos:** `ESTIMASTRUCT/estimastruct.db`
- 277 fichas/actividades (obras/presupuestos)
- 1957 recursos (insumos)
- 16 unidades de medida

---

## Logs útiles

### Backend error
Look in logs en la terminal. Busca líneas con `ERROR` en rojo.

### Frontend error
F12 → Console → busca líneas rojas

---

## Comandos útiles

```bash
# Matar procesos en puertos
taskkill /F /IM python.exe  # Mata todos los Python
netstat -ano | findstr ":5000\|:8000"  # Muestra qué corre en esos puertos

# Acceso directo lanzar manual
D:\OneDrive\Bots\Estimbot\Estimacion\START_DEV.bat

# O PowerShell directo
cd D:\OneDrive\Bots\Estimbot\Estimacion
.\START_ESTIMASTRUCT.ps1
```

---

## Estado = ✅ LISTO

- Frontend HTML restaurado
- Backend APIs funcionales
- Hot reload activo
- Logs interleaved en una ventana
- Acceso directo en Desktop
