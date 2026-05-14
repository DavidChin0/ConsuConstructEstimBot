Paquete ESTIMBOT de Consultorias de Construcción S. de R.L. 
ConsuConstruct.com By D. Chinchilla

Este paquete incluye dependencias totalmente OPEN SOURCE para la estimación y análsis Estructural

# EstimaStruct

EstimaStruct es una plataforma open source para estimación de costos, análisis estructural y detalle técnico.

Funciona como puente entre Revit 2027, schedules exportados desde pyRevit y el módulo de análisis de precios dentro del ecosistema Estimbot.

## Stack

- Backend: FastAPI + SQLAlchemy + SQLite
- Frontend: HTML, CSS y Vanilla JavaScript
- Interfaz legacy/compatibilidad: Flask
- Importación de datos: Excel y CSV

## Requisitos

- Python 3.10 o superior
- `pip`
- Windows 10/11 recomendado para los scripts de arranque incluidos

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

## Ejecución

### Opción 1: arranque completo

```bat
START_SIMPLE.bat
```

Esto levanta:
- Frontend Flask en `http://localhost:5000`
- Backend FastAPI en `http://localhost:8002`

### Opción 2: backend manual

```powershell
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

### Opción 3: interfaz Flask manual

```powershell
cd ESTIMASTRUCT
python app.py
```

## Estructura

- `backend/` API, modelos, routers y procesos de importación/exportación
- `frontend/` interfaz principal
- `ESTIMASTRUCT/` compatibilidad Flask y plantillas
- `development/Template2_Updated/` bases versionadas de fichas
- `scripts_utils/` utilidades de mantenimiento

## Notas

- La versión canónica para nuevas obras es `v1.1`.
- Los schedules de Revit son la fuente de cantidades.
- Los archivos generados, bases locales y logs se ignoran en Git para mantener el repositorio limpio.
- La interfaz Flask crea una base SQLite mínima en el primer arranque si todavía no existe `ESTIMASTRUCT/estimastruct.db`.
