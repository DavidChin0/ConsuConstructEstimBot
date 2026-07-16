"""Audit CSI keynotes: EVERYTHING in the Revit model that carries a keynote
(placed instances, element TYPES — placed or not —, and MATERIALS) vs the
EstimaStruct V1.2 catalog.

Reads the model dump written by execute_revit_code (model_audit_raw.json), which
now has the shape:
    {
      "keynote_table": { "<CSI key>": "<keynote text>", ... },   # project keynote .txt
      "objects":       [ {kind, id, category, family, type, keynote, type_mark, placed}, ... ]
    }
kind is one of: "type" | "material" | "instance". A keynote almost always lives on
the TYPE (or material), not the placed instance, so the previous instance-only audit
missed loaded-but-unplaced types (e.g. windows) and every material. This version keys
off the object's own keynote regardless of kind or placement.

Classification per keyed object (Director instruction 2026-07-07, option B):
  GREEN = CSI exists in catalog AND the Revit keynote TEXT matches the EstimaStruct
          ficha description (normalized similarity >= TEXT_MATCH_RATIO).
  RED   = CSI not in catalog, or keynote text diverges from the catalog description.

The keynote text comes from the project keynote table (key -> text). Accents in that
.txt are often mojibake (�); normalize_text() strips non-alphanumerics and accents
and compares by difflib ratio so mojibake does not cause false mismatches.

Keynote must be read via BuiltInParameter.KEYNOTE_PARAM (localized display name is
"Nota de clave" on Spanish Revit) — see revit_dump_snippet.py.

Output: audit_keynotes_report.csv (same canonical CSV, now also including
multicapa rows for complex assemblies: compound type + every compound layer).
"""
import json
import os
import re
import csv
import unicodedata
from difflib import SequenceMatcher
from collections import defaultdict

MODEL_DUMP = r"D:\OneDrive\Bots\Estimbot\EXPORTS\model_audit_raw.json"
FICHAS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas"
OUT_CSV = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP\audit_keynotes_report.csv"

# Similarity threshold (0..1) above which keynote text == catalog description.
TEXT_MATCH_RATIO = 0.82


def normalize_csi_key(key):
    """Same normalization as scripts_runner/import_quantities.py::_normalize_csi_key."""
    if not key:
        return ""
    raw = str(key).replace("_x000D_", "").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines and all(ln == lines[0] for ln in lines):
        raw = lines[0]
    else:
        raw = " ".join(lines)
    raw = re.sub(r"\s*\.\s*", ".", raw)
    raw = re.sub(r"\s+", " ", raw)
    parts = raw.split(" ")
    if len(parts) <= 3:
        return raw
    return " ".join(parts[:3]) + "." + ".".join(parts[3:])


def normalize_text(s):
    """Lowercase, strip accents + mojibake, keep alphanumerics only. Used for the
    fuzzy keynote-text vs catalog-description comparison."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", u"{}".format(s))
    s = u"".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def text_ratio(a, b):
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def load_catalog():
    live = os.path.join(FICHAS_DIR, "fichas_v1.2.live.json")
    canon = os.path.join(FICHAS_DIR, "fichas_v1.2.json")
    candidates = [p for p in (live, canon) if os.path.exists(p)]
    path = max(candidates, key=os.path.getmtime)
    with open(path, encoding="utf-8") as f:
        fichas = json.load(f)
    by_csi = {}
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        key = normalize_csi_key(ficha.get("csi", ""))
        if key:
            by_csi[key] = ficha
    return by_csi, path, len(fichas)


def classify_keynote(norm_key, keynote_raw, keytext, ficha_desc, ficha):
    if not ficha:
        return (
            "RED",
            u"CSI '{}' no existe en catálogo V1.2".format(keynote_raw or ""),
            0.0,
        )

    ratio = text_ratio(keytext, ficha_desc)
    if not keytext:
        return (
            "RED",
            u"CSI en catálogo pero keynote sin texto en tabla Revit",
            ratio,
        )
    if ratio >= TEXT_MATCH_RATIO:
        return (
            "GREEN",
            u"OK (texto coincide, sim={:.2f})".format(ratio),
            ratio,
        )
    return (
        "RED",
        u"texto keynote != descripción catálogo (sim={:.2f})".format(ratio),
        ratio,
    )


def audit():
    with open(MODEL_DUMP, encoding="utf-8") as f:
        model = json.load(f)

    keynote_table = model.get("keynote_table", {})
    # normalized keynote table: CSI key -> text
    ktab = {}
    for k, v in keynote_table.items():
        if k == "__error__":
            continue
        ktab[normalize_csi_key(k)] = v

    catalog, catalog_path, catalog_count = load_catalog()

    rows_out = []
    stats = defaultdict(int)

    for obj in model.get("objects", []):
        keynote_raw = obj.get("keynote")
        norm_key = normalize_csi_key(keynote_raw)
        ficha = catalog.get(norm_key)
        keytext = ktab.get(norm_key, "")
        ficha_desc = ficha.get("descripcion", "") if ficha else ""
        status, reason, ratio = classify_keynote(
            norm_key, keynote_raw, keytext, ficha_desc, ficha
        )

        stats[status] += 1
        stats["kind_" + obj.get("kind", "?")] += 1
        rows_out.append({
            "audit_scope": "base_object",
            "kind": obj.get("kind"),
            "element_id": obj.get("id"),
            "category": obj.get("category"),
            "family": obj.get("family"),
            "type": obj.get("type"),
            "placed": obj.get("placed"),
            "keynote": keynote_raw or "",
            "type_mark": obj.get("type_mark") or "",
            "keynote_text": keytext,
            "ficha_desc": ficha_desc,
            "status": status,
            "reason": reason,
            "parent_type_id": "",
            "parent_type_name": "",
            "row_role": "",
            "layer_index": "",
            "layer_function": "",
            "layer_width_mm": "",
            "material_id": "",
            "material_name": "",
            "material_keynote": "",
        })

    for comp in model.get("compound_elements", []):
        comp_type_id = comp.get("type_id")
        comp_type_name = comp.get("type_name")
        comp_category = comp.get("category_label")
        comp_placed = comp.get("placed")
        comp_type_mark = comp.get("type_type_mark") or ""
        comp_type_keynote = comp.get("type_keynote") or ""
        comp_type_norm = normalize_csi_key(comp_type_keynote)
        comp_type_ficha = catalog.get(comp_type_norm)
        comp_type_text = ktab.get(comp_type_norm, "")
        comp_type_desc = comp_type_ficha.get("descripcion", "") if comp_type_ficha else ""
        comp_status, comp_reason, _ = classify_keynote(
            comp_type_norm,
            comp_type_keynote,
            comp_type_text,
            comp_type_desc,
            comp_type_ficha,
        )

        rows_out.append({
            "audit_scope": "compound",
            "kind": "compound_type",
            "element_id": comp_type_id,
            "category": comp_category,
            "family": "",
            "type": comp_type_name,
            "placed": comp_placed,
            "keynote": comp_type_keynote,
            "type_mark": comp_type_mark,
            "keynote_text": comp_type_text,
            "ficha_desc": comp_type_desc,
            "status": comp_status,
            "reason": comp_reason,
            "parent_type_id": comp_type_id,
            "parent_type_name": comp_type_name,
            "row_role": "type",
            "layer_index": "",
            "layer_function": "",
            "layer_width_mm": "",
            "material_id": "",
            "material_name": "",
            "material_keynote": "",
        })
        stats[comp_status] += 1
        stats["kind_compound_type"] += 1

        for li, layer in enumerate(comp.get("layers", [])):
            layer_keynote = layer.get("material_keynote") or ""
            layer_norm = normalize_csi_key(layer_keynote)
            layer_ficha = catalog.get(layer_norm)
            layer_text = ktab.get(layer_norm, "")
            layer_desc = layer_ficha.get("descripcion", "") if layer_ficha else ""
            layer_status, layer_reason, _ = classify_keynote(
                layer_norm,
                layer_keynote,
                layer_text,
                layer_desc,
                layer_ficha,
            )
            rows_out.append({
                "audit_scope": "compound",
                "kind": "compound_layer",
                "element_id": "",
                "category": comp_category,
                "family": "",
                "type": comp_type_name,
                "placed": comp_placed,
                "keynote": layer_keynote,
                "type_mark": comp_type_mark,
                "keynote_text": layer_text,
                "ficha_desc": layer_desc,
                "status": layer_status,
                "reason": layer_reason,
                "parent_type_id": comp_type_id,
                "parent_type_name": comp_type_name,
                "row_role": "layer",
                "layer_index": li,
                "layer_function": layer.get("function", ""),
                "layer_width_mm": layer.get("width_mm", ""),
                "material_id": layer.get("material_id", ""),
                "material_name": layer.get("material_name", ""),
                "material_keynote": layer_keynote,
            })
            stats[layer_status] += 1
            stats["kind_compound_layer"] += 1

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "audit_scope", "kind", "element_id", "category", "family", "type", "placed",
            "keynote", "type_mark", "keynote_text", "ficha_desc", "status", "reason",
            "parent_type_id", "parent_type_name", "row_role", "layer_index",
            "layer_function", "layer_width_mm", "material_id", "material_name",
            "material_keynote",
        ])
        writer.writeheader()
        writer.writerows(rows_out)

    print("Catálogo: {} ({} fichas)".format(catalog_path, catalog_count))
    print("Tabla keynotes Revit: {} entradas".format(len(ktab)))
    print("Filas auditadas: {}  (tipos {}, materiales {}, instancias {}, compound types {}, compound layers {})".format(
        len(rows_out),
        stats.get("kind_type", 0),
        stats.get("kind_material", 0),
        stats.get("kind_instance", 0),
        stats.get("kind_compound_type", 0),
        stats.get("kind_compound_layer", 0),
    ))
    print("  Compound types: {} | Compound layers: {}".format(
        stats.get("kind_compound_type", 0), stats.get("kind_compound_layer", 0)
    ))
    print("")
    print("GREEN (CSI + texto coincide):  {}".format(stats["GREEN"]))
    print("RED  (falta/mismatch):         {}".format(stats["RED"]))
    print("")
    print("Reporte: {}".format(OUT_CSV))


if __name__ == "__main__":
    audit()
