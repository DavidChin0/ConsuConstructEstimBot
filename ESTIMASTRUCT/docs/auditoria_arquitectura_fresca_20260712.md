> [!CONTEXT]
> Auditoría independiente de arquitectura de EstimaStruct, generada desde cero el 2026-07-12,
> verificando código actual con evidencia `path:line` fresca (no copiada de `auditoria_arquitectura_20260712.md`,
> que se usó solo como checklist de qué buscar). NO se modificó código vivo: este documento es el entregable.

# EstimaStruct — Auditoría de Arquitectura (independiente) 2026-07-12

---

## 1. Arquitectura real

### 1.1 Topología de procesos

```
┌────────────────────────────┐        ┌───────────────────────────────────────┐
│ Flask :5000 (ESTIMASTRUCT) │        │ FastAPI :8002 (backend/)              │
│ app.py — 257 LOC            │ ──────►│ main.py — 20 routers, 8,236 LOC        │
│ sqlite3 crudo (no ORM)      │        │ SQLAlchemy ORM, Numeric(14,4)          │
│ DB: estimastruct.db         │        │ DB: estimacion.db                      │
└────────────────────────────┘        └──────┬────────────────────────────────┘
                                              │
   Frontend vanilla JS (7,010 LOC activo)     │ urllib → Supabase (portal)
   sin build system, cache-bust por mtime     │ reportlab / Chromium → PDF
                                              ▼
        Revit/pyRevit ──CSV/TXT──► scripts_runner/* ◄──CSV/TSV── ETABS
```

Ambas BDs viven **fuera del repo**, en `C:\EstimaStruct\data\` (`estimacion.db` y `estimastruct.db`), configurado vía `backend/config.py:17` (`ESTIMA_DB_PATH`) y `ESTIMASTRUCT/app.py:20` (`ESTIMASTRUCT_UI_DB`). Las copias homónimas dentro del repo (`backend/estimacion.db`, `ESTIMASTRUCT/estimastruct.db`) son stale — una incluso renombrada a mano `estimastruct.db.STALE_20260712`, documentando su propia obsolescencia en el nombre de archivo.

Arranque: `START_UNICA.ps1:47` levanta `uvicorn backend.main:app --port 8002 --reload`; `START_UNICA.ps1:54` levanta Flask como proceso Python plano en :5000.

### 1.2 Flujo de datos end-to-end

1. **Catálogo** — fichas JSON curadas (`development/Template2_Updated/.../fichas_v1.X.json`) = fuente de partidas con insumos, CSI como llave maestra.
2. **Presupuesto** — `POST /presupuestos/from-template` materializa fichas → `Capitulo` → `Partida` → `InsumoPartida`. `costo_base = MO + MA + matriz`; `PU = base × (1 + sobrecosto/100)`; `total = cantidad × PU`. Fuente única declarada: `backend/services/pricing.py` (`calc_base`, `precio_unitario`, `recalcular_partida`).
3. **Cantidades** — Revit exporta schedules CSV → `scripts_runner/import_quantities.py` agrega por CSI → escribe `revit_q`/`cantidad` → recalcula.
4. **Ingeniería** — motores puros sin ORM (`calculo_estructural.py`, `calculo_miembro_acero.py`, `calculo_conexion_acero.py`, `calculo_sismico_choc08.py`): patrón Request(Pydantic) → Router → Motor → Resultado.
5. **Puente** — `services/partidas_bridge.py` vuelca takeoff de diseño a partidas CSI.
6. **Salidas** — export XLSX (`routers/export.py`), PDF reportlab (`routers/export_pdf.py` + `membrete.py`), PDF HTML/Chromium (`routers/preview_pdf.py`), cronograma (`routers/cronograma.py`), publish a Supabase (`routers/portal_publish.py`).

### 1.3 Inventario de código

| Capa | LOC | Notas |
|---|---|---|
| Routers FastAPI (20) | 8,236 | `diseno_estructural.py` = 1,215 (god router), `export.py` = 1,098 |
| Motores puros (`calculo_*.py` + afines) | ~6,700 | sin ORM, testeable, la mejor arquitectura del sistema |
| Servicios (`services/*.py`) | ~235 | `pricing.py` (81) fuente única declarada de precio |
| scripts_runner (pipeline Revit) | 1,890 | 9 archivos |
| Flask + templates | 257 + assets | sqlite3 crudo, sin ORM |
| Frontend JS activo | 7,010 | vanilla, sin build, 9 archivos `.bak_*` mezclados en el árbol |
| **Tests** | **0** | cero en todo el repo, sin pytest declarado |

---

## 2. Problemas críticos (por riesgo)

### 🔴 P1 — `pricing.calc_base` es fuente única "de jure", no "de facto"

`services/pricing.py` está bien construido — usa `Decimal`/`ROUND_HALF_UP` internamente (líneas 24-53) y el propio docstring documenta el bug histórico de doble conteo que motivó su creación. Pero **4 sitios reimplementan la fórmula a mano en float**, sin importar el módulo:

- `backend/routers/export.py:57,60` — `base = float(mo)+float(ma)+float(matriz)`, luego `PU` a mano.
- `backend/routers/presupuestos.py:319-320` (dentro de `_create_from_template2_updated`) y `:449-450` (dentro de `actualizar_sobrecosto`) — mismo archivo que YA importa `calc_base` en otras funciones, inconsistencia intra-archivo.
- `backend/routers/acero_diseno.py:474-477` — bucketing MO/MA manual, **no usa `unitario_matriz` en absoluto** y no importa `backend.services.pricing`.
- `backend/scripts_runner/import_quantities.py:225-227` — mismo patrón, en el pipeline de import de Revit.

Riesgo: cualquier partida con insumos que pueblan `unitario_matriz` (SUBCONTRATO/FLETE/EQUIPO) reporta costos distintos según qué endpoint la calculó. Mismo patrón de raíz que el bug de doble conteo ya corregido: la fórmula se reescribe en vez de reusarse.

### 🔴 P2 — Cero tests sobre motor financiero y de diseño estructural

Ningún archivo `test_*.py`, sin pytest en dependencias (`START_UNICA.ps1:36,39` solo instala `fastapi uvicorn sqlalchemy flask pydantic`). Los motores puros son funciones sin ORM — costo de testear mínimo, retorno enorme. El propio historial de `pricing.py` prueba que el bug de doble conteo habría caído con un test de invariante de 10 líneas.

### 🔴 P3 — 3 bases de datos SQLite vivas + 13 backups sin rotación

- `C:\EstimaStruct\data\estimacion.db` (FastAPI, 16 tablas incl. `alembic_version`).
- `C:\EstimaStruct\data\estimastruct.db` (Flask, 5 tablas: `actividades`, `recursos`, `unidades` — duplican conceptualmente el catálogo `Recurso` de la BD principal).
- `backend/technical_memory.db` (6 tablas de logging/memoria técnica).
- Además: `C:\EstimaStruct\data\` acumula **13 backups `.bak_*`** de `estimacion.db` sin purga automática, más 5 en `_LEGACY/backend/db_backups/`, más copias stale dentro del repo (`backend/estimacion.db`, `backend/estimacion.db.bak_MA374_...`, `ESTIMASTRUCT/estimastruct.db.STALE_20260712`).

Dos fuentes de verdad para precios de recursos = split-brain garantizado entre Flask y FastAPI.

### 🟠 P4 — API financiera sin autenticación + CORS `*`

`backend/main.py:24-29` — `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`. Cero middleware de auth en toda la API (ni JWT, ni API key, ni sesión) — confirmado por ausencia total de `Depends(...auth/token/current_user...)` en los 20 routers. Flask tampoco tiene auth. Aceptable como app local de un solo usuario; inaceptable en cuanto se exponga por LAN/Tailscale o al portal multiusuario.

### 🟠 P5 — Decimal solo "de tránsito", no end-to-end

Las columnas SQL son `Numeric(14,4)` (correcto), y `pricing.py` opera internamente en `Decimal` desde el fix del 2026-07-12. Pero **sus funciones públicas reciben y devuelven `float`** (decisión deliberada documentada en `pricing.py:32` para no romper la interfaz de los callers) — y el 100% de los routers castea a `float()` en cuanto lee la columna (ej. `routers/insumos.py:86-88`, `routers/partidas.py:394-396`, `routers/presupuestos.py:401-403`). El blindaje `Decimal` dura solo dentro de `pricing.py`; en el resto de la capa de aplicación el dinero vuelve a ser IEEE-754 binario.

### 🟠 P6 — Alembic configurado pero no usado como mecanismo principal

`backend/alembic/` existe con una sola migración baseline (`606c3f3a7b6b_baseline.py`). Pero `backend/main.py:15` corre `Base.metadata.create_all(bind=engine)` en cada arranque del lifespan, y comentarios explícitos en `models.py:314,360,450` documentan la estrategia real: "tabla nueva → create_all la crea sola". `create_all` nunca hace `ALTER` sobre columnas existentes — cualquier cambio de tipo/constraint en una columna ya creada no queda versionado en ningún lado. Además hay migraciones ad-hoc paralelas fuera de Alembic (`scripts_utils/migrate_all_dbs.py`, `migrate_reasignar_capitulos.py`).

### 🟡 P7 — God routers

`diseno_estructural.py` (1,215 LOC) y `export.py` (1,098 LOC) concentran CRUD + lógica de negocio + parsers + export. `acero_diseno.py` (842 LOC) reimplementa pricing a mano en vez de importar el servicio compartido — síntoma de que la lógica compartida vive en routers, no en `services/`.

### 🟡 P8 — Frontend sin higiene de repo

9 archivos `.bak_*`/`.STALE_*` conviviendo en el árbol activo (`frontend/js/app.js.bak_premod2_20260616` y 3 más, `tabla-render.js.bak_*` ×2, `index.html.bak_*`/`.STALE_*` ×3) — sin `.gitignore` que los filtre porque el repo git nunca se inicializó. Cache-busting por mtime (`ESTIMASTRUCT/app.py:25-40`) es un workaround manual documentado en el propio código, sin pipeline de build/hashing real.

---

## 3. Lógica duplicada (mapa exacto, verificado)

| Lógica | Copias (`path:line`) | Riesgo |
|---|---|---|
| `base = MO+MA+matriz` y `PU = base×(1+sc/100)` inline (existiendo `pricing.calc_base`/`precio_unitario`) | `routers/export.py:57,60`; `routers/presupuestos.py:319-320,449-450`; `routers/acero_diseno.py:474-477`; `scripts_runner/import_quantities.py:225-227` | Alto — ya causó doble conteo histórico |
| `_tipo_from_clave` | `routers/presupuestos.py:73-82` y `routers/updater.py:282-288` (cuerpo idéntico) | Medio — clasificación de insumos diverge si se edita una copia |
| `_csi_sort_key` / natural-sort | `routers/bases.py:120-126`, `routers/presupuestos.py:17-23`, `scripts_runner/generate_keynotes.py:87-91` (`_csi_natural_key`) — mismo regex `\d+|\D+` en 3 archivos, pese a existir `csi_utils.py` como módulo compartido | Medio — orden CSI inconsistente entre vistas y reportes |
| "resolver sobrecosto con default 20.0" | `routers/calculos.py:14`, `routers/insumos.py:30-35`, `routers/partidas.py:79-86`, `routers/acero_diseno.py:472`, `routers/portal_publish.py:60,200` — 5 implementaciones independientes | Bajo — default mágico repetido, pero divergencia posible si se cambia en un solo sitio |
| Catálogo `recursos` | `estimacion.db` (ORM, tabla `recurso`) y `estimastruct.db` (Flask, tabla `recursos`) | Alto — P3 |

---

## 4. Cuellos de botella de rendimiento (verificados)

1. **N+1 real** — `routers/presupuestos.py:517`: `db.query(Partida).filter(...).count()` ejecutado **dentro** del loop `for pa in all_partidas` (línea 492) del endpoint de reasignación de capítulos. O(N) queries de COUNT por cada partida movida.
2. **`joinedload` exclusivo, cero `selectinload` en todo el repo** — con colecciones anidadas de 3 niveles (`capitulos→partidas→insumos`) en `routers/calculos.py:47-48`, `routers/export.py:344-346,484,864` (repetido 3 veces en el mismo archivo), `routers/presupuestos.py:544`. Un solo `LEFT OUTER JOIN` de 3 niveles multiplica filas — con presupuestos grandes puede devolver decenas de miles de filas redundantes por petición.
3. **Relaciones sin `lazy=` explícito** en `models.py:27,83,120` — cae en `lazy="select"` por default; cualquier endpoint que itere una colección sin haberla precargado con `joinedload`/`selectinload` dispara N+1 silencioso fila a fila.
4. **`.count()` redundante fuera de loop** (no N+1 pero evitable con agregación): `routers/partidas.py:230,240`, `routers/diagnostics.py:76-77`, `routers/insumos.py:105`, `routers/updater.py:375` (este último dentro de loop de import masivo de fichas Excel).
5. **Cache-busting por mtime en cada request** (`ESTIMASTRUCT/app.py:25-40`, `_current_asset_version()`) — glob+stat de todo `js/*.js`/`css/*.css` por request; trivial hoy, correcto sería memoizar con TTL.

---

## 5. Riesgos de escalabilidad

| Riesgo | Detonante | Mitigación |
|---|---|---|
| SQLite mono-escritor + WAL | Segundo usuario concurrente (portal) | El ORM hace el swap a Postgres barato **si** primero se elimina el `sqlite3` crudo de Flask |
| 3 BDs vivas fuera del repo, sin backup versionado | Corrupción de una sin que se note en la otra | Consolidar catálogo `recursos` en una sola BD (P3); automatizar rotación/purga de los 13+ `.bak_*` en `C:\EstimaStruct\data\` |
| `create_all` como mecanismo principal de esquema | Columna nueva con cambio de tipo/constraint sobre columna existente | Generar migraciones Alembic incrementales reales, no solo el baseline |
| Frontend monolito sin build (7,010 LOC activo, 9 backups mezclados) | Cada módulo nuevo crece `app.js`/`calculo-estructural.js` a mano | `calculo-estructural.js` ya es el archivo más grande (3,263 LOC) — modularizar antes de que crezca más |
| API sin auth expuesta solo por `localhost` | Exposición futura por LAN/Tailscale/portal multiusuario | Auth mínima + CORS restringido antes de exponer (P4) |

---

## 6. Estrategia de refactor (fases, sin cambiar funcionalidad)

### FASE A — Red de seguridad
1. `git init` + commit inicial (si aún no se ejecutó) para poder revertir con confianza.
2. Tests de caracterización de `pricing.calc_base`/`precio_unitario`/`recalcular_partida` fijando el comportamiento actual — ver §7.3. Sin esto, cualquier fase posterior no es verificable.

### FASE B — Una sola fuente de precio
3. Reemplazar los 5 sitios de fórmula inline (`export.py:57,60`; `presupuestos.py:319-320,449-450`; `acero_diseno.py:474-477`; `import_quantities.py:225-227`) por `pricing.calc_base`/`precio_unitario`/`recalcular_partida`. `acero_diseno.py` requiere decisión previa: ¿debe incluir `unitario_matriz` o es semántica distinta (costo de acero puro)? Escalar antes de tocar.
4. Mover `_tipo_from_clave` y `_csi_sort_key`/`_csi_natural_key` al módulo ya existente `csi_utils.py`; un solo import en los 5 sitios que hoy la reimplementan.
5. Unificar las 5 implementaciones de "resolver sobrecosto default 20.0" en una sola función de `pricing.py` o `config.py` (`SOBRECOSTO_DEFAULT`).

### FASE C — Consolidar bases de datos
6. Decidir destino de `estimastruct.db`/tablas `recursos`/`actividades`/`unidades`: si la UI de matrices de Flask sigue viva, servirla desde FastAPI contra `estimacion.db`; si es legacy, archivar y borrar rutas Flask correspondientes.
7. Automatizar rotación de `.bak_*` en `C:\EstimaStruct\data\` (ej. conservar últimos N, purgar el resto por cron/script) — hoy crecen sin límite.
8. Borrar o mover a `_LEGACY/` las copias stale dentro del repo (`backend/estimacion.db`, `ESTIMASTRUCT/estimastruct.db`, `estimastruct.db.STALE_20260712`) — confunden qué BD es la viva.

### FASE D — Descomponer god routers
9. `diseno_estructural.py` (1,215 LOC) → separar CRUD / sismo / suelos / parsers ETABS en módulos bajo `services/`, siguiendo el patrón ya usado por `partidas_bridge.py`.
10. `export.py` (1,098 LOC) → separar generación XLSX de la lógica de agregación de costos (que hoy reimplementa pricing, ver P1).
11. `acero_diseno.py` → una vez resuelto P1/#3, debe consumir `pricing.py` en vez de reimplementar bucketing.

### FASE E — Esquema y datos
12. Migraciones Alembic incrementales reales por cada cambio de columna (no solo el baseline) — `alembic revision --autogenerate` contra `models.py` en vez de depender de `create_all`.
13. Higiene de repo: mover los 9 `.bak_*`/`.STALE_*` de `frontend/` y `ESTIMASTRUCT/templates/` fuera del árbol activo (a `_LEGACY/` o borrarlos si el historial ya vive en git tras FASE A).

### FASE F — Infraestructura
14. `selectinload` en vez de `joinedload` en las queries de 3 niveles (`calculos.py:47-48`, `export.py:344-346,484,864`, `presupuestos.py:544`) — mismo resultado, sin explosión cartesiana.
15. Fix del N+1 de `presupuestos.py:517` — un solo `GROUP BY` antes del loop, igual que el patrón ya bueno de `listar()`.
16. Auth mínima (API key local o token) + CORS restringido a `localhost:5000` antes de exponer por LAN/Tailscale (P4).

---

## 7. Código de referencia (production-grade, no aplicado)

### 7.1 Fuente única de precio — cerrar los 5 sitios inline (FASE B)

```python
# routers/export.py — reemplazar líneas 57,60
from backend.services.pricing import calc_base, precio_unitario

base = calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz)
pu = precio_unitario(base, sobrecosto)

# routers/acero_diseno.py — reemplazar 474-477 (TRAS decidir si aplica unitario_matriz)
from backend.services.pricing import calc_base, precio_unitario

base = calc_base(costo_mo, costo_ma, unitario_matriz or 0)
pu = precio_unitario(base, sobrecosto)
```

### 7.2 CSI helpers unificados en `csi_utils.py` (FASE B)

```python
# backend/csi_utils.py — ya existe; agregar/consolidar aquí, un solo import en los 5 sitios
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

Reemplaza: `routers/presupuestos.py:17-23,73-82`, `routers/updater.py:282-288`, `routers/bases.py:120-126`, `scripts_runner/generate_keynotes.py:87-91`.

### 7.3 Test de caracterización — invariante de precio (FASE A)

```python
# tests/test_pricing_invariants.py
from decimal import Decimal
from backend.services.pricing import calc_base, precio_unitario

def test_calc_base_suma_los_tres_componentes():
    assert calc_base(10, 20, 7) == calc_base(Decimal("10"), Decimal("20"), Decimal("7"))
    assert float(calc_base(10, 20, 7)) == 37.0

def test_precio_unitario_aplica_sobrecosto_pct():
    assert precio_unitario(100, 20) == 120.0
    assert precio_unitario(100, 0) == 100.0

def test_acero_diseno_debe_usar_calc_base_no_reimplementar():
    """Congela el comportamiento actual de acero_diseno.py:474-477 (sin unitario_matriz)
    para detectar cuando se migre a calc_base — en ese momento este test debe actualizarse
    a propósito, no romperse por accidente."""
    # placeholder — completar con fixture real de CasoDiseno al escribir la fase A
```

### 7.4 Fix N+1 de reasignación de capítulos (FASE F)

```python
# routers/presupuestos.py — reemplazar el .count() dentro del loop (línea 517)
from sqlalchemy import func

counts = dict(
    db.query(Partida.capitulo_id, func.count(Partida.id))
      .join(Capitulo, Capitulo.id == Partida.capitulo_id)
      .filter(Capitulo.presupuesto_id == pid)
      .group_by(Partida.capitulo_id)
      .all()
)

for pa in all_partidas:
    target = capitulos_map[div]
    pa.orden = counts.get(target.id, 0)
    counts[target.id] = pa.orden + 1
    counts[old_cap_id] = counts.get(old_cap_id, 1) - 1
    pa.capitulo_id = target.id
```

### 7.5 `selectinload` en vez de `joinedload` en queries de 3 niveles (FASE F)

```python
# routers/calculos.py:47-48, export.py:344-346/484/864, presupuestos.py:544
from sqlalchemy.orm import selectinload

p = db.query(Presupuesto).options(
    selectinload(Presupuesto.capitulos)
        .selectinload(Capitulo.partidas)
        .selectinload(Partida.insumos),
).filter(Presupuesto.id == pid).first()
```

---

## 8. Qué NO tocar (está bien como está)

- **Motores puros sin ORM** (`calculo_estructural.py`, `calculo_miembro_acero.py`, `calculo_conexion_acero.py`, `calculo_sismico_choc08.py`) — patrón Request→Router→Motor→Resultado correcto, ~6,700 LOC testeables sin fricción. Solo les falta cobertura de tests.
- **`backend/services/pricing.py`** — diseño correcto (Decimal interno, docstrings forenses), el problema es adopción (P1), no el módulo en sí.
- **Alembic baseline + `create_all` para tablas aditivas** — estrategia documentada y consistente para el caso simple; falta extenderla a columnas modificadas (P6).
- **CSI como llave maestra** en todo el join Revit↔ETABS↔partidas — consistente en todo el codebase.
- **Paquete `backend/`** — `__init__.py` presente en todos los subpaquetes, imports absolutos `from backend.xxx import`, sin `os.chdir` ni `sys.path.insert` hacks (fuera de alembic/env.py y un script utilitario) — mejor de lo reportado en auditorías previas.

---

## 9. Resumen ejecutivo

| Dimensión | Nota | Un renglón |
|---|---|---|
| Diseño de dominio | 🟢 | CSI-céntrico, motores puros, `pricing.py` bien diseñado |
| Consistencia de cálculo | 🔴 | 5 sitios reimplementan la fórmula pese a existir fuente única |
| Testing | 🔴 | 0 tests, sin pytest en dependencias |
| Topología de datos | 🟠 | 3 BDs vivas fuera del repo + 18+ backups sin rotación |
| Seguridad | 🟠 | Sin auth, CORS `*` (tolerable solo local) |
| Evolución de esquema | 🟠 | Alembic configurado pero solo baseline; `create_all` como mecanismo real |
| Empaquetado backend | 🟢 | Paquete real, imports limpios — mejor que lo reportado en auditorías previas |
| Rendimiento | 🟡 | 1 N+1 confirmado + `joinedload` exclusivo en queries de 3 niveles |
| Higiene de repo | 🟡 | 18+ archivos `.bak_*`/`.STALE_*` mezclados en árboles activos |

**Primeros 3 pasos concretos:** (1) tests de caracterización de `pricing.py` (§7.3), (2) unificar los 5 sitios de fórmula inline empezando por `acero_diseno.py` (requiere decisión de negocio sobre `unitario_matriz`), (3) automatizar rotación de los 18+ backups `.bak_*`/`.STALE_*` antes de que sigan creciendo sin control.
