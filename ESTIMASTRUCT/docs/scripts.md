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
