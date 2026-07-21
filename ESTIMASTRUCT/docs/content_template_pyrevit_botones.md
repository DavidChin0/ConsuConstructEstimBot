# Template de Contenido Revit — Botones pyRevit EstimBot

> **Fecha auditoría:** 2026-07-06 · **Revit 2027** · Obra auditada en vivo: "Proyecto Apartamento Valle de Angeles2"
> Cubre los 2 botones que GENERAN elementos MEP automáticamente: **Generate Layout** (plomería) y **Conduit by Ciruit** (eléctrico).
> Objetivo: checklist de contenido que debe estar cargado en el template ANTES de correr los botones, para que no fallen.

---

## Botón 1: Generate Layout (Plumbing.panel)

**Script:** `EstimBot.tab\Plumbing.panel\Generate Layout.pushbutton\script.py` + core `D:\OneDrive\Bots\Estimbot\scripts\generate_layout_core.py`

### Qué crea
- Tubería (`Pipe.Create`) ruteando desde fixtures existentes hasta un main.
- Codos (`NewElbowFitting`), Tees/Takeoffs (`NewTeeFitting`/`NewTakeoffFitting`) en los puntos de unión al main.

### Qué NO crea (prerequisito, debe existir ANTES)
- Los **fixtures de plomería** (aparatos sanitarios) con sus conectores de tubería ya asignados al sistema correcto (Sanitary/DomesticColdWater/DomesticHotWater/Vent). El botón conecta fixtures existentes, no los coloca.

### Prerequisito de contenido — por Pipe Type, 4 grupos de Routing Preferences obligatorios

El script lee `pipe_type.RoutingPreferenceManager`. Si falta un grupo, el ramal falla:

| Grupo | Para qué | Obligatorio |
|-------|----------|--------------|
| **Segments** | segmento de tubería (Ø + material) | ✅ |
| **Elbows** | `NewElbowFitting` en quiebres | ✅ |
| **Junctions** (Tee/Wye) | `NewTeeFitting` + `NewTakeoffFitting` (toma del ramal) | ✅ |
| **Transitions** | reductor cuando el ramal baja de Ø | ✅ |

No hay lookup de familia por NOMBRE hardcodeado — el script solo exige que exista **al menos 1 PipeType con los 4 grupos completos**, y el usuario lo elige de una lista al correr el botón. El `SystemClassification` se matchea contra el Piping System Type del proyecto (viene del template MEP estándar: Sanitary, Domestic Cold Water, Domestic Hot Water, Vent, etc. — no hay que crearlos, ya vienen).

### Familias necesarias por sistema (para armar los Routing Preferences)

Librería: `C:\ProgramData\Autodesk\RVT 2027\Libraries\English\US\Pipe\Fittings\PVC\Sch 40\`

| Sistema | Pipe Segment | Elbow | Junction (Tee) | Transition (reductor) |
|---------|---------------|-------|-----------------|--------------------------|
| Potable (agua fría) | `PVC - Sch 40` | `M_Elbow - PVC - Sch 40` | `M_Tee - PVC - Sch 40` | `M_Coupling Reducing - PVC - Sch 40` |
| Drenaje/Sanitario | `PVC - Sch 40 - DWV` | `M_Bend - PVC - Sch 40 - DWV` | `M_Tee Sanitary - PVC - Sch 40 - DWV` (o `M_Wye 45 Deg`) | `M_Reducer - PVC - Sch 40 - DWV` |
| Ventilación | `PVC - Sch 40 - DWV` | `M_Ell Vent - PVC - Sch 40 - DWV` | `M_Tee Vent` | — |
| Agua caliente | **CPVC** (no está en librería estándar, bajar de fabricante) | — | — | — |

Detalle exhaustivo de cada familia (rutas exactas, roles secundarios como Cross/Cap/Union): ver
D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\docs\revit_content_generate_layout.md

### ✅ Auditoría en vivo (obra Valle de Angeles, 2026-07-06) — Pipe Types

| Pipe Type | Segments | Elbows | Junctions | Transitions | Estado |
|-----------|----------|--------|-----------|-------------|--------|
| PVC - Sanitario | 1 | 1 | 1 | 1 | ✅ COMPLETO |
| Potable | 1 | 1 | 1 | 1 | ✅ COMPLETO |
| CPVC | 1 | 2 | 2 | 2 | ✅ COMPLETO |
| PVC Normal | 1 | 1 | 1 | 1 | ✅ COMPLETO |

**Piping System Types presentes:** Sanitary, Domestic Cold Water, Domestic Hot Water, Vent, Hydronic Supply/Return, Fire Protection (Wet/Dry/Pre-Action/Other), Other — set completo del template MEP, nada que agregar.

**Veredicto: Generate Layout está 100% listo en esta obra.** (El diagnóstico 2026-07-04 de bugs de tee/takeoff/duplicados ya fue corregido en el código — ver `project_generate_layout_plumbing.md`.)

---

## Botón 2: Conduit by Ciruit (Electrical.panel)

**Script:** `EstimBot.tab\Electrical.panel\Conduit by Ciruit.pushbutton\script.py` (nombre interno `PYR_S9`)

### Qué crea
- Conduit troncal (`Conduit.Create`) por circuito eléctrico real, con ramales verticales+horizontales desde cada dispositivo hasta el troncal.
- Codos (`NewElbowFitting`) y Tees (`NewTeeFitting`) en las uniones.
- Cajas de dispositivo (2x4) en tomas/switches/data/comm/seguridad/incendio/nurse call/teléfono.
- Cajas octogonales/redondas en luminarias.
- (Opcional) Parámetros de trazabilidad en el Conduit: `CONS_CircuitId`, `CONS_CircuitName`, `CONS_Panel`, `CONS_SourceElementId`, `CONS_SourceCategory` — solo si existen como parámetro compartido/de proyecto; si no existen, el script los omite en silencio (no falla).

### Qué NO crea (prerequisito, debe existir ANTES)
- **Los dispositivos eléctricos ya colocados Y circuiteados** (circuito eléctrico REAL de Revit — Electrical Systems, no solo un parámetro de texto). Sin `ElectricalSystem` real asignado, el elemento se salta (`skipped_uncircuited`). Categorías que reconoce: Aparatos eléctricos, Dispositivos de iluminación, Luminarias, Equipos eléctricos, Dispositivos de comunicación/datos/seguridad/incendio/nurse call/teléfono.
- **Niveles** ya creados (para asignar el conduit al nivel correcto).

### Prerequisito de contenido — 3 elementos que el usuario elige al correr el botón

| Elemento | Requisito | Cómo lo busca el script |
|----------|-----------|--------------------------|
| **Conduit Type** | Al menos 1 definido en el proyecto | Lista directa de `ConduitType`, cualquiera sirve |
| **Caja de dispositivo (2x4)** | Familia/tipo que contenga palabra de caja (`box`/`caja`/`junction`/`registro`/`conexiones`/`conexion`/`device box`/`pull box`) **Y** un término de 2x4 (`2x4`, `2 x 4`, `rectangular`, `device`, `carga`, `sin carga`, `conexiones`) — **Y NO contenga** `switch/interruptor/tomacorriente/receptacle/outlet/duplex/gfci/lighting fixture/panel/tablero` | `find_box_symbols()` + `is_box_symbol_match()` |
| **Caja octogonal/redonda** | Familia/tipo que contenga palabra de caja **Y** término octogonal (`oct`, `octagonal`, `octogonal`, `round`, `redonda`, `hexagonal`, `conexiones`) — mismas exclusiones | igual que arriba |

Ambas cajas son **opcionales** — si no hay match, el script avisa y continúa sin colocarlas (no bloquea el conduit).

### 🔴 Auditoría en vivo (obra Valle de Angeles, 2026-07-06) — GAP ENCONTRADO

**Conduit Types:** ✅ presentes — Rigid Nonmetallic Conduit (RNC Sch 40/Sch 80), Rigid Metal Conduit (RMC), Electrical Metallic Tubing (EMT). Listo.

**Cajas — NINGUNA familia cargada matchea el buscador del script:**

| Familia cargada actualmente | Contiene palabra de caja | Matchea 2x4 | Matchea octogonal | Por qué falla |
|---|---|---|---|---|
| `Caja de Registro` (tipos "Caja de Registro"/"Caja de Contador") | ✅ (caja+registro) | ❌ | ❌ | no contiene ningún término 2x4 ni octogonal |
| `M_Junction Boxes - Load` (100 Square 120/208/277/480) | ✅ (junction+box) | ❌ | ❌ | nombre de tipo no trae "2x4"/"rectangular"/"carga"/"conexiones" ni "octagonal"/"redonda"/"hexagonal" |
| `M_Hexagon Junction Box` (120V/208V/277V/480V) | ✅ (junction+box) | ❌ | ❌ (casi) | dice **"Hexagon"**, el script busca **"hexagonal"** — falta la terminación, no matchea por 3 letras |
| `M_Conduit Junction Box - Tee/Cross/Transition - PVC/Aluminum` | ✅ | ❌ | ❌ | son fittings de conduit (uniones), no cajas de dispositivo — tampoco traen término 2x4/octogonal |

**Resultado:** hoy, correr el botón en esta obra deja `box_2x4 = None` y `box_oct = None` — el conduit SÍ se crea, pero **ninguna caja se coloca**, sin error visible más que un alert informativo.

### Fix recomendado (elegir uno)

**Opción A — renombrar tipo existente** (más rápido, 0 familias nuevas):
- Duplicar/renombrar un tipo de `M_Hexagon Junction Box` a algo que incluya `"hexagonal"` textual, ej. `"Hexagonal 120V"`.
- Duplicar/renombrar un tipo de `Caja de Registro` o `M_Junction Boxes - Load` a algo con `"2x4"` o `"carga"`/`"sin carga"` en el nombre, ej. `"Caja de Registro - Carga 2x4"`.

**Opción B — cargar familias con nombre correcto desde el inicio** (recomendado para template limpio):
- Caja de dispositivo: `M_Caja de conexiones - Carga.rfa` / `M_Caja de conexiones - Sin carga.rfa`
- Caja octogonal: `M_Caja de conexiones simple redonda.rfa` (o variante que incluya "hexagonal" en el nombre del tipo)

(Estos nombres ya están referenciados en el texto de ayuda del propio script — sugiere que existieron/existen en otra obra o se planearon así; no están cargados en Valle de Angeles hoy.)

**Paneles eléctricos:** 1 `Electrical Equipment` presente en la obra — suficiente para que `get_panel_from_system` funcione si el circuito tiene panel asignado.

**Niveles:** 8 niveles presentes (Cimentación, Cimentaciós, Primer–Cuarto Nivel, Terraza 1/2) — listo.

---

## Checklist consolidado — qué cargar en un template nuevo

| # | Elemento | Botón | Tipo | Estado en Valle de Angeles |
|---|----------|-------|------|------------------------------|
| 1 | Pipe Type con Segments+Elbows+Junctions+Transitions, por sistema (Potable/Sanitario/Vent/Agua caliente) | Generate Layout | Configuración de proyecto | ✅ 4/4 completos |
| 2 | Familias PVC Sch 40 (presión): Elbow, Tee, Coupling Reducing | Generate Layout | Familia (.rfa) | ✅ cargadas |
| 3 | Familias PVC Sch 40 DWV (drenaje/sanitario): Bend, Tee Sanitary/Wye, Reducer | Generate Layout | Familia (.rfa) | ✅ cargadas |
| 4 | Familia CPVC (agua caliente) | Generate Layout | Familia (.rfa) | ✅ cargada (Pipe Type "CPVC" con 2/2/2 routing) |
| 5 | Piping System Types (Sanitary, DCW, DHW, Vent) | Generate Layout | Config. de proyecto (viene del template MEP) | ✅ presentes |
| 6 | Conduit Type (cualquiera) | Conduit by Ciruit | Config. de proyecto | ✅ 4 tipos presentes |
| 7 | Familia caja de dispositivo (2x4) con nombre que matchee el buscador | Conduit by Ciruit | Familia (.rfa) + naming | 🔴 **GAP** — ninguna coincide |
| 8 | Familia caja octogonal/redonda con nombre que matchee el buscador | Conduit by Ciruit | Familia (.rfa) + naming | 🔴 **GAP** — "Hexagon" ≠ "hexagonal" |
| 9 | Al menos 1 Electrical Equipment (panel) | Conduit by Ciruit | Instancia en obra | ✅ 1 presente |
| 10 | Niveles del proyecto | Ambos | Config. de proyecto | ✅ 8 presentes |
| 11 | Dispositivos eléctricos YA circuiteados (Electrical System real, no solo texto) | Conduit by Ciruit | Modelado previo | Verificar por obra — prerequisito de modelado, no de contenido |
| 12 | Fixtures de plomería YA conectados al sistema correcto | Generate Layout | Modelado previo | Verificar por obra — prerequisito de modelado, no de contenido |
| 13 (opcional) | Parámetros compartidos `CONS_CircuitId/CircuitName/Panel/SourceElementId/SourceCategory` en categoría Conduit | Conduit by Ciruit | Parámetro de proyecto | Opcional, no bloquea — mejora trazabilidad/auditoría si se agrega |

---

## Fuentes revisadas para esta auditoría

- Scripts: `Generate Layout.pushbutton\script.py` + `generate_layout_core.py`, `Conduit by Ciruit.pushbutton\script.py`
- Doc previo (más detalle de familias PVC): `revit_content_generate_layout.md` (2026-06-04)
- Memoria: `project_generate_layout_plumbing.md` (diagnóstico bugs 2026-07-04)
- Auditoría en vivo vía Revit MCP (`execute_revit_code`) sobre "Proyecto Apartamento Valle de Angeles2": Pipe Types + Routing Preferences, Conduit Types, Family Symbols (cajas), Piping System Types, Electrical Equipment, Levels.
