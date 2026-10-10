# Scripts — EstimaStruct

> Referencia de todos los scripts en `backend/scripts_runner/`. Se corren offline (no via HTTP) o via `POST /presupuestos/{id}/scripts/{nombre}`.
> Ver `architecture.md §4.3` para el componente Scripts Runner en el contexto del sistema.

---

## RAG — embed_architecture.py

**Propósito:** Chunk `docs/architecture.md` por sección §N → embed con nomic-embed-text → insert en `arch_chunks` (pgvector).

```bash
# Re-embed completo (correr tras cada cambio en architecture.md)
python backend/scripts_runner/embed_architecture.py --wipe

# Solo agregar sin limpiar (si architecture.md creció)
python backend/scripts_runner/embed_architecture.py

# Proyecto diferente
python backend/scripts_runner/embed_architecture.py --arch docs/otra.md --project nombre
```

**Tabla destino:** `arch_chunks` en PostgreSQL `estimastruct`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `section_ref` | TEXT | §N del chunk (ej. `§5.2`) |
| `section_title` | TEXT | Título completo de la sección |
| `content` | TEXT | Texto crudo del chunk (≤ 600 palabras) |
| `token_count` | INT | Palabras aproximadas |
| `embedding` | vector(768) | nomic-embed-text 768d |
| `project` | TEXT | `estimastruct` (namespace) |

**Query semántico (SQL):**

```sql
-- Top-3 chunks más relevantes para una query embedding
SELECT section_ref,
       section_title,
       LEFT(content, 400) AS preview,
       1 - (embedding <=> '[...vector_768d...]'::vector) AS score
FROM   arch_chunks
WHERE  project = 'estimastruct'
ORDER  BY embedding <=> '[...vector_768d...]'::vector
LIMIT  3;
```

**Embed query en Python:**

```python
import json, urllib.request

def embed_query(text: str) -> list[float]:
    payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())["embedding"]

vec = embed_query("¿cómo conecta pyRevit con EstimaStruct?")
# → usar vec en query SQL arriba
```

**Estado:** 28 chunks (§0..§10, sub-chunked por `###` cuando > 600 palabras). Último embed: 2026-07-21.

---

## Auditoría Keynotes — audit_keynotes.py + run_audit_pipeline.py

**Propósito:** Audita keynotes del modelo Revit contra catálogo PG + fichas JSON. Produce CSV + XLSX con GREEN/RED por elemento.

```bash
python backend/scripts_runner/run_audit_pipeline.py
```

Output: `audit_keynotes_report.csv`, `audit_keynotes_report.xlsx` (4 hojas: Resumen, Auditoría, REDs, Cantidades).

---

## Keynotes — generate_keynotes.py + generate_keynotes_catalog.py

**Propósito:** Genera `keynotes.txt` para Revit desde catálogo PG (primary) + fichas JSON (fallback).

```bash
python backend/scripts_runner/generate_keynotes.py
python backend/scripts_runner/generate_keynotes_catalog.py
```

---

## Fichas v1.3 — generate_fichas_v13.py

**Propósito:** Genera `fichas_v1.3.live.json` (375 fichas = 359 PG + 16 JSON-only).

```bash
python backend/scripts_runner/generate_fichas_v13.py
```

---

## TypeMarks Revit — revit_marks_master.py

**Propósito:** Script maestro para setear TypeMarks en Revit (muros, pisos, puertas, ventanas, MEP) via MCP. Usa `csi_to_codigo.json` como mapping.

```bash
python backend/scripts_runner/revit_marks_master.py
```

---

## Dump Revit — revit_dump_snippet.py + revit_full_dump_snippet.py

**Propósito:** IronPython snippets que corren en Revit via MCP `execute_revit_code`. Produce `model_audit_raw.json` y `project_full_dump.json` (full_v2: 2.37 MB, 2344 instancias, 719 materiales con texturas).

No correr como script standalone — ejecutar via MCP.

---

## Migración SQLite → Postgres — migrate_sqlite_to_postgres.py

**Propósito:** Migra `estimacion.db` SQLite → PostgreSQL estimastruct. Ya corrido 2026-07-19.

```bash
python backend/scripts_runner/migrate_sqlite_to_postgres.py
```

---

## Import Cantidades — import_quantities.py

**Propósito:** Lee CSV de Revit schedules (01-99, T01-T04) y actualiza cantidades en partidas de una obra en PG.

Llamado via `POST /revit-mcp/obras/{id}/import-quantities` o desde botón pyRevit.

---

## Sync Auditoría — sync_audit_colors.py + sync_colores_from_obra.py

**Propósito:** Aplica colores GREEN/RED del CSV de auditoría a la BD (sync estado visual).

---

## Matches Catálogo v1.2 — identify_v12_green_name_matches.py + apply_v12_green_matches_to_db.py

**Propósito:** Identifica partidas en fichas v1.2 con match por nombre (no CSI) y aplica las coincidencias GREEN a la BD.

---

## Build Material Contract — build_material_replacement_contract.py

**Propósito:** Genera contrato de materialización (materiales Revit → partidas EstimaStruct) para una obra.

---

## Validate Units — validate_units.py

**Propósito:** Verifica consistencia de unidades en catálogo (m², pza, ml, etc.) contra fichas.

---

## Generate Complex — generate_complex_selectors.py + generate_complex_correlations.py

**Propósito:** Genera selectores y correlaciones para elementos compuestos (compound walls/floors) en el catálogo.

---

## Canon Snapshot — build_template_canon_snapshot.py + add_scripts_tab_to_canon.py

**Propósito:** Genera snapshot del template canónico y agrega pestaña Scripts al XLSX canon.

---

## MEP Run Planning — mep_run_core.py (pyrevit/scripts/)

**Propósito:** Núcleo puro (CPython + IronPython 2.7) de planificación on-demand de un tramo MEP punto-a-punto. Sibling de `generate_layout_core.py` (layout completo desde conectores) y `generate_hvac_layout_core.py` (ductos) — mismo patrón, sin dependencias de Revit API, testeable con pytest normal.

Función principal: `create_mep_run(system, level, from_point, to_point, norma='HN'|'UPC', material=None, fixture_units=0.0, flow=0.0, level_elevation_mm=None, offset_mm=None, existing_pipes_mm=None) -> LayoutPlan`

Reglas codificadas (fuente: `00 Notes/plans/2026-08-29_mep-tuberias-estandares-params.md`, CICLO 1):
- Diámetro por WSFU/DFU vía `generate_layout_core.calculate_pipe_diameter_mm` (reuso, no duplicado).
- Potable (DCW/DHW): bajo losa, offset configurable por nivel (default -150mm).
- Sanitario (DWV): pendiente 1/4"/pie = 20.8 mm/m hacia el punto de colector (`to_point`).
- Trampa (sello 75mm, banda 2-4") + vent (mín. 1/2 diámetro de drenaje, piso duro 1-1/4") en el extremo de fixture de tramos sanitarios.
- Clash detection contra dataset existente (distancia < suma de radios, o cruce de ejes en planta) — reporta, no excepciona.
- Regla dura potable-arriba-de-drenaje: en cruce con sanitario, la rama potable se levanta (offset vertical mínimo 50mm), registrado en `plan.clash_report`.
- Material default por clasificación vía ASTM (D2241/D2846/D2665) con flag `uso_final` (presion/gravedad) — ver hallazgo SDR-vs-Sch40-DWV de CICLO 1.

```bash
D:/LLM/python/python.exe -m pytest pyrevit/scripts/test_mep_run_core.py -v
```

**Estado:** CICLO 2 (2026-08-29) — 19/19 tests verdes, sin wiring a Revit.

### CICLO 3A — pushbutton "Crear Red MEP" (2026-08-29, goal-21479)

Nuevo botón en `pyrevit/EstimBot.extension/EstimBot.tab/Plumbing.panel/Crear Red MEP.pushbutton/` (`bundle.yaml` + `script.py`). Wirea `create_mep_run()` a creación real de pipes en el documento activo, reusando (import via `imp.load_source`, sin duplicar) `create_pipe_segment`, `get_pipe_type`, `get_piping_system_type_id` y helpers de `Generate Layout.pushbutton/script.py`.

- **Automatización E2E** (mismo patrón `ESTIMBOT_GL_*` de Generate Layout): `ESTIMBOT_MRP_AUTOMATION`, `_SYSTEM`, `_LEVEL`, `_NORMA`, `_MATERIAL`, `_MODE` (`preview` | `crear geometria real`), `_FROM`/`_TO` (`"x,y,z"` mm, `z` vacío = auto-derivar por nivel), `_DATASET_DIR`, `_FIXTURE_UNITS`, `_FLOW`, `_CONFIRM`. Se dispara sin click de ribbon con `exec(compile(open(script.py).read(), script.py, "exec"), {"__name__": "__main__"})` — **ojo:** `exec(open(...).read())` a secas NO alcanza (el `__name__` del sandbox de `revit_execute_code` no es `"__main__"`), hay que pasar el dict de globals explícito.
- **Dataset `mep_metadata/<obra>/pipes.json`:** los campos `start`/`end` `x`/`y`/`z` son coordenadas internas de Revit en **pies**, sin sufijo `_ft` en el nombre (verificado 2026-08-29 contra el modelo vivo Valle de Angeles2: `element_id 2545595` coincide exacto). `load_existing_pipes_mm()` en el nuevo script convierte `*304.8` antes de pasarlo a `find_clashes`; si se reusa este dataset en otro lado, replicar la conversión.
- **Lock de escritura** `D:/OneDrive/Bots/Estimbot/revit_write.lock`: se adquiere/libera alrededor de la transacción de creación real (no en preview).
- **E2E corrido 2026-08-29 contra Valle de Angeles2 (bridge ya abierto, sin relanzar):**
  - Preview (`Domestic Cold Water`, nivel `Terraza 1`, tramo de 3048mm): detectó `axis_crossing` real contra `element_id 2547084` (Sanitary) y aplicó la corrección potable-sobre-drenaje (`lift_mm=50.0`) — regla dura respetada, sin colisión bloqueante. Log: `D:/OneDrive/Bots/Estimbot/logs/mep_run.log`.
  - Escritura real: **BLOQUEADA** — `DB.Transaction(doc, ...).Start()` lanza `"Starting a new transaction is not permitted"` de forma persistente (confirmado con 3 intentos diagnósticos separados por >20s cada uno). Ventana `EstimBot - Generate Layout` abierta en el escritorio en el momento del intento — indicio de Worker B (corre en paralelo sobre el mismo documento, per spec) con una transacción propia sin cerrar. No se forzó ni se reintentó indefinidamente (protocolo de crash de la spec).
  - **Pendiente para el próximo intento:** re-correr el mismo comando de creación real (`ESTIMBOT_MRP_MODE=crear geometria real`) una vez el documento esté libre de transacciones ajenas; confirmar con el diagnóstico `DB.Transaction(doc,"diag").Start()` antes de reintentar.
- **Hallazgo colateral (no bloqueante, pre-existente en `generate_layout_core.resolve_piping_system_classification`):** labels con sufijo numérico como `"Sanitary 29"` no matchean el lexer de clasificación y caen a `DomesticColdWater` por default — el texto de detalle de clash queda mal etiquetado (`"... (DomesticColdWater)"` para un pipe sanitario real), aunque `enforce_potable_over_drainage` sigue funcionando porque compara contra el string crudo (`"sanitary" in detail.lower()`), no contra la clasificación resuelta. Cosmético, no se tocó (fuera del scope de este ciclo).
- Tests: `D:/LLM/python/python.exe -m pytest pyrevit/scripts/test_mep_run_core.py -v` → 19/19 verdes (sin cambios respecto a CICLO 2).

### CICLO 3B — bloqueo confirmado, ventana huérfana identificada (2026-08-29, goal-21480)

Worker B (goal-21480) reprodujo el mismo bloqueo de CICLO 3A de forma independiente: `DB.Transaction(doc,"diagnostic-probe-goal21480").Start()` sigue lanzando `"Starting a new transaction is not permitted"`. `D:/OneDrive/Bots/Estimbot/revit_write.lock` **no existe** (nadie tiene el lock formal) — la causa es la ventana WPF huérfana `EstimBot - Generate Layout` (900x600) que sigue abierta en el desktop reteniendo el contexto de la API en modal state, no una transacción con lock formal tomado.

Intento de cierre no destructivo con `win_focus` + `win_keys("esc")` no tuvo efecto. Intento con `win_keys("alt+f4")` **no aterrizó en la ventana objetivo** (el foco reportado por `win_focus` no coincidía con el foco real de teclado) y en su lugar disparó el diálogo nativo `Shut Down Windows` de Windows — cancelado de inmediato con `esc`, sin apagado real. **Lección para próximos ciclos: no usar atajos globales (`alt+f4`, `win+...`) para cerrar ventanas ajenas sin confirmación visual — usar `win_click` sobre el botón X con coordenadas verificadas, o esperar a que el proceso dueño la cierre.** Detalle completo: vault `02 Worklog/Tareas/2026-08-29_mep-ciclo3b-red-completa-bloqueo.md`.

Nota de ruta: el repo real de `mep_run_core.py` vive en `D:/GitHub/EstimBot/ConsuConstructEstimBot/pyrevit/scripts/`, NO bajo `ESTIMASTRUCT/` — la spec del ciclo lo referencia como `pyrevit/scripts/mep_run_core.py` relativo a la raíz del repo EstimBot.

Pendiente sin cambios de CICLO 3A: liberar la ventana huérfana, confirmar con el diagnóstico de transacción, y recién ahí ejecutar DHW+Vent, copia de casa, clash detection global y dump `post_cycle3b/`.

---

## Pipe Match — inventory / match / preview (pyrevit/scripts/, goal-21516)

**Propósito:** Reutilizable IronPython 2.7 de auditoría pipe↔fitting: snapshot del documento vivo y match 1-a-1 contra el dataset dorado (`development/mep_metadata/<obra>/pipes.json` + `fittings.json`) por category, family, type, system, material, diameter, level — con detalle de connectors, length y placement (tolerancias configurables). READ-ONLY, no toca el modelo.

Tres scripts (mismo patrón dual CPython/IronPython 2.7 de `mep_run_core.py`):

| Archivo | Rol | Corre en |
|---|---|---|
| `pipe_match_core.py` | Motor puro de match + comparación de detalle + `preview_text()` | CPython (tests) e IronPython |
| `pipe_match_inventory.py` | Dump vivo de pipes (`OST_PipeCurves`) y fittings (`OST_PipeFitting`) al schema del dataset dorado | Dentro de Revit (bridge `:48884`, `revit_execute_code`) |
| `pipe_match_preview.py` | Live snapshot + match contra el plan + report JSON y texto | Dentro de Revit (bridge `:48884`) |

**Match key (pipes):** `(category, family_name, type_name, system_label, material, diameter_mm, level)`.
**Match key (fittings):** `(category, family_name, type_name, level)`.
**Detalle post-match:** `connector_count`, `open_connectors`, `length_ft` (tolerance 0.5 ft), `start/end placement` y `placement` (tolerance 1.0 ft). Diferencias dentro de tolerancia = nota, no falla.

**Schema de inventario** = idéntico al dataset dorado: coordenadas/`Connection origin` en **pies Revit crudos** (convertir `*304.8` para mm en otro consumidor), `diameter_mm` derivado de radio de conector o atributo `Diameter`, `element_id` = `int(Id.ToString())` (nunca `.IntegerValue`, Revit 2024+).

**Tests (CPython, sin Revit):**

```bash
D:/LLM/python/python.exe -m pytest pyrevit/scripts/pipe_match_core_test.py -v
```

**Verificado 2026-08-30 (goal-21516):** 15/15 tests verdes contra el dataset dorado `valle_de_angeles2` (45 pipes, 22 fittings) — self-match perfecto, missing/extra/diameter/level/system/length detectados, drift dentro de tolerancia no reportado. Parsing OK de los 3 scripts.

### Verificación LIVE contra Valle de Angeles2 (2026-08-30, goal-21516)

Bridge `:48884` relanzado (Revit había muerto; `revit_mcp_ensure(model_path=...)` canon), doc `Proyecto Apartamento Valle de Angeles2`:

- **Inventario live:** 45 pipes / 22 fittings → `valle_de_angeles2/live_pipes.json` + `live_fittings.json` (prefijo `live_` para no pisar el dorado). Element IDs idénticos al plan (p.ej. pipe 2545595, fitting 2545604).
- **Preview live vs plan:** `matched=67 unmatched_live=0 unmatched_plan=0 field_mismatches=22` → `valle_de_angeles2/pipe_match_preview.json`. Los 22 field-mismatches son TODOS fittings y TODOS por `connector_count: plan=0 live=2` — el dump dorado de fittings no persistió conectores (gap de datos del PLAN, no defecto live; la schema del dorado tenía `connectors: []`). Pipes: cero diff — diámetros/material/system/level/length/placement dentro de tolerancia.
- **Gotchas de acceso Revit 2027 descubiertos (verificado por probe live):**
  - `ELEM_FAMILY_PARAM`/`ELEM_TYPE_PARAM` via `get_Parameter(...).AsValueString()` = la ÚNICA vía para family ("Pipe Types"/"M_Elbow - Generic") y type ("Potable"/"PVC - Sanitario"/"Standard"). `LookupParameter("Family Name"/"Type Name")` devuelve NULL y `GetTypeId()`/`Symbol.Name` lanzan `AttributeError` en 2027.
  - **Caché de módulos del bridge-IronPython:** el primer `import pipe_match_inventory` en un proceso del bridge compila y REUTILIZA la primera versión del módulo — un segundo `import` tras editar el archivo ejecuta código VIEJO (campo family/type en None). Fix: `pipe_match_preview` hace `exec(source_bytes, fresh_ns)` (siempre lee disco) en vez de `import`; sentinel `_PIPE_MATCH_EMBED` suprime el auto-`main()` de inventory al embeberse.
- Tests: `D:/LLM/python/python.exe -m pytest pyrevit/scripts/pipe_match_core_test.py -v` → 15/15 verdes.
