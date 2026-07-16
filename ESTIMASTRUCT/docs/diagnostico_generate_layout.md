# Diagnóstico — Botón pyRevit "Generate Layout" (plomería)

> **ESTADO 2026-06-03:** ✅ **Fase 1 EJECUTADA** — tie-in con `NewTakeoffFitting` (G1) + conteo de fittings (G2).
> `connect_branch_to_main` intenta takeoff primero (no rompe curva, no exige tee family); tee = fallback.
> `create_pipes_from_plan` cuenta codos+tees+takeoffs y los reporta (UI ya no dice "pendiente"). py_compile OK.
> Pendiente: Fase 2 (export cantidades → CSI 22) · Fase 3 (limpiar dead code/logging).

> **Fecha:** 2026-06-03 · **Análisis read-only.** Objetivo: reemplazar el "Generate Layout" nativo de Revit
> (auto-ruteo MEP, deprecado/removido ~Revit 2025). Verificado contra `API Stubs PyRevit`.
> **Botón:** `EstimBot.extension\EstimBot.tab\Plumbing.panel\Generate Layout.pushbutton\script.py` (2000 líneas)
> **Núcleo:** `scripts\generate_layout_core.py` (puro, IronPython+CPython) · **Test:** `tests\test_generate_layout_core.py` → **9/9 OK**.

---

## 1. Qué hace + qué consume

**Flujo:** seleccionas fixtures en Revit → infiere sistema → rutea main + ramales → crea tuberías + fittings.

| Paso | Función | Consume |
|------|---------|---------|
| 1. Selección | `get_selected_elements` / `collect_valid_families` | FamilyInstances con conectores de **plomería físicos no conectados** (excluye in-place) |
| 2. Sistema | `infer_system_options` / `choose_system` | DCW · DHW · Sanitary · Vent (del `PipeSystemType`/`MEPSystem` del conector) |
| 3. Filtro | `filter_valid_items_for_system` | conectores que matchean el sistema elegido |
| 4. Modo | `choose_execution_mode` | "Vista previa segura" o "Crear geometría real" |
| 5. Snapshots | `collect_connector_snapshots` + `collect_wall_segments` | xyz, flow, fixture units por conector + **muros** (ancla el main al perímetro) |
| 6. Plan | `build_layout_plan` (core) | main (horiz/vert anclado a muro) + ramales (drop-to-floor + floor-run) + **Ø por FU/flow** |
| 7. Crear | `create_pipes_from_plan` | `PipeType` (scored por sistema) + `PipingSystemType` (por clasificación) + `Level` |
| | | `Pipe.Create` (segmentos) · `NewElbowFitting` (codos ramal) · `BreakCurve`+`NewTeeFitting` (tie a main) |

**Salidas:** tuberías reales en el modelo + log `D:\OneDrive\Bots\Estimbot\logs\generate_layout.log`. Selecciona/zoom a lo creado.

---

## 2. Revisión contra el API (stubs) — ✅ correcto

| Llamada usada | Stub | OK |
|---------------|------|----|
| `Pipe.Create(doc, sysTypeId, pipeTypeId, levelId, startPt, endPt)` | `Plumbing\__init__.pyi:88` | ✅ |
| `PlumbingUtils.BreakCurve(doc, pipeId, ptBreak) -> ElementId` | `:377` | ✅ |
| `doc.Create.NewTeeFitting(c1, c2, c3)` | `Creation\__init__.pyi:293` | ✅ |
| `doc.Create.NewElbowFitting(c1, c2)` | `:292` | ✅ |
| `getattr(DB.MEPSystemClassification, ...)` · `PipingSystemType` | presentes | ✅ |
| compat ElementId `Value`/`IntegerValue` (Revit 2024+) | `element_id_value` maneja ambos | ✅ |

**Hallazgo clave:** existe **`doc.Create.NewTakeoffFitting(connector, curve)`** (`Creation:297`) — la API LIMPIA para tomar un ramal sobre un main **sin romper la curva**. El script usa `BreakCurve` + `NewTeeFitting` con **fuerza bruta de 6 órdenes de conectores** ("IDEA 1-5") — frágil. `NewTakeoffFitting` lo simplifica y robustece.

---

## 3. Diagnóstico — qué FALTA (priorizado)

| # | Sev | Falta / problema | Acción |
|---|-----|------------------|--------|
| **G1** | 🔴 | **Tie-in ramal→main frágil.** `connect_branch_to_main` rompe el main (`BreakCurve`) + crea tee probando 6 órdenes + `tee_routing_preflight` EXIGE un tee family cargado en las routing preferences del PipeType. Si no hay tee cargado → **todos los ramales fallan**. Es el eslabón débil del reemplazo. | Reescribir con `NewTakeoffFitting(branch_connector, main_curve)`; fallback a tee solo si takeoff no aplica |
| **G2** | 🟠 | **Fittings no se cuentan.** `create_pipes_from_plan` devuelve (created, failed, ids) pero NO el nº de codos/tees. La UI dice literal **"Fittings: pendiente"**. | Contar codos+tees, devolver en summary + alert |
| **G3** | 🟠 | **No exporta cantidades a EstimaStruct.** Crea tubería pero no vuelca longitud×Ø×sistema a partidas CSI 22 (plomería). El propósito de presupuesto queda a medias. | Export CSV (sistema, Ø, longitud) → endpoint import EstimaStruct (igual que conexiones) |
| **G4** | 🟡 | **Código muerto `tie-in-`.** `create_pipes` ajusta Ø para segmentos `tie-in-*` que el core **nunca emite** (ramales solo "drop-to-floor"/"floor-run"). | Implementar riser de tie-in o eliminar la rama |
| **G5** | 🟡 | **Alcance simplificado vs nativo.** 1 main (horiz o vert) + ramales drop+floor. Sin risers entre niveles, sin loops/redes, sin equipos, venteo no se conecta al sanitario, slope solo lineal. | Documentar como MVP; roadmap multi-main/risers si se requiere paridad |
| **G6** | 🟡 | **Logging de debug ruidoso** ("IDEA 1-5", dumps de conectores/ángulos) — útil en dev, ensucia prod. | Bajar a nivel debug / flag |
| **G7** | 🟢 | **Bien:** modo preview, transacción atómica con rollback, filtros de conector físico/sistema, fallback de PipeType, compat 2024+. | — |

---

## 4. Propósito vs estado

- **Reemplazar el Generate Layout nativo:** ✅ el núcleo (auto-rutear fixtures → main + ramales + Ø) está implementado y testeado (core 9/9). La creación de tubería funciona. **El reemplazo es viable.**
- **"Que todo funcione correctamente":** el riesgo real es **G1 (tie a main)** — sin tee family cargado, los ramales no cierran. Resolver con `NewTakeoffFitting`. Luego G2 (reporte) y G3 (presupuesto).

---

## 5. Plan para dejarlo correcto

**Fase 1 — Robustez del tie-in (G1, G2)**
1. Reescribir `connect_branch_to_main`: intentar `doc.Create.NewTakeoffFitting(branch_open_connector, main_pipe.Location.Curve)` primero. Si lanza/None → fallback al tee actual (BreakCurve+NewTeeFitting).
2. Quitar el `tee_routing_preflight` como bloqueante (pasarlo a aviso); el takeoff no depende de tee family en routing prefs.
3. Contar fittings (codos+tees+takeoffs) y devolverlos: `create_pipes_from_plan` → (created, fittings, failed, ids). UI: reemplazar "Fittings: pendiente" por el conteo real.

**Fase 2 — Puente a presupuesto (G3)**
4. Tras crear, agregar longitud por (sistema, Ø) → export CSV `S?_plumbing_latest.csv` (`sistema, diametro_mm, longitud_m`).
5. Endpoint EstimaStruct `POST /diseno/{pid}/plomeria-import-csv` → partidas CSI 22 11/22 13 con cantidad (m) — patrón igual al import de conexiones pyRevit ya hecho.

**Fase 3 — Limpieza (G4, G6)**
6. Eliminar la rama `tie-in-` muerta (o implementar el riser).
7. Encapsular el logging "IDEA/DEBUG" detrás de un flag `DEBUG`.

**No tocar (correcto):** core de planificación (testeado), modo preview, transacción atómica, scoring de PipeType.

> Bloque mínimo para "que funcione bien HOY": **Fase 1** (G1+G2) — el tie-in robusto con `NewTakeoffFitting` + conteo de fittings.
