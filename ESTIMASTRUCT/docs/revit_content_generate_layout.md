# Content Revit requerido — pyRevit "Generate Layout" (plomería PVC)

> **Fecha:** 2026-06-04 · **Revit 2027** · Librería **English = métrica** (familias `M_`, "english-metric").
> Verificado en disco: `C:\ProgramData\Autodesk\RVT 2027\Libraries\English\US\Pipe\Fittings\PVC\`.
> El botón crea tubería (`Pipe.Create`) + codos (`NewElbowFitting`) + uniones a main (`NewTakeoffFitting`→`NewTeeFitting`).

---

## 1. Qué EXIGE el script (mínimo por Pipe Type → Routing Preferences)

El script lee `pipe_type.RoutingPreferenceManager`. Si faltan estos grupos, los ramales fallan
(`tee_routing_preflight` bloquea si no hay tee/junction):

| Grupo Routing Pref. | Para qué (en el script) | Obligatorio |
|---------------------|--------------------------|-------------|
| **Segments** | el segmento de tubería (Ø + material) | ✅ |
| **Elbows** (codo) | `NewElbowFitting` + auto-ruteo de quiebres | ✅ |
| **Junctions** (Tee/Wye) | `NewTeeFitting` + `NewTakeoffFitting` (toma del ramal al main) | ✅ |
| **Transitions** (reductor) | el ramal baja de Ø respecto al main → se necesita reductor | ✅ |
| Crosses · Caps · Unions · Flanges · MultiPort | no los usa el script | opcional |

> **No hay familia Tap/Takeoff PVC** en la librería → `NewTakeoffFitting` usa la **Tee** del grupo Junctions. Correcto, no falta nada.

---

## 2. Familias PVC (English-Metric) — ya instaladas en tu disco

**Ruta base:** `C:\ProgramData\Autodesk\RVT 2027\Libraries\English\US\Pipe\Fittings\PVC\Sch 40\Socket-Type\`

### A) PRESIÓN — agua potable fría (`\Socket-Type\`)
| Familia (.rfa) | Rol Routing Pref. |
|----------------|-------------------|
| `M_Elbow - PVC - Sch 40` | Elbow (codo) ✅ |
| `M_Tee - PVC - Sch 40` | **Junction (tee)** ✅ |
| `M_Coupling Reducing - PVC - Sch 40` | **Transition (reductor)** ✅ |
| `M_Coupling - PVC - Sch 40` | Union (acople) |
| `M_Cross - PVC - Sch 40` | Cross (opcional) |
| `M_Cap - PVC - Sch 40` · `M_Plug - PVC - Sch 40` | Cap (tapón) |

### B) DWV — drenaje + sanitario + ventilación (`\Socket-Type\DWV\`)
| Familia (.rfa) | Rol |
|----------------|-----|
| `M_Bend - PVC - Sch 40 - DWV` (+ `M_Bend Long Sweep`) | Elbow (codo drenaje) ✅ |
| `M_Tee Sanitary - PVC - Sch 40 - DWV` | **Junction (tee sanitaria)** ✅ |
| `M_Wye 45 Deg - PVC - Sch 40 - DWV` (+ Reducing/Double) | Junction (yee — preferida en drenaje) |
| `M_Reducer - PVC - Sch 40 - DWV` | **Transition (reductor)** ✅ |
| `M_Tee Vent` · `M_Ell Vent - PVC - Sch 40 - DWV` | ventilación |
| `M_Cleanout Two-Way - PVC - Sch 40 - DWV` | registro (cleanout) |
| `M_Trap P - PVC - Sch 40 - DWV` | sifón de fixture |
| `M_Cap` · `M_Plug` · `M_Coupling` (- DWV) | cierre/acople |

---

## 3. Qué tubería por sistema

| Sistema | Clasificación Revit | Tubería | Pipe Segment | Codo | Junction |
|---------|---------------------|---------|--------------|------|----------|
| **Potable (agua fría)** | Domestic Cold Water | PVC presión | `PVC - Sch 40` | M_Elbow Sch 40 | M_Tee Sch 40 |
| **Drenaje** | Sanitary (o Storm/Other) | PVC-DWV | `PVC - Sch 40 - DWV` | M_Bend DWV | M_Wye / M_Tee Sanitary |
| **Sanitario (aguas negras)** | Sanitary | PVC-DWV | `PVC - Sch 40 - DWV` | M_Bend DWV | M_Tee Sanitary DWV |
| Ventilación | Vent | PVC-DWV | `PVC - Sch 40 - DWV` | M_Ell Vent | M_Tee Vent |
| Agua caliente | Domestic Hot Water | **CPVC** (PVC no resiste) | — | — | — |

> **CPVC NO está en la librería** (Fittings: Carbon Steel, Gray Iron, Malleable Iron, PVC, Steel — sin CPVC).
> Si harás agua caliente, baja CPVC aparte (Autodesk online / fabricante). El script igual funciona; solo necesita
> un Pipe Type con sus routing prefs.

---

## 4. Dónde encontrar las familias

1. **Ya las tienes** (PVC): la ruta de §2. Cargar con **Insert → Load Family** → navegar ahí.
2. **Autodesk online:** Insert → **Load Autodesk Family** (descarga del cloud por categoría/material).
3. **CPVC / catálogo real LatAm:** sitio del fabricante (Amanco/Durman/Pavco) — bajan familias Revit con el
   catálogo de Ø reales (SDR potable, sanitario). Útil para presupuesto exacto.

---

## 5. CRÍTICO — cargar NO basta (3 pasos)

El script falla si solo cargas las .rfa sin configurarlas. Por cada sistema:

1. **Cargar** las familias (Insert → Load Family) al proyecto `.rvt`.
2. **Crear un Pipe Type** por sistema (ej. `PVC - Presión`, `PVC - DWV`): Edit Type → Duplicate.
3. **Asignar Routing Preferences** del Pipe Type (Edit Type → **Routing Preferences**):
   - Segment → PVC Sch 40 (o DWV)
   - Elbow → M_Elbow / M_Bend
   - **Junction → M_Tee / M_Tee Sanitary / M_Wye**  ← sin esto, los ramales NO cierran
   - Transition → M_Coupling Reducing / M_Reducer
4. **Piping System Types** (Domestic Cold Water, Sanitary, Vent) deben existir en el proyecto — vienen en el
   template MEP. El script matchea por `SystemClassification`.

> **Checklist mínimo para que el botón funcione, por sistema:** 1 Pipe Type + Segment + Elbow + **Tee(Junction)** + Reducer, todo asignado en Routing Preferences. Con eso, `Generate Layout` rutea main + ramales + tees/takeoffs.

---

## 6. Resumen de carga rápida (lo mínimo)

**Potable:** `M_Elbow`, `M_Tee`, `M_Coupling Reducing` (PVC Sch 40) → Pipe Type "PVC-Presión" → sistema Domestic Cold Water.
**Drenaje + Sanitario:** `M_Bend`, `M_Tee Sanitary` (o `M_Wye 45`), `M_Reducer` (PVC Sch 40 DWV) + `M_Cleanout`, `M_Trap P` → Pipe Type "PVC-DWV" → sistema Sanitary.
**Vent (si aplica):** `M_Ell Vent`, `M_Tee Vent` → sistema Vent.
