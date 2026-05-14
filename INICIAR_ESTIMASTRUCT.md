# Iniciar ESTIMASTRUCT — Guía Rápida

## Problema
Frontend carga pero vacío. Causa: backend FastAPI no corre en puerto 8000.

## Solución: Levantar AMBOS servidores

### Opción 1: DOS ventanas de terminal (RECOMENDADO)

**Terminal 1 — Backend FastAPI (puerto 8000):**
```bash
cd D:\OneDrive\Bots\Estimbot\Estimacion\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend Flask (puerto 5000):**
```bash
cd D:\OneDrive\Bots\Estimbot\Estimacion\ESTIMASTRUCT
python app.py
```

Luego acceder a: **http://localhost:5000/**

---

### Opción 2: Scripts batch (Windows)

**Terminal 1:**
```bash
D:\OneDrive\Bots\Estimbot\Estimacion\RUN_BACKEND.bat
```

**Terminal 2:**
```bash
D:\OneDrive\Bots\Estimbot\Estimacion\ESTIMASTRUCT.bat
```

---

## Qué hace cada servidor

| Servidor | Puerto | Función |
|----------|--------|---------|
| **Frontend Flask** | 5000 | Sirve HTML/CSS/JS (ESTIMASTRUCT) |
| **Backend FastAPI** | 8000 | APIs de presupuestos (`/presupuestos`, `/partidas`, etc.) |

El frontend (app.js) espera backend en `http://localhost:8000`.

---

## Validación

Ambos deben estar corriendo:

```bash
# Terminal 1 - prueba backend
curl http://localhost:8000/

# Terminal 2 - prueba frontend
curl http://localhost:5000/
```

Luego abrir navegador: **http://localhost:5000/**

---

## Si sigue vacío

1. Abre Developer Console (F12 → Console)
2. Busca errores de red o JavaScript
3. Verifica que ambos servidores estén corriendo (`netstat -ano`)
