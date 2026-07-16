"""Suggest CSI keynotes for Revit objects that have none, by matching against
EstimaStruct V1.2 catalog on (a) unit compatibility and (b) text similarity of
family/type name vs ficha descripcion.

Does NOT write to Revit. Produces a CSV of suggestions per group
(category+family+type) for a human/Director to approve, before anything gets
written back to Revit's Keynote/Type Mark parameters.

Requires model_audit_raw.json to include "unit_kind"/"unit_qty" per instance
(see revit_dump_snippet.py — get_unit_hint: LocationCurve length > Area > Volume
> count, in that priority, converted to meters/m2/m3).

Output: suggest_keynotes_report.csv (one row per category+family+type group
missing a keynote), columns: category, family, type, unit_kind, instance_count,
element_ids, suggested_csi, suggested_codigo, suggested_descripcion,
suggested_unidad, confidence (0-1), match_reason.
"""
import json
import os
import re
import csv
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

MODEL_DUMP = r"D:\OneDrive\Bots\Estimbot\EXPORTS\model_audit_raw.json"
FICHAS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas"
OUT_CSV = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP\suggest_keynotes_report.csv"

# Same noise filter as audit_keynotes.py — non-physical/annotation categories.
NOISE_CATEGORY_SUBSTRINGS = [
    "etiqueta", "símbolo", "simbolo", "marca", "leyenda", "material",
    "eje", "boceto", "plano", "cámara", "camara", "anotaci", "circuito",
    "cad de", "curva de nivel", "punto ", "origen interno",
    "información de proyecto", "informacion de proyecto", "referencia a vista",
    "entorno", "emplazamiento", "vínculo", "vinculo", "camino de sol",
    "camino del recorrido", "base de camino",
]

# Below this score, the text match is noise (generic/English Revit sample family
# names vs Spanish catalog descriptions) — do NOT surface a suggested CSI, since a
# wrong code written back to Revit corrupts cost data silently. Calibrated empirically:
# real matches on this project scored >=0.5, everything below was garbage.
CONFIDENCE_THRESHOLD = 0.35

# Bucket ficha.unidad values into the same 4 buckets used for the Revit unit_kind hint.
# Manual judgment calls (2026-07-04) for categories where text-similarity matching
# is structurally useless — either the category is MEP/system metadata that isn't
# individually billable (the real pipes/conduits get billed at a different category
# level), a sub-element already billed via its parent assembly (balusters under a
# railing type), sample/placeholder furniture that isn't real scope, or a genuine
# catalog gap that needs a NEW partida (not a match to an existing one). Keyed by
# category name (case-sensitive, matches Revit's Spanish category name exactly).
CATEGORY_JUDGMENT = {
    "Tipo de carga analítica eléctrica": "METADATA — carga analítica, no facturable individualmente",
    "Sistema de interruptores": "METADATA — sistema de interruptores, no facturable individualmente",
    "Sistemas de tuberías": "METADATA — contenedor de sistema MEP; las tuberías reales ya se facturan en categoría Tuberías/Tubos",
    "Rejillas de muro cortina": "METADATA — sub-componente de panel de muro cortina, no facturable aparte",
    "Segmentos de tubería": "METADATA — sub-segmento de ruteo MEP; duplica lo ya facturado en Tuberías/Tubos",
    "Curvas de nivel principales": "METADATA — líneas de contorno topográfico, no facturable",
    "Balaustres": "SUB-ELEMENTO — parte de baranda ya facturada como assembly (RAI-01/RAI-02); asignar CSI individual sería doble conteo",
    "Líneas de extensión de camino de barandales de barandilla": "METADATA — trayectoria de baranda, no facturable aparte",
    "Habitaciones": "METADATA — Room de Revit (programa de áreas), no es partida de construcción",
    "Líneas": "METADATA — líneas de detalle 2D, no facturable",
    "Sólido topográfico": "AMBIGUO — requiere Director: ¿terreno base ya cubierto por movimiento de tierra, o superficie nueva a facturar?",
    "Escaleras": "GAP — escalera prefabricada sin partida equivalente en catálogo (GR-02 es metálica, no precast); requiere partida nueva",
    "Uniones de tubo": "GAP — fittings de conduit/tubo (junction box, elbow) sin código CSI; mismo gap ya escalado para fittings soldados",
    "Tramos de tubo": "AMBIGUO — puede ser el conduit real facturable (26 05 33 canalización) o metadata duplicada; requiere Director",
    "Tubos": "AMBIGUO — puede ser el conduit real facturable (26 05 33 canalización) o metadata duplicada; requiere Director",
    "Paneles de muro cortina": "GAP — panel de vidrio de muro cortina sin partida CW específica; requiere partida nueva o mapeo a vidrio existente",
    "Aparatos eléctricos": "GAP — caja de registro eléctrica sin código CSI equivalente; requiere partida nueva o mapeo manual",
    "Tramos": "AMBIGUO — 'Tramo monolítico', requiere Director (¿losa? ¿grada?)",
    "Uniones de tubería": "GAP — fittings soldados (welded elbow/transition), ningún CSI actual cubre acero soldado; ya escalado en auditoría original 2026-07-04",
    "Montantes de muro cortina": "GAP — montante (mullion) de muro cortina sin CSI; requiere partida nueva",
    "Mobiliario": "SOSPECHOSO — nombres de familia genéricos/placeholder (EN_Bed_..., Entertainment_Center_...) — probablemente contenido de muestra de Revit, no alcance real; confirmar con Director si se borra o se factura",
    "Muros": "GAP — variante de muro sin código catalogado y sin match específico conocido; revisar composición de capas/acabado y crear partida si corresponde",
    "Barandales superiores": "AMBIGUO — barandal superior (pasamanos) puede ser el elemento facturable de la baranda o un sub-componente ya cubierto por RAI-01/02; requiere Director",
    "Modelos genéricos": "GAP — 'Modelos genéricos' placeholder (Excavación, Estacionamiento, Calle, Exc2): objetos reales de obra sin familia propia asignada, requieren partida nueva por caso",
}


# Finer-grained override, checked BEFORE CATEGORY_JUDGMENT: (category, type substring,
# case-insensitive) -> reason. Needed because a single category (e.g. "Muros") can
# contain wall types with completely different judgment calls — a blanket
# category-level reason would misattribute one wall type's gap to another's.
CATEGORY_TYPE_JUDGMENT = [
    ("Muros", "wpcint", "GAP CONOCIDO — variante con acabado WPCINT sin partida en catálogo; requiere crear 06 86 13 (CC-WPCInt) — ya escalado"),
    ("Muros", "vynil", "GAP CONOCIDO — variante con acabado Vynil sin partida en catálogo; requiere crear 09 29 00.7 (CC-Vynil) — ya escalado"),
    ("Muros", 'bloque de 4"', "GAP — match manual disponible: catálogo tiene STR-05 (04 26 00.1, 'Pared de Bloque de Concreto de Partición de 4\"') — asignar en Revit"),
    ("Muros", 'bloque de 6"', "GAP — match manual disponible: catálogo tiene STR-06 (04 26 00.2, 'Pared bloque 6\"') — asignar en Revit"),
]


UNIDAD_BUCKETS = {
    "length": {"m", "ml", "m.l.", "ml."},
    "area": {"m2", "m²"},
    "volume": {"m3", "m³"},
    "count": {"pza", "und", "unidad", "glb", "global", "conexion", "lance", "mes", "nivel"},
}


def is_noise_category(category):
    if not category:
        return True
    low = category.lower()
    return any(sub in low for sub in NOISE_CATEGORY_SUBSTRINGS)


def unidad_bucket(unidad):
    if not unidad:
        return None
    low = unidad.strip().lower()
    for bucket, values in UNIDAD_BUCKETS.items():
        if low in values:
            return bucket
    return None


def load_catalog():
    live = os.path.join(FICHAS_DIR, "fichas_v1.2.live.json")
    canon = os.path.join(FICHAS_DIR, "fichas_v1.2.json")
    candidates = [p for p in (live, canon) if os.path.exists(p)]
    path = max(candidates, key=os.path.getmtime)
    with open(path, encoding="utf-8") as f:
        fichas = json.load(f)
    clean = []
    for f_ in fichas:
        if not isinstance(f_, dict):
            continue
        clean.append(f_)
    return clean, path, len(fichas)


def strip_accents(text):
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "y", "en", "por", "con",
    "para", "del", "a", "e", "instalacion", "suministro", "instalación",
}


def tokenize(text):
    text = strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(w for w in text.split() if w and w not in STOPWORDS and len(w) > 1)


def similarity(a_tokens, b_tokens, a_raw, b_raw):
    if not a_tokens or not b_tokens:
        return SequenceMatcher(None, a_raw.lower(), b_raw.lower()).ratio() * 0.5
    overlap = a_tokens & b_tokens
    jaccard = len(overlap) / len(a_tokens | b_tokens)
    seq_ratio = SequenceMatcher(None, a_raw.lower(), b_raw.lower()).ratio()
    return 0.7 * jaccard + 0.3 * seq_ratio


def suggest():
    with open(MODEL_DUMP, encoding="utf-8") as f:
        model = json.load(f)

    fichas, catalog_path, catalog_count = load_catalog()
    fichas_by_bucket = defaultdict(list)
    for f_ in fichas:
        bucket = unidad_bucket(f_.get("unidad"))
        if bucket:
            fichas_by_bucket[bucket].append(f_)

    # Group instances missing a keynote by (category, family, type)
    groups = defaultdict(lambda: {"ids": [], "unit_kinds": defaultdict(int)})
    for inst in model["instances"]:
        if inst.get("keynote"):
            continue
        if is_noise_category(inst.get("category")):
            continue
        key = (inst.get("category"), inst.get("family"), inst.get("type"))
        g = groups[key]
        g["ids"].append(inst.get("id"))
        g["unit_kinds"][inst.get("unit_kind") or "count"] += 1

    rows_out = []
    for (category, family, type_name), g in groups.items():
        # Dominant unit_kind for this group (most common among its instances)
        unit_kind = max(g["unit_kinds"].items(), key=lambda kv: kv[1])[0]

        judgment = None
        type_low = (type_name or "").lower()
        for cat_match, type_sub, reason in CATEGORY_TYPE_JUDGMENT:
            if category == cat_match and type_sub in type_low:
                judgment = reason
                break
        if judgment is None:
            judgment = CATEGORY_JUDGMENT.get(category)
        if judgment:
            rows_out.append({
                "category": category,
                "family": family,
                "type": type_name,
                "unit_kind": unit_kind,
                "instance_count": len(g["ids"]),
                "element_ids": ";".join(str(i) for i in g["ids"][:20]),
                "suggested_csi": "",
                "suggested_codigo": "",
                "suggested_descripcion": "",
                "suggested_unidad": "",
                "confidence": 0,
                "match_reason": judgment,
            })
            continue

        query_raw = " ".join(filter(None, [family, type_name, category]))
        query_tokens = tokenize(query_raw)

        candidates = fichas_by_bucket.get(unit_kind, [])
        best = None
        best_score = -1.0
        for f_ in candidates:
            desc = f_.get("descripcion", "")
            score = similarity(query_tokens, tokenize(desc), query_raw, desc)
            if score > best_score:
                best_score = score
                best = f_

        if best is None:
            rows_out.append({
                "category": category,
                "family": family,
                "type": type_name,
                "unit_kind": unit_kind,
                "instance_count": len(g["ids"]),
                "element_ids": ";".join(str(i) for i in g["ids"][:20]),
                "suggested_csi": "",
                "suggested_codigo": "",
                "suggested_descripcion": "",
                "suggested_unidad": "",
                "confidence": 0,
                "match_reason": "sin fichas de unidad compatible ({}) en catálogo".format(unit_kind),
            })
            continue

        if best_score < CONFIDENCE_THRESHOLD:
            rows_out.append({
                "category": category,
                "family": family,
                "type": type_name,
                "unit_kind": unit_kind,
                "instance_count": len(g["ids"]),
                "element_ids": ";".join(str(i) for i in g["ids"][:20]),
                "suggested_csi": "",
                "suggested_codigo": "",
                "suggested_descripcion": "",
                "suggested_unidad": "",
                "confidence": round(best_score, 3),
                "match_reason": "SIN MATCH CONFIABLE (mejor candidato {} score {:.3f} < umbral {}) — requiere catalogar manualmente o es metadata/no-facturable".format(
                    best.get("codigo", "?"), best_score, CONFIDENCE_THRESHOLD
                ),
            })
            continue

        rows_out.append({
            "category": category,
            "family": family,
            "type": type_name,
            "unit_kind": unit_kind,
            "instance_count": len(g["ids"]),
            "element_ids": ";".join(str(i) for i in g["ids"][:20]),
            "suggested_csi": best.get("csi", ""),
            "suggested_codigo": best.get("codigo", ""),
            "suggested_descripcion": best.get("descripcion", ""),
            "suggested_unidad": best.get("unidad", ""),
            "confidence": round(best_score, 3),
            "match_reason": "match texto+unidad ({})".format(unit_kind),
        })

    rows_out.sort(key=lambda r: (-r["confidence"], -r["instance_count"]))

    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "category", "family", "type", "unit_kind", "instance_count",
            "element_ids", "suggested_csi", "suggested_codigo",
            "suggested_descripcion", "suggested_unidad", "confidence",
            "match_reason",
        ])
        writer.writeheader()
        writer.writerows(rows_out)

    confiable = sum(1 for r in rows_out if r["suggested_csi"])
    metadata_ct = sum(1 for r in rows_out if r["match_reason"].startswith("METADATA"))
    subelemento_ct = sum(1 for r in rows_out if r["match_reason"].startswith("SUB-ELEMENTO"))
    gap_ct = sum(1 for r in rows_out if "GAP" in r["match_reason"])
    ambiguo_ct = sum(1 for r in rows_out if r["match_reason"].startswith("AMBIGUO") or r["match_reason"].startswith("SOSPECHOSO"))
    sin_match_ct = sum(1 for r in rows_out if r["match_reason"].startswith("SIN MATCH"))

    print("Catálogo: {} ({} fichas)".format(catalog_path, catalog_count))
    print("Grupos sin keynote (categoria+familia+tipo): {}".format(len(rows_out)))
    print("Instancias afectadas: {}".format(sum(r["instance_count"] for r in rows_out)))
    print("")
    print("Sugerencias CONFIABLES (score >= {}):     {}".format(CONFIDENCE_THRESHOLD, confiable))
    print("METADATA (no facturable):              {}".format(metadata_ct))
    print("SUB-ELEMENTO (ya facturado en assembly): {}".format(subelemento_ct))
    print("GAP (requiere partida nueva en catálogo): {}".format(gap_ct))
    print("AMBIGUO/SOSPECHOSO (requiere Director):  {}".format(ambiguo_ct))
    print("SIN match confiable, sin judgment call:  {}".format(sin_match_ct))
    print("")
    print("Reporte: {}".format(OUT_CSV))


if __name__ == "__main__":
    suggest()
