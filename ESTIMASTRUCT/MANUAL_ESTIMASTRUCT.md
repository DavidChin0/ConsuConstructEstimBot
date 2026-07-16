# 📖 MANUAL ESTIMASTRUCT — Arquitectura Completa

**Última actualización:** 26 abril 2026  
**Versión:** 1.0  
**Autor:** Claude Code + Development Team  
**Status:** ✅ Productivo

---

## 🎯 RESUMEN EJECUTIVO

**ESTIMASTRUCT** es un sistema de estimación de costos para construcción con arquitectura Full-Stack:
- **Frontend:** HTML/CSS/JS (Vanilla) — UI para crear presupuestos
- **Backend:** FastAPI (Python) — APIs REST + lógica de negocio
- **Database:** SQLite — Presupuestos, capítulos, partidas, insumos
- **Data Source:** Template 2 - Updated (JSON) — Base de fichas estándar

**Flujo principal:** Usuario crea obra → Frontend envía datos → Backend carga template → Se crea presupuesto en BD

---

## 📁 ESTRUCTURA DE CARPETAS

```
D:\OneDrive\Bots\Estimacion\
├── frontend/
│   ├── index.html          # HTML estructura
│   ├── css/style.css       # Estilos (tema oscuro, grid layout)
│   ├── js/app.js           # Lógica principal (1800+ líneas)
│   └── [otros assets]
├── backend/
│   ├── main.py             # FastAPI app, CORS, static files
│   ├── db.py               # SQLAlchemy, SessionLocal
│   ├── models.py           # ORM: Presupuesto, Capitulo, Partida, etc.
│   ├── requirements.txt    # Dependencies (fastapi, sqlalchemy, openpyxl)
│   ├── routers/
│   │   ├── presupuestos.py # POST /presupuestos, /presupuestos/from-template
│   │   ├── partidas.py     # CRUD partidas
│   │   ├── insumos.py      # Catálogo insumos
│   │   ├── recursos.py     # Mano obra, materiales
│   │   ├── export.py       # Exportar a Excel
│   │   ├── scripts.py      # Pasos 2, 4, 5 (Revit, exportar)
│   │   └── calculos.py     # Totales, sobrecosto
│   ├── scripts_runner/     # Ejecutores de scripts
│   └── seed_bd.py          # Importar datos iniciales
├── CAMBIOS_IMPLEMENTADOS.md # Frontend changes
├── CAMBIOS_BACKEND.md      # Backend changes
├── TROUBLESHOOTING.md      # Debugging guide
└── MANUAL_ESTIMASTRUCT.md  # Este archivo
```

---

## 🎨 FRONTEND — HTML/CSS/JS

### **Ubicación:** `D:\OneDrive\Bots\Estimacion\frontend\`

### **index.html — Estructura**

#### Header (línea 12-45)
```html
<div id="header">
  <h1>ESTIMASTRUCT</h1>
  <span class="obra-titulo">Obra activa</span>
  <div class="totales">Costo directo | Total</div>
  <button id="btn-actualizar">⟳ Actualizar</button>
  <button id="btn-modo">👤 Cliente</button>
  <div id="dev-menu-wrap">
    <button id="btn-dev-menu">⚙ Pasos ▾</button>
    <div id="dev-menu">
      <button data-step="opciones">⚙ Opciones</button>
      <button data-step="2">Paso 2 — Keynotes</button>
      <button data-step="4">Paso 4 — RevitQ</button>
    </div>
  </div>
  <div id="export-menu-wrap">
    <button id="btn-exportar">⬇ Exportar ▾</button>
  </div>
  <button id="btn-nueva-obra">+ Nueva Obra</button>
</div>
```

#### Layout (línea 47-199)
```html
<div id="layout">
  <div id="sidebar">Obras list</div>
  <div id="main">
    <div id="recursos-bar">Vinetas (INSUMOS, MANO OBRA)</div>
    <div id="content-wrapper">
      <div id="table-area">Tabla de capítulos/partidas</div>
      <div id="recursos-panel-lateral">Búsqueda y listado de recursos</div>
    </div>
    <div id="panel-bottom">Detalle de partida seleccionada</div>
  </div>
</div>
```

#### Modales (línea 200+)
- `#modal-csv-pick` — Elegir archivo de schedules
- `#modal-script-out` — Mostrar output de scripts
- `#modal-delete` — Confirmar borrar obra
- `#modal-rename` — Renombrar obra
- `#modal-obra` — Crear nueva obra
- `#modal-template-version` — **Selector V1.0/V1.1 (NUEVO)**

### **style.css — Temas y Componentes**

#### Variables CSS (línea 3-23)
```css
:root {
  --bg: #2d2d2d;           /* Fondo oscuro */
  --surface: #3a3a3a;      /* Superficies */
  --accent: #f5c518;       /* Amarillo marca */
  --accent-dim: #d4a815;   /* Amarillo oscuro */
  --text: #efefef;         /* Texto claro */
  --text-dim: #a8a8a8;     /* Texto tenue */
  --border: #555555;       /* Bordes */
  --sidebar-w: 220px;
  --header-h: 56px;
}
```

#### Grid Layout
- Header: 56px (flex)
- Sidebar: 220px (left)
- Main: flex (resto)
  - Table-area: izquierda (scroll)
  - Recursos-panel: derecha (hidden by default)
  - Panel-bottom: abajo (hidden by default)

### **app.js — Lógica Principal**

#### Estado Global (línea 26-35)
```javascript
let state = {
  presupuestos: [],        // Lista de obras
  activeId: null,          // Obra actual seleccionada
  activeData: null,        // Datos completos obra actual
  selectedPartida: null,   // Partida seleccionada para editar
  collapsedCaps: new Set(), // Capítulos colapsados
  showTypeMark: false,     // Mostrar columna Type Mark
  unidades: [],            // Unidades disponibles
  modo: "cliente",         // "cliente" o "desarrollador"
  templateVersion: "v1.0", // "v1.0" o "v1.1" (localStorage)
};
```

#### Funciones Principales

**Obras:**
- `loadObras()` — Fetch GET /presupuestos
- `loadObra(id)` — Cargar obra específica
- `renderSidebar()` — Renderizar lista obras
- `borrarObra()` — DELETE /presupuestos/{id}

**UI:**
- `toggleModo()` — Cambiar Cliente ↔ Desarrollador
- `applyModoUI()` — Mostrar/ocultar elementos según modo
- `toggleTypeMark()` — Show/hide columna Type Mark
- `renderTable()` — Renderizar tabla de capítulos/partidas

**Modales:**
- `openModalObra()` — Abre modal crear obra
- `initModalObra()` — Setup evento submit
- `openModalTemplateVersionDialog()` — Abre selector V1.0/V1.1
- `initModalTemplateVersion()` — Setup radio buttons

**Pasos (Scripts):**
- `runStep2Keynotes()` — POST /presupuestos/{id}/scripts/keynotes
- `openStep4PickCsv()` — Elegir CSV para importar schedules

**API Utility:**
```javascript
async function api(method, path, body = null) {
  // Fetch con Content-Type: application/json
  // Manejo de errores
}
const API = "http://localhost:8000";
```

#### Event Listeners (DOMContentLoaded)
```javascript
document.addEventListener("DOMContentLoaded", () => {
  loadObras();                      // Cargar lista
  initDevMenu();                    // Setup ⚙ Pasos
  initModalTemplateVersion();       // Setup selector V1.0/V1.1 ← NUEVO
  initModalObra();                  // Setup modal crear
  initExportMenu();                 // Setup ⬇ Exportar
  initPanelBottom();                // Setup panel detalle
  applyModoUI();                    // Aplicar estilos modo
});
```

---

## ⚙️ BACKEND — FastAPI + SQLAlchemy

### **Ubicación:** `D:\OneDrive\Bots\Estimacion\backend\`

### **main.py — Aplicación FastAPI**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# Static files
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")

# Routers
app.include_router(presupuestos.router)
app.include_router(partidas.router)
app.include_router(insumos.router)
app.include_router(recursos.router)
app.include_router(export.router)
app.include_router(scripts.router)
app.include_router(calculos.router)

# uvicorn run main.py --reload
```

### **db.py — Base de Datos**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./estimastruct.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Base de datos:** `estimastruct.db` (SQLite, mismo directorio que backend)

### **models.py — ORM Definitions**

#### **Presupuesto**
```python
class Presupuesto(Base):
    __tablename__ = "presupuesto"
    
    id: str (UUID primary key)
    nombre: str
    cliente: str (nullable)
    fecha: date
    moneda: str ("HNL", "USD")
    es_template: bool (True para templates)
    created_at: datetime
    
    Relationships:
    - config: ConfigPresupuesto (1-to-1)
    - capitulos: [Capitulo] (1-to-many)
```

#### **ConfigPresupuesto**
```python
class ConfigPresupuesto(Base):
    presupuesto_id: FK
    sobrecosto: float (20)           # % overhead → PU = base × (1 + sobrecosto/100)
    administracion: float            # % indirecto
    utilidad: float
    imprevistos: float
    iva: float (15)
    otros_factor: float
    template_version: str ("v1.0")  # ✨ NEW: DB version used (v1.0 original / v1.1 updated)
    
    Nota: template_version se guarda por proyecto (no global).
    Cada presupuesto puede usar v1.0 (277 fichas) o v1.1 (40 fichas).
```

#### **Capitulo**
```python
class Capitulo(Base):
    __tablename__ = "capitulo"
    
    id: str (UUID PK)
    presupuesto_id: FK
    clave: str (CSI division "03", "04", etc.)
    nombre: str (DIVISIONES_CSI[clave])
    orden: int
    
    Relationships:
    - presupuesto: Presupuesto
    - partidas: [Partida]
```

#### **Partida** (Ficha/Actividad)
```python
class Partida(Base):
    __tablename__ = "partida"
    
    id: str (UUID PK)
    capitulo_id: FK
    clave_csi: str (completo "09 22 13")
    descripcion: str
    unidad: str ("m2", "global", etc.)
    cantidad: float (ingresada por usuario)
    
    # Precios importados de template
    costo_mo: float (mano obra unitaria)
    costo_ma: float (material unitario)
    unitario_matriz: float (sub-matrices, 0 normalmente)
    costo_base: float (= MO + MA + matriz)
    precio_unitario: float (= costo_base × (1 + sobrecosto/100))
    total: float (= cantidad × precio_unitario)
    
    # Revit integration
    revit_q: float (cantidad inicial de Revit)
    factor_e: float (ajuste externo)
    factor_f: float (ajuste fórmula)
    
    # Metadata
    color_tipo: str ("amarillo", "verde", "azul", "rosa")
    type_mark: str (identificador Revit)
    es_formula: bool
    formula_ref: str ("=$E$66")
    orden: int
```

### **routers/presupuestos.py — API Principal**

#### **Modelos Pydantic**
```python
class ConfigIn(BaseModel):
    sobrecosto: float = 20
    administracion: float = 0
    utilidad: float = 0
    imprevistos: float = 0
    iva: float = 15
    otros_factor: float = 0

class PresupuestoIn(BaseModel):
    nombre: str
    cliente: Optional[str] = None
    moneda: str = "HNL"
    config: Optional[ConfigIn] = None

class FromTemplateIn(BaseModel):  # ← CON NUEVO PARÁMETRO
    nombre: str
    cliente: Optional[str] = None
    moneda: str = "HNL"
    config: Optional[ConfigIn] = None
    template_version: str = "v1.0"  # v1.0 o v1.1
```

#### **Endpoints**

**GET /presupuestos**
```
Retorna: [
  {
    "id": "uuid",
    "nombre": "Residencial Los Pinos",
    "cliente": "Cliente ABC",
    "moneda": "HNL",
    "es_template": False,
    "costo_directo": 50000,
    "total_con_indirectos": 57500
  }
]
```

**POST /presupuestos** — Crear obra vacía
```
Body: PresupuestoIn
Retorna: {"id": "uuid", "nombre": "..."}
```

**POST /presupuestos/from-template** — **ENDPOINT PRINCIPAL**
```
Body: FromTemplateIn {
  "nombre": "Nueva obra",
  "cliente": "ABC",
  "moneda": "HNL",
  "template_version": "v1.0",  ← NUEVO
  "config": { "sobrecosto": 20, ... }
}

Flujo:
1. Si template_version == "v1.0" o "v1.1":
   → Llamar _load_fichas_from_json(template_version)
   → Llamar _create_from_template2_updated()
   → Crea capítulos + partidas desde JSON
2. Si no existe:
   → Fallback a Template de BD (Template CC 2026)

Retorna: {
  "id": "uuid",
  "nombre": "Nueva obra",
  "capitulos": 8,
  "template_source": "Template 2 - Updated v1.0"  ← NUEVO
}
```

**GET /presupuestos/{id}** — Detalle obra
```
Retorna: {
  "id": "uuid",
  "nombre": "...",
  "capitulos": [
    {
      "id": "uuid",
      "clave": "03",
      "nombre": "Concreto",
      "partidas": [
        {
          "id": "uuid",
          "clave_csi": "03 31 00.1",
          "descripcion": "...",
          "cantidad": 0,
          "precio_unitario": 100,
          "total": 0,
          ...
        }
      ]
    }
  ]
}
```

**PUT /presupuestos/{id}/partidas/{pid}** — Editar partida
```
Body: { "cantidad": 50, "revit_q": 40, ... }
Recalcula: total = cantidad × precio_unitario
```

**DELETE /presupuestos/{id}** — Borrar obra

### **Funciones Nuevas (Template 2 - Updated)**

#### **_load_fichas_from_json(template_version: str) → list**
```python
# Lee: D:\...\ESTIMASTRUCT\development\Template2_Updated\{version}\fichas\fichas_{version}.json
# Retorna: Lista de fichas (28 objetos)
# Fallback: Si v1.0 no existe, intenta v1.1
```

#### **_create_from_template2_updated(nuevo, template_version, sobrecosto, db)**
```python
# 1. Carga fichas del JSON
fichas = _load_fichas_from_json(template_version)

# 2. Para cada ficha:
#    - Mapea CSI a división (00-33)
#    - Crea/reutiliza capítulo
#    - Crea partida con:
#      - costo_mo: suma insumos con código "MO-*"
#      - costo_ma: suma insumos con código "MA-*"
#      - precio_unitario = (MO + MA) × (1 + sobrecosto/100)

# 3. Guarda todo en BD
```

### **Otros Routers**

**partidas.py** — CRUD partidas
- PUT /presupuestos/{id}/partidas/{pid} — Actualizar cantidad, unitario
- DELETE /presupuestos/{id}/partidas/{pid} — Borrar partida

**export.py** — Exportar a Excel
- GET /presupuestos/{id}/export — Presupuesto (main + proposal)
- GET /presupuestos/{id}/export-db — BD completa (matrix view)

**scripts.py** — Integración Revit
- POST /presupuestos/{id}/scripts/keynotes — Genera keynotes.txt
- GET /scripts/schedules-csvs — Lista CSVs disponibles
- POST /presupuestos/{id}/scripts/import-quantities — Importa cantidades

---

## 💾 DATABASE — Modelos y Relaciones

### **Diagrama ER**
```
Presupuesto (1)
  ├─ ConfigPresupuesto (1)
  └─ Capitulo (*)
      └─ Partida (*)
          └─ Insumo (vía descripción)
```

### **Flujo de Datos al Crear Obra**

```
Usuario crea "Nueva Obra"
    ↓
Frontend: POST /presupuestos/from-template
  {
    "nombre": "Residencial",
    "template_version": "v1.0"
  }
    ↓
Backend: crear_desde_template()
    ├─ Lee: fichas_v1.0.json (28 fichas)
    ├─ Para cada ficha:
    │   ├─ Mapea CSI → división → capítulo
    │   ├─ Suma insumos MO/MA
    │   └─ Crea Partida con precios
    └─ INSERT INTO presupuesto, capitulo, partida
    ↓
BD: estimastruct.db
    ├─ presupuesto (1 nueva)
    ├─ config_presupuesto (1)
    ├─ capitulo (8 nuevos)
    └─ partida (28 nuevos)
    ↓
Frontend recibe: {"id": "uuid", "capitulos": 8}
    ↓
Usuario ve: 28 fichas listas en tabla
```

---

## 🔄 TEMPLATE 2 - UPDATED — Data Layer

### **Ubicación:** `D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\`

### **Estructura v1.0**
```
v1.0/
├── fichas/
│   ├── fichas_v1.0.json (492 KB)  ← Lee backend
│   └── fichas_v1.0.csv (3 KB)     ← Referencia
├── insumos/
│   ├── insumos_v1.0.json (43 KB)
│   └── insumos_v1.0.csv (17 KB)
└── README.md
```

### **Formato Ficha (JSON)**
```json
{
  "csi": "09 22 13",
  "codigo": "CEI-01",
  "descripcion": "Estructura cielo falso (m2)",
  "unidad": "m2",
  "cantidad": 1,
  "costoTotal": 91,
  "insumos": [
    {
      "codigo": "MA-065",
      "descripcion": "Furring metal 0.34mm x12'",
      "unidad": "lance",
      "cantidad": 0.55,
      "precioUnitario": 107,
      "total": 58.85
    },
    {
      "codigo": "MO-006.1",
      "descripcion": "Ayudante especializado",
      "unidad": "jor",
      "cantidad": 0.05,
      "precioUnitario": 535,
      "total": 26.75
    }
  ]
}
```

### **Contenido v1.0**
- **28 fichas:** CSI 03, 04, 05, 06, 07, 09, 22, 26
- **146 insumos:** Códigos MA-*, MO-*, EQ-*
- **Precios:** Lempiras (HNL)
- **Rendimientos:** Cantidades por m2/unidad

### **Crear v1.1**
1. Copiar: v1.0 → v1.1
2. Actualizar: fichas_v1.1.json (precios nuevos)
3. Backend automáticamente leerá v1.1 cuando se seleccione

---

## 🎯 FLUJOS PRINCIPALES

### **Flujo 1: Crear Presupuesto Desde Template**

```
Frontend                           Backend                        Database
   |                                |                               |
   | 1. Usuario: "+ Nueva Obra"     |                               |
   |=========================================>                       |
   |                                |                               |
   | 2. Modal: nombre, cliente      |                               |
   |    (template_version = v1.0)   |                               |
   |                                |                               |
   | 3. POST /presupuestos/         |                               |
   |    from-template               |                               |
   |=========================================>                       |
   |                                |                               |
   |                                | 4. Lee fichas_v1.0.json      |
   |                                |========>                      |
   |                                | (28 fichas)                   |
   |                                |<========                      |
   |                                |                               |
   |                                | 5. Crea estructura:           |
   |                                |    - 1 Presupuesto           |
   |                                |    - 1 Config                |
   |                                |    - 8 Capítulos            |
   |                                |    - 28 Partidas            |
   |                                |========================================>
   |                                |                               | INSERT
   |                                |                               |<========
   |                                |                               |
   | 6. {id, nombre, capitulos: 8}  |                               |
   |<=========================================                       |
   |                                |                               |
   | 7. GET /presupuestos/{id}      |                               |
   |=========================================>                       |
   |                                |                               | SELECT
   |                                |                               |<========
   | 8. Renderiza tabla             |                               |
   |    (28 fichas listas)          |                               |
   |<=========================================                       |
```

### **Flujo 2: Editar Cantidad de Partida**

```
Frontend                           Backend                        Database
   |                                |                               |
   | 1. Usuario: modifica cantidad  |                               |
   |                                |                               |
   | 2. PUT /presupuestos/{id}/     |                               |
   |     partidas/{pid}             |                               |
   |     { "cantidad": 50 }         |                               |
   |=========================================>                       |
   |                                |                               |
   |                                | 3. Calcula:                  |
   |                                |    total = 50 × precio_unit. |
   |                                |                               | UPDATE
   |                                |========================================>
   |                                |                               |<========
   | 4. Tabla actualiza             |                               |
   |    (total recalculado)         |                               |
   |<=========================================                       |
```

### **Flujo 3: Cambiar Versión Template (V1.0 → V1.1)**

```
Frontend                           
   |
   | 1. Modo Desarrollador: 🛠 Desarrollador
   |
   | 2. ⚙ Pasos ▾ → ⚙ Opciones
   |
   | 3. Modal selector:
   |    ☑ V1.0 (actual)
   |    ○ V1.1
   |
   | 4. Selecciona V1.1
   |
   | 5. localStorage actualiza:
   |    "estimastruct.template-version" = "v1.1"
   |
   | 6. Próxima obra (Backend):
   |    Lee fichas_v1.1.json (si existe)
   |    Si no existe, fallback a v1.0
```

---

## 🔧 CONFIGURACIÓN Y DEPLOYMENT

### **Variables Hardcodeadas (Backend)**

```python
# routers/presupuestos.py
base_path = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated"

# backend/main.py
DATABASE_URL = "sqlite:///./estimastruct.db"
API_URL = "http://localhost:8000"

# seed_bd.py
XLSX_PATH = r"D:\OneDrive\Bots\Estimbot\MasterFiles\Base de Datos Import.xlsx"
```

### **Variables Frontend (localStorage)**

```javascript
// Clave: "estimastruct.template-version"
// Valores: "v1.0", "v1.1"
// Default: "v1.0"

// Clave: "estimastruct.modo"
// Valores: "cliente", "desarrollador"
// Default: "cliente"
```

### **Requirements Backend**
```
fastapi
sqlalchemy
openpyxl
python-multipart
```

### **Startup Backend**
```bash
cd D:\OneDrive\Bots\Estimacion\backend
uvicorn main.py --reload --host 0.0.0.0 --port 8000
```

### **Frontend (Static)**
Servido por FastAPI desde `/frontend` en `http://localhost:8000`

---

## 📊 ESTADOS Y TRANSICIONES

### **Estado Usuario**
```javascript
state.modo
  ├─ "cliente"       → Oculta dev tools, panel bottom, recursos-bar
  └─ "desarrollador" → Muestra todo, ⚙ Pasos, opciones avanzadas
```

### **Estado Aplicación**
```javascript
state.activeId          → ID obra seleccionada (null = sin obra)
state.selectedPartida   → Partida seleccionada (null = ninguna)
state.templateVersion   → "v1.0" o "v1.1" (localStorage)
state.showTypeMark      → Boolean (mostrar columna)
state.collapsedCaps     → Set de capitulos colapsados
```

---

## 🐛 DEBUGGING Y TROUBLESHOOTING

### **Problema: Menú "Opciones" no aparece**
**Causa:** Cache del navegador  
**Solución:** Ctrl+Shift+Delete → Borrar cache → Ctrl+F5

### **Problema: Partidas no se guardan**
**Causa:** Error en backend  
**Acción:** Ver console.log() en F12 → Ver errores en FastAPI

### **Problema: Template 2 no carga**
**Causa:** Ruta incorrrecta o archivo no existe  
**Solución:** Verificar que fichas_v1.0.json existe en ruta correcta  
**Debug:** Ver error en console del navegador

### **Problema: Obra creada pero sin capítulos**
**Causa:** Template de BD no tiene datos  
**Acción:** Correr `python seed_bd.py` desde backend/

---

## 📈 MÉTRICAS Y PERFORMANCE

### **Tamaños**
- HTML: ~20 KB
- CSS: ~30 KB
- JS: ~80 KB (app.js)
- SQLite DB: ~5-10 MB (después de seed)
- Template JSON: ~535 KB (28 fichas)

### **Queries Principales**
```python
# Listar obras (sin datos completos)
SELECT * FROM presupuesto WHERE es_template = FALSE
# ~50ms

# Cargar obra completa (con joins)
SELECT p.*, c.*, pa.* FROM presupuesto p
LEFT JOIN capitulo c ON p.id = c.presupuesto_id
LEFT JOIN partida pa ON c.id = pa.capitulo_id
WHERE p.id = ?
# ~100-200ms
```

---

## 📚 REFERENCIAS Y DOCUMENTACIÓN

### **Archivos Relacionados**
- `CAMBIOS_IMPLEMENTADOS.md` — Cambios frontend (modal, JS)
- `CAMBIOS_BACKEND.md` — Cambios backend (funciones, endpoints)
- `Template2_Updated/README.md` — Detalles del template
- `TROUBLESHOOTING.md` — Guía de debugging

### **Ubicaciones Críticas**
- Frontend: `D:\OneDrive\Bots\Estimacion\frontend\`
- Backend: `D:\OneDrive\Bots\Estimacion\backend\`
- Data: `D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\`
- DB: `D:\OneDrive\Bots\Estimacion\backend\estimastruct.db`

### **Stack Technology**
- **Frontend:** HTML5 + CSS3 + Vanilla JavaScript (no frameworks)
- **Backend:** FastAPI + SQLAlchemy
- **Database:** SQLite3
- **Server:** uvicorn (ASGI)
- **Data Format:** JSON (templates), Excel (import)

---

## ✅ CHECKLIST DE FUNCIONAMIENTO

Antes de dar por completado:
- [ ] Frontend carga sin errores (F12 console limpia)
- [ ] Modo Desarrollador ↔ Cliente funciona
- [ ] ⚙ Pasos ▾ → ⚙ Opciones abre modal
- [ ] Selector V1.0/V1.1 persiste en localStorage
- [ ] Crear obra carga fichas_v1.0.json correctamente
- [ ] Editar cantidad en partida recalcula total
- [ ] Exportar a Excel funciona
- [ ] Backend no tiene errores en logs

---

## 🎯 SETTINGS POR PROYECTO — Template Version

**Implementación:** 26 abril 2026  
**Status:** ✅ Productivo

Cada proyecto (presupuesto) puede usar una base de datos diferente, no solo una configuración global.

### Versiones Disponibles

| Versión | Fichas | Fuente | Uso |
|---------|--------|--------|-----|
| **V1.0** | 277 | MatricesImport.xlsx | Datos originales (default) |
| **V1.1** | 40 | Fichas revisadas 26 abril | Datos actualizados |

### Flujo: Crear Obra con Versión Específica

```
1. Usuario abre ESTIMASTRUCT
   ↓
2. Click: ⚙ Pasos → ⚙ Opciones
   ↓
3. Selecciona: V1.0 o V1.1 → Guarda
   (Guarda en localStorage para futuras obras)
   ↓
4. Click: + Nueva Obra
   ↓
5. Modal abre con selector "Base de Datos"
   - Pre-seleccionado con valor de localStorage
   - Permite cambiar antes de crear
   ↓
6. Rellena: Nombre, Cliente, Moneda, Sobrecosto, Versión
   ↓
7. Click: Crear Obra
   ↓
8. Frontend envía: {nombre, cliente, moneda, template_version: "v1.0", config: {...}}
   ↓
9. Backend:
   - Crea Presupuesto
   - Crea ConfigPresupuesto CON template_version
   - Carga fichas desde v1.0 JSON (277 fichas)
   - Crea capítulos/partidas automáticamente
   ↓
10. Obra creada con 6-8 capítulos × 277 partidas
   ↓
11. Header muestra: "Nombre Obra [DB: V1.0 Original]"
```

### Storage de Configuración

**En localStorage (global):**
- Clave: `estimastruct.template-version`
- Valor: "v1.0" o "v1.1"
- Uso: Default para nuevas obras

**En BD - ConfigPresupuesto (por proyecto):**
- Campo: `template_version` (String)
- Valor: "v1.0" o "v1.1"
- Uso: Qué versión usó cada presupuesto específico
- Visible: Badge al lado del nombre en obra activa

### Cambiar Versión

**Actual:** Crear nueva obra con versión diferente
```
Proyecto A → v1.0 (277 fichas)
Proyecto B → v1.1 (40 fichas)
Proyecto C → v1.0 (usuario cambió de opinión)
```

**Futuro:** Permitir cambiar en settings de obra existente

### Archivos Relacionados

```
backend/models.py
  ├─ ConfigPresupuesto.template_version (línea ~40)

backend/routers/presupuestos.py
  ├─ FromTemplateIn.template_version (línea ~45)
  ├─ crear_desde_template() (línea ~220-245)

frontend/index.html
  ├─ #obra-template-version selector (línea ~308)
  ├─ #template-version-badge (línea ~15)

frontend/js/app.js
  ├─ initModalObra() (línea ~1093, sínc selector)
  ├─ openModalObra() (línea ~1122, cargar valor)
  ├─ updateTemplateDesc() (línea ~1137, mostrar descripción)
  ├─ updateTemplateVersionBadge() (línea ~193, mostrar badge)

Data Layer:
  Template2_Updated/
  ├─ v1.0/fichas/fichas_v1.0.json (277 fichas)
  └─ v1.1/fichas/fichas_v1.1.json (40 fichas)
```

---

## 🚀 PRÓXIMAS MEJORAS

### Completadas (26 abril 2026)
- ✅ **V1.0 Template** — 277 fichas originales de MatricesImport.xlsx
- ✅ **V1.1 Template** — 40 fichas actualizadas (Fichas revisadas 26 abril)
- ✅ **Settings Por Proyecto** — Cada obra puede usar versión diferente

### Futuras
1. **Cambiar Template en Obra Existente** — Editar ConfigPresupuesto.template_version
2. **Más Templates** — V1.2, V1.3 para diferentes clientes/épocas
3. **Historial de Cambios** — Auditoría de qué versión usó cada cambio
4. **Real-time sync** — WebSockets para múltiples usuarios
5. **Revit Integration** — Pasos 2 y 4 completos
6. **Reportes avanzados** — Gráficos de costos, análisis por versión
7. **Mobile** — Responsive design o app móvil
8. **Validation en cambio de versión** — Alertar si hay cambios incompatibles

---

**Creado:** 26 abril 2026  
**Próxima revisión:** Cuando haya cambios significativos  
**Mantenedor:** Claude Code + Team  
**Status:** ✅ Documentación Completa
