> [!CONTEXT]
> Auditoría de arquitectura de EstimaStruct (2026-07-12). Ingeniería inversa del sistema completo,
> problemas críticos detectados, estrategia de refactor y código de referencia production-grade.
> NO se modificó código vivo: este documento es el entregable. Complementa (no reemplaza) a
> `ARQUITECTURA_Y_FLUJO.md`, que sigue siendo el contrato del flujo de negocio.

> [!WARNING]
> **HISTÓRICO 2026-07-12.** Las decisiones de esta auditoría fueron formalizadas en [`docs/architecture.md §9 ADRs`](architecture.md).
> Ver ADR-001 a ADR-006 para el resultado de esta auditoría.
> No actualizar este archivo.

# EstimaStruct — Auditoría de Arquitectura 2026-07-12

---

## 1. Arquitectura real (ingeniería inversa)

### 1.1 Topología de procesos

```
┌─────────────────────────────┐      ┌──────────────────────────────────────┐
│  Flask :5000 (UI server)    │      │  FastAPI :8002 (API de negocio)      │
│  ESTIMASTRUCT/app.py        │ ───► │  backend/main.py — 19 routers        │
│  · sirve templates/index.html (PROD)│  · SQLAlchemy ORM                    │
│  · sirve frontend/js|css|vendor     │  · SQLite C:\EstimaStruct\data\      │
│  · cache-bust ?v=mtime por request  │    estimacion.db (WAL, FK ON)        │
│  · SU PROPIA BD: estimastruct.db ◄──┼─ ⚠ segunda BD con tabla `recursos`  │
│    (actividades/recursos/unidades)  │  · technical_memory.db (sqlite raw)  │
└─────────────────────────────┘      │  · valores_banco.json (estado file)  │
                                      └──────┬───────────────────────────────┘
   Navegador (vanilla JS ~7,000 loc)         │ urllib → Supabase (portal)
   core.js → API = localhost:8002            │ reportlab / Chromium → PDF
                                              ▼
        Revit/pyRevit ──CSV/TXT──►  scripts_runner/*  ◄──CSV/TSV── ETABS
```

### 1.2 Flujo de datos completo (end-to-end)

1. **Catálogo** — fichas JSON curadas (`development/Template2_Updated/v1.X/fichas/fichas_v1.X.json`, en OneDrive) = fuente de partidas con insumos. CSI = llave maestra.
2. **Presupuesto** — `POST /presupuestos/from-template` materializa fichas → `Capitulo` → `Partida` → `InsumoPartida`. Precios: `costo_base = MO + MA + matriz`; `PU = base × (1 + sobrecosto/100)`; `total = cantidad × PU`.
3. **Cantidades** — Revit exporta schedules CSV → `import_quantities.py` agrega por CSI → escribe `revit_q`/`cantidad` → recalcula.
4. **Ingeniería** — modelo B (`DisenoElemento → CasoDiseno → ResultadoDiseno`, espejo en `ConexionAcero/Caso/Resultado`). Motores puros sin ORM (`calculo_*.py`): patrón limpio Request(Pydantic) → Router → Motor → Resultado. Parsers ETABS tolerantes.
5. **Puente A↔B** — `generar-partidas` vuelca takeoff del diseño a partidas CSI (Div 03/05).
6. **Salidas** — export XLSX (`export.py`), PDF reportlab (`export_pdf.py` + `membrete.py`), PDF HTML/Chromium (`preview_pdf.py`), cronograma Gantt (`cronograma.py`), publish a Supabase (`portal_publish.py`).

### 1.3 Inventario de código

| Capa | LOC | Notas |
|---|---|---|
| Routers FastAPI (19) | ~7,900 | `diseno_estructural.py` = 2,004 (god router) |
| Motores puros | ~4,600 | lo mejor del codebase; sin ORM, testeable |
| Infra backend (db/config/models/pricing) | ~600 | FASE 0/1 ya aplicadas, correctas |
| scripts_runner (pipeline Revit) | ~1,900 | paths OneDrive hardcodeados |
| Flask + templates | ~1,800 | segunda BD + flujo preview deprecado |
| Frontend JS | ~7,000 | vanilla, sin build, sin módulos ES |
| **Tests** | **0** | ni un solo test en todo el repo |

---

## 2. Problemas críticos (ordenados por riesgo)

### 🔴 P1 — Definición divergente de `costo_directo` (riesgo financiero)

`export_pdf.py:190` calcula costo directo **sin** `unitario_matriz`:

```python
costo_directo += cantidad * (float(pa.costo_mo or 0) + float(pa.costo_ma or 0))
```

mientras `presupuestos.py` (listar, `_totales`) y `services/pricing.calc_base` usan `MO + MA + matriz`. Toda partida con insumos SUBCONTRATO/FLETE/EQUIPO (pueblan `unitario_matriz` desde el fix 2026-07-03) reporta un costo directo **menor en el PDF banco** que en la app. Mismo patrón de raíz que el bug de doble conteo de `/calcular` ya corregido: fórmula reimplementada a mano en vez de usar la fuente única.
**Acción:** decisión del Director — si el PDF banco debe excluir matriz es regla de negocio y hay que documentarla en el docstring; si no, es bug y la línea debe llamar a `pricing.calc_base`.

### 🔴 P2 — Cero tests con motor financiero y de diseño estructural

El sistema calcula presupuestos reales y verifica diseño ACI/LRFD, y no existe ninguna prueba automatizada. Los motores puros (`calculo_*.py`, `services/pricing.py`) son funciones sin ORM — el costo de testearlos es mínimo y el retorno enorme. El historial ya lo demuestra: el bug de doble conteo (2026-07-03) y el P1 de arriba habrían caído con un test de invariante de 10 líneas.

### 🔴 P3 — Dos bases de datos con el mismo concepto

`ESTIMASTRUCT/estimastruct.db` (Flask) tiene tablas `recursos`, `actividades`, `unidades` — duplican el catálogo `Recurso` y las partidas de `estimacion.db` (FastAPI). Dos fuentes de verdad para precios de recursos = split-brain garantizado. Además `estimastruct.db` vive **dentro de OneDrive**, el mismo riesgo de corrupción por sync que motivó la migración FASE 0 de la BD principal.

### 🟠 P4 — API financiera sin autenticación + CORS `*`

`main.py`: `allow_origins=["*"]`, sin auth en ningún endpoint. Cualquier proceso local (o cualquier página web abierta en el navegador, vía CORS permisivo) puede borrar presupuestos o disparar `POST /presupuestos/{id}/publish-supabase`. Aceptable como app 100% local de un solo usuario; inaceptable en cuanto se exponga por Tailscale/LAN o entre el portal multiusuario.

### 🟠 P5 — Dinero en `float`

Las columnas son `Numeric(14,4)` pero todo el runtime convierte a `float` y opera en binario (`pricing.py`, routers, exports). La política "sin redondeo" documentada evita deltas *entre rutas*, pero no evita el drift acumulativo de float en sumas de miles de insumos. Para HNL con 2 decimales, `Decimal` con cuantización explícita en fronteras es el estándar.

### 🟠 P6 — Sin migraciones de esquema

`Base.metadata.create_all` + scripts `migrate_*.py` manuales. `create_all` solo crea tablas nuevas — nunca agrega columnas. Cada columna aditiva exige script manual idempotente y correrlo a mano; olvidarlo = crash en runtime con la BD viva. Con Alembic el modelo genera la migración y la BD guarda su versión.

### 🟠 P7 — El paquete backend no es un paquete

15 archivos hacen `sys.path.insert(0, ...)`. `main.py` hace `os.chdir(os.path.dirname(__file__))` en import-time (side effect global: `notifications.log` y todo path relativo dependen de él). Consecuencias: imports frágiles, imposible testear con pytest sin replicar el hack, doble-import posible (`models` importado por dos rutas distintas de sys.path).

### 🟡 P8 — God router `diseno_estructural.py` (2,004 líneas)

Mezcla: CRUD elementos/casos, motor de memoria de cálculo, contexto sísmico CHOC-08, clasificación de suelos, parsers ETABS, import masivo, puente a partidas y resumen CSI. `acero_diseno.py` importa 7 helpers privados (`_correr_caso_acero`, `_get_o_crear_capitulo`…) desde él — helpers compartidos viviendo en un router, no en servicios.

### 🟡 P9 — Flujo de release del frontend

- PROD = `templates/index.html` **editado directo** (flujo preview→promote deprecado, pero `/preview`, `/preview/init`, `/preview/promote` siguen vivos en `app.py` — código muerto operable que puede pisar prod con un POST).
- Repo git sin inicializar (decisión conocida) → los backups son `_backups/` rotando 3 + `.bak_*` sueltos (`app.js.bak_premod_20260616`, `estimacion.db.bak_MA374...` junto al código).
- Dos CSS casi gemelos (`style.css` 1,494 / `style_preview.css` 1,463) que divergen en silencio.

---

## 3. Lógica duplicada (mapa exacto)

| Lógica | Copias | Riesgo |
|---|---|---|
| `base = MO + MA + matriz` inline (existiendo `pricing.calc_base`) | `presupuestos.py:320`, `presupuestos.py:450`, `export.py:58`, `export_pdf.py:190` (esta además **omite** matriz → P1) | Alto — ya causó el bug de doble conteo |
| `_tipo_from_clave` | `presupuestos.py:74` y `updater.py:283` (idénticas) | Medio — clasificación de insumos diverge si se edita una |
| `_csi_sort_key` | `presupuestos.py:18` y `bases.py:120` — **mismo nombre, implementación distinta** | Medio — orden CSI inconsistente entre vistas |
| Copia campo-a-campo de `Partida` (20 campos) | `from-template` (BD), `duplicar()`, `_create_from_template2_updated` | Alto — columna nueva en `models.py` = 3 sitios a tocar; olvidarlo pierde datos silenciosamente |
| Catálogo `recursos` | `estimacion.db` (ORM) y `estimastruct.db` (Flask raw) | Alto — P3 |
| `sobrecosto = float(cfg.sobrecosto) if cfg ... else 20.0` | 6+ routers | Bajo — default mágico `20.0` repetido |

---

## 4. Cuellos de botella de rendimiento

1. **`duplicar()` (presupuestos.py)** — `db.flush()` dentro del loop de partidas: ~1,000 flushes por duplicación. Un flush al final basta (los FKs se resuelven con `relationship`, ver §6.3).
2. **`reasignar_capitulos`** — `db.query(Partida).count()` **dentro del loop** por cada partida movida (N+1 de COUNTs) + otro count por capítulo al final. Un solo `GROUP BY` resuelve todo.
3. **`joinedload` anidado en colecciones** (`detalle`, `calcular`, `duplicar`) — JOIN de colecciones anidadas multiplica filas: presupuesto × capítulos × partidas × insumos ≈ producto cartesiano parcial que SQLAlchemy dedupe en memoria. `selectinload` emite 1 query por nivel sin explosión.
4. **`_current_asset_version()` (Flask)** — glob + stat de todo `js/*.js` y `css/*.css` **en cada request**. Trivial hoy; correcto sería memoizar con TTL de 1s.
5. **Ordenamiento en Python por request** — `detalle` re-ordena capítulos y partidas con `sorted()` en cada GET; el orden natural CSI podría materializarse en la columna `orden` al escribir.
6. **SQLite un solo escritor** — WAL mitiga lecturas, pero `check_same_thread=False` + threadpool de FastAPI significa que escrituras largas (recalcular, import) serializan a todos los demás. Suficiente mono-usuario; es EL límite duro para el portal multiusuario.

Lo bueno ya hecho: `listar()` agrega costo directo en un solo SQL (comentario lo documenta), `_recalcular_todo` tiene skip-unchanged, pragmas WAL/mmap/cache afinados.

---

## 5. Riesgos de escalabilidad

| Riesgo | Detonante | Mitigación |
|---|---|---|
| SQLite mono-escritor | Portal Finanzas / 2º usuario concurrente | Camino ya trazado: Supabase/Postgres. El ORM hace el swap barato **si** se elimina el sqlite3 raw (`cronograma.py`, `routers/memory.py`, Flask) |
| Estado en archivos junto a la BD (`valores_banco.json`) | Cualquier acceso concurrente / backup parcial | Migrar a tabla (ya está en el roadmap del PDF banco) |
| Fichas maestras (JSON) y `estimastruct.db` en OneDrive | Sync corrompe/mueve mientras se lee | Mover a `C:\EstimaStruct\` como se hizo con la BD (FASE 0 ya probó el patrón) |
| `SilentNotifier` = thread daemon por proceso | `uvicorn --workers N` → N monitores duplicados | Aceptable hoy (1 worker); documentar la restricción |
| Frontend monolito global-state sin build | Cada módulo nuevo crece `app.js`/`index.html` a mano | La modularización ya empezó (core.js, tabla-render.js…); continuarla, no revertirla |
| pyRevit extension fuera del repo (`%APPDATA%`) | Drift silencioso entre botones y backend | Consolidar en repo (ya en roadmap R6/🟢) |

---

## 6. Estrategia de refactor (fases, sin cambiar funcionalidad)

Orden por retorno/riesgo. Cada fase es shippeable sola y verificable con "números idénticos antes/después".

### FASE A — Red de seguridad (prerequisito de todo lo demás)
1. `git init` + primer commit (decisión ya tomada, no ejecutada).
2. Suite mínima de tests de caracterización: fijar el comportamiento ACTUAL (no el ideal) de `pricing`, `/calcular`, `detalle`, un export. Con esto, todo refactor posterior se valida solo.

### FASE B — Una sola fuente de precio
3. Reemplazar los 4 sitios inline por `pricing.calc_base` / `recalcular_partida`. En `export_pdf._costos_obra`: **escalar decisión al Director** (P1) antes de tocar — es semántica financiera.
4. Mover `_tipo_from_clave` y `_csi_sort_key` a `csi_utils.py` (ya existe y es el lugar natural); un solo import en los 4 routers.

### FASE C — Paquete real
5. `__init__.py` de paquete + imports absolutos `from backend.xxx import` → borrar los 15 `sys.path.insert` y el `os.chdir`. Arranque: `python -m uvicorn backend.main:app`.
6. `lifespan` en vez de `@app.on_event` (deprecado en FastAPI 0.111).
7. `config.py` → `pydantic-settings` (validación de env + `.env` en `D:\Secrets`).

### FASE D — Descomponer el god router
8. `diseno_estructural.py` → `routers/diseno_crud.py` + `routers/sismo.py` + `routers/suelos.py` + `services/etabs_parse.py` + `services/partidas_bridge.py` (donde viven `_get_o_crear_capitulo`, `_crear_o_actualizar_partida`, `_correr_caso*`). Mismos paths → frontend intacto (patrón ya probado en R3).

### FASE E — Matar el split-brain
9. Decidir destino de `estimastruct.db`: (a) si la UI de matrices sigue viva, servirla desde la API :8002 contra `estimacion.db`; (b) si es legacy, archivar tablas y borrar rutas Flask `/api/matrices|recursos|unidades`. En cualquier caso, sacarla de OneDrive.
10. Borrar el flujo preview→promote muerto de `app.py` (deprecado 2026-07-03) — o al menos quitar los POST.
11. Candidato final: servir el frontend estático desde FastAPI (`StaticFiles` + template) y retirar Flask → un solo proceso, un solo puerto, cero drift de cache-busting.

### FASE F — Datos e infraestructura
12. Alembic (autogenerate contra `models.py`; los `migrate_*.py` quedan como historial).
13. `Decimal` en fronteras monetarias (pricing + exports), cuantización documentada. Validar contra tests de FASE A.
14. Auth mínima (API key local o token) + CORS restringido a `localhost:5000` **antes** de exponer por Tailscale.

---

## 7. Código de referencia (production-grade)

Muestras listas para adoptar en las fases. No aplicadas al código vivo.

### 7.1 `main.py` — lifespan + CORS restringido (FASE C/F)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import engine
from backend.models import Base
from backend.error_handler import register_exception_handlers
from backend.silent_notifier import notifier, notify_file
from backend.config import settings
from backend import routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)          # las tablas nuevas; columnas → Alembic
    notifier.subscribe(notify_file(settings.LOGS_DIR / "notifications.log"))
    notifier.start_monitoring()
    yield
    notifier.stop_monitoring()


app = FastAPI(title="Estimacion API", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,           # ["http://localhost:5000"]
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

for r in routers.ALL:                              # routers/__init__.py: ALL = [presupuestos.router, ...]
    app.include_router(r)
```

### 7.2 Fuente única de precio en los 4 sitios inline (FASE B)

```python
# presupuestos.py — from-template BD y actualizar_sobrecosto: reemplazar el inline por:
from backend.services.pricing import recalcular_partida

for cap in p.capitulos:
    for pa in cap.partidas:
        recalcular_partida(pa, sc)     # escribe costo_base, PU y total — misma fórmula que /calcular

# export_pdf.py — _costos_obra (TRAS decisión del Director sobre P1):
from backend.services.pricing import calc_base

def _costos_obra(p: Presupuesto) -> tuple[float, float]:
    """total_real = Σ total (con sobrecosto). costo_directo = Σ cantidad × costo_base (SIN sobrecosto).
    costo_base = MO + MA + matriz — misma definición que /presupuestos y /calcular (fix P1)."""
    total_real = costo_directo = 0.0
    for cap in p.capitulos:
        for pa in cap.partidas:
            total_real += float(pa.total or 0)
            costo_directo += float(pa.cantidad or 0) * calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz)
    return total_real, costo_directo
```

### 7.3 `duplicar()` sin N flushes y sin copia campo-a-campo (FASE B/D)

```python
# models.py — la lista de campos vive UNA vez, junto al modelo:
class Partida(Base):
    ...
    COPY_FIELDS = (
        "clave_csi", "descripcion", "unidad", "cantidad", "revit_q", "factor_e",
        "factor_f", "color_tipo", "costo_mo", "costo_ma", "unitario_matriz",
        "costo_base", "precio_unitario", "total", "es_formula", "formula_ref",
        "type_mark", "omniclass_num", "assembly_num", "orden",
    )

    def clone(self) -> "Partida":
        return Partida(**{f: getattr(self, f) for f in self.COPY_FIELDS})


# routers/presupuestos.py — duplicar: relationships resuelven los FKs → cero flush en el loop
@router.post("/{pid}/duplicar", status_code=201)
def duplicar(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        selectinload(Presupuesto.config),
        selectinload(Presupuesto.capitulos)
            .selectinload(Capitulo.partidas)
            .selectinload(Partida.insumos),
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    nuevo = Presupuesto(nombre=f"{p.nombre} (copia)", cliente=p.cliente, moneda=p.moneda)
    if p.config:
        nuevo.config = p.config.clone()            # mismo patrón COPY_FIELDS en ConfigPresupuesto
    for cap in p.capitulos:
        new_cap = Capitulo(clave=cap.clave, nombre=cap.nombre, orden=cap.orden)
        for pa in cap.partidas:
            new_pa = pa.clone()
            new_pa.insumos = [ins.clone() for ins in pa.insumos]
            new_cap.partidas.append(new_pa)
        nuevo.capitulos.append(new_cap)

    db.add(nuevo)                                  # cascade inserta TODO el árbol en un flush
    db.commit()
    return {"id": nuevo.id, "nombre": nuevo.nombre}
```

### 7.4 `reasignar_capitulos` sin N+1 de COUNTs (FASE B)

```python
from sqlalchemy import func

# UN query por todos los counts, antes del loop:
counts = dict(
    db.query(Partida.capitulo_id, func.count(Partida.id))
      .join(Capitulo, Capitulo.id == Partida.capitulo_id)
      .filter(Capitulo.presupuesto_id == pid)
      .group_by(Partida.capitulo_id)
      .all()
)

for pa in all_partidas:
    ...
    target = capitulos_map[div]
    pa.orden = counts.get(target.id, 0)
    counts[target.id] = pa.orden + 1               # mantener en memoria; sin ir a la BD
    counts[old_cap_id] -= 1
    pa.capitulo_id = target.id

# capítulos vacíos: leer del dict, no re-consultar
vacios = [cap for cap in p.capitulos if counts.get(cap.id, 0) == 0 and cap.clave != "00"]
```

### 7.5 Helpers CSI unificados (FASE B → `csi_utils.py`)

```python
# csi_utils.py — versión canónica única (hoy hay 2 _csi_sort_key distintas y 2 _tipo_from_clave)
import re

_NUM_RX = re.compile(r"\d+|\D+")

def csi_sort_key(clave: str) -> list:
    """Orden natural: '01 31 13' < '01 31 13.1' < '01 31 13.2' < '01 32 00'."""
    return [(0, int(t)) if t.isdigit() else (1, t.lower())
            for t in _NUM_RX.findall(clave or "")]

_TIPO_POR_PREFIJO = (
    (("MO-", "MO."), "MANO_OBRA"),
    (("HE-", "EQ-"), "EQUIPO"),
    (("SC-", "SUB-"), "SUBCONTRATO"),
    (("DIS-",), "DISEÑO"),
)

def tipo_from_clave(clave: str) -> str:
    c = (clave or "").upper()
    for prefijos, tipo in _TIPO_POR_PREFIJO:
        if c.startswith(prefijos):
            return tipo
    return "MATERIAL"
```

### 7.6 Test de caracterización — invariante de precio (FASE A; habría cazado P1 y el bug de /calcular)

```python
# tests/test_pricing_invariants.py
from backend.services.pricing import calc_base, precio_unitario, rebucket_insumos

class Ins:
    def __init__(self, tipo, total): self.tipo, self.total = tipo, total

def test_bucketing_3vias_cubre_todo_insumo():
    insumos = [Ins("MANO_OBRA", 10), Ins("MATERIAL", 20), Ins("SUBCONTRATO", 5), Ins("FLETE", 2)]
    mo, ma, otros = rebucket_insumos(insumos)
    assert (mo, ma, otros) == (10, 20, 7)
    # INVARIANTE: base desde buckets == suma directa de insumos (nada se cae ni se duplica)
    assert calc_base(mo, ma, otros) == sum(i.total for i in insumos)

def test_pu_es_base_por_factor():
    assert precio_unitario(100, 20) == 120.0
    assert precio_unitario(100, 0) == 100.0
```

### 7.7 `settings` tipado (FASE C)

```python
# config.py
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = {"env_prefix": "ESTIMA_", "env_file": r"D:\Secrets\estimastruct.env"}

    DB_PATH: Path = Path(r"C:\EstimaStruct\data\estimacion.db")
    FICHAS_DIR: Path = Path(r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated")
    EXPORTS_DIR: Path = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS")
    CORS_ORIGINS: list[str] = ["http://localhost:5000"]
    SOBRECOSTO_DEFAULT: float = 20.0        # hoy es un literal mágico repetido en 6 routers

    @property
    def LOGS_DIR(self) -> Path:
        return Path(__file__).resolve().parent / "logs"

settings = Settings()
```

---

## 8. Qué NO tocar (está bien como está)

- **Motores puros sin ORM** (`calculo_estructural`, `calculo_miembro_acero`, `calculo_conexion_acero`, `calculo_sismico_choc08`, `cronograma`): el patrón 4 capas es correcto y es la mejor decisión de arquitectura del sistema. Solo les faltan tests.
- **`db.py`** — pragmas, rollback en `get_db`, ruta fuera de OneDrive: FASE 0 bien ejecutada.
- **`services/pricing.py`** — fuente única correcta con docstrings forenses ejemplares; el problema es que 4 sitios aún no la usan.
- **CSI como llave maestra** en todo el join Revit↔ETABS↔partidas: consistente y bien defendido en código y docs.
- **`listar()` de presupuestos** — la agregación SQL única es exactamente el patrón a replicar en los demás hot paths.

---

## 9. Resumen ejecutivo

| Dimensión | Nota | Un renglón |
|---|---|---|
| Diseño de dominio | 🟢 | CSI-céntrico, motores puros, dos modelos bien separados |
| Consistencia de cálculo | 🔴 | 4 fórmulas inline; una diverge (P1, PDF banco) |
| Testing | 🔴 | 0 tests sobre motor financiero/estructural |
| Topología | 🟠 | 2 servidores, 3 BDs SQLite, 1 JSON de estado |
| Seguridad | 🟠 | Sin auth, CORS abierto (tolerable solo 100% local) |
| Evolución de esquema | 🟠 | create_all + scripts manuales; sin Alembic |
| Rendimiento actual | 🟢 | Adecuado mono-usuario; N+1s puntuales identificados |
| Deuda de empaquetado | 🟡 | sys.path hacks ×15, os.chdir, .bak en repo, sin git |

**Primeros 3 pasos concretos:** (1) `git init` + commit inicial, (2) tests de caracterización de pricing (§7.6), (3) decisión del Director sobre P1 y unificar los 4 sitios de fórmula.
