"""Create Revit instances from CSI/metadata payloads using existing families.

This file follows the same pattern as the other Revit snippets in this repo:

- the outer file is a normal Python helper
- the IronPython / pyRevit code lives in the CODE raw string
- paste CODE into execute_revit_code on the Revit MCP bridge

Purpose:
  - Read a viewer/snapshot JSON payload that contains placed metadata
  - Match each record to an already loaded FamilySymbol
  - Create instances in the active Revit document
  - Skip records that cannot be matched safely

Assumptions:
  - The target project already has the needed families loaded
  - The source metadata carries category/family/type plus a point or curve
  - System-family creation (walls/floors/roofs/ceilings) is not automated here
    unless the source record already provides enough geometry and a compatible
    family-symbol style match

The snippet is intentionally conservative:
  - DRY_RUN defaults to True
  - existing signatures are skipped so re-running does not duplicate obvious
    placements
  - only point/curve placements are attempted
"""

CODE = r'''
import json
import os
import re
from collections import defaultdict

from pyrevit import revit, DB

doc = revit.doc
FT_TO_M = 0.3048
DRY_RUN = True

CSI_MAP_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\csi_to_codigo.json"
SOURCE_CANDIDATES = [
    r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\revit-mcp-audit\output\template_canon_snapshot_20260717.json",
    r"D:\OneDrive\Bots\Viewer\projects\ValleDeAngeles\template_canon_snapshot.json",
    r"D:\OneDrive\Bots\Viewer\projects\ValleDeAngeles\viewer_snapshot.json",
    r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas\fichas_v1.2.live.json",
]
MAX_SKIP_LOGS = 40


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def norm(text):
    if text is None:
        return ""
    try:
        if not isinstance(text, unicode):
            text = unicode(text)
    except Exception:
        try:
            text = str(text)
        except Exception:
            return ""
    try:
        import unicodedata
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
    except Exception:
        pass
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def safe_text(value):
    if value is None:
        return ""
    try:
        return str(value).strip()
    except Exception:
        try:
            return unicode(value).strip()
        except Exception:
            return ""


def get_record_text(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return safe_text(value)
    return ""


def eid(element_id):
    if element_id is None:
        return -1
    try:
        value = getattr(element_id, "Value", None)
        if value is not None:
            return int(value)
    except Exception:
        pass
    try:
        return int(getattr(element_id, "IntegerValue", -1))
    except Exception:
        return -1


def ft(v):
    try:
        return float(v)
    except Exception:
        return None


def m_to_ft(v):
    try:
        return float(v) / FT_TO_M
    except Exception:
        return None


def xyz_from_payload(node):
    if node is None:
        return None
    if isinstance(node, (list, tuple)) and len(node) >= 3:
        return DB.XYZ(float(node[0]), float(node[1]), float(node[2]))
    if not isinstance(node, dict):
        return None

    if "x_ft" in node and "y_ft" in node and "z_ft" in node:
        return DB.XYZ(float(node["x_ft"]), float(node["y_ft"]), float(node["z_ft"]))
    if "x_m" in node and "y_m" in node and "z_m" in node:
        return DB.XYZ(m_to_ft(node["x_m"]), m_to_ft(node["y_m"]), m_to_ft(node["z_m"]))

    if "x" in node and "y" in node and "z" in node:
        if node.get("units") == "m":
            return DB.XYZ(m_to_ft(node["x"]), m_to_ft(node["y"]), m_to_ft(node["z"]))
        return DB.XYZ(float(node["x"]), float(node["y"]), float(node["z"]))

    return None


def curve_from_payload(loc):
    if not isinstance(loc, dict):
        return None
    kind = safe_text(loc.get("kind")).lower()
    if kind != "curve":
        return None

    start = xyz_from_payload(loc.get("start"))
    end = xyz_from_payload(loc.get("end"))
    if start is None or end is None:
        return None
    try:
        return DB.Line.CreateBound(start, end)
    except Exception:
        return None


def point_from_payload(loc):
    if loc is None:
        return None
    if isinstance(loc, dict):
        kind = safe_text(loc.get("kind")).lower()
        if kind == "curve":
            return None
        if "point" in loc:
            return xyz_from_payload(loc.get("point"))
        if "xyz" in loc:
            return xyz_from_payload(loc.get("xyz"))
        return xyz_from_payload(loc)
    return xyz_from_payload(loc)


def load_source_payload():
    for path in SOURCE_CANDIDATES:
        if os.path.isfile(path):
            return path, load_json(path)
    return None, None


def extract_records(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("all_instances", "objects", "elements", "records", "items"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return value

    snap = payload.get("template_snapshot")
    if isinstance(snap, dict):
        for key in ("all_instances", "objects"):
            value = snap.get(key)
            if isinstance(value, list) and value:
                return value

    return []


def get_doc_level_index():
    by_name = {}
    levels = []
    for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements():
        try:
            name = safe_text(lv.Name)
        except Exception:
            name = ""
        if not name:
            continue
        by_name[norm(name)] = lv
        try:
            levels.append((float(lv.Elevation), lv))
        except Exception:
            continue
    levels.sort(key=lambda item: item[0])
    return by_name, levels


def resolve_level(record, level_by_name, levels):
    level_name = safe_text(record.get("level") or record.get("level_name") or record.get("level_id"))
    if level_name:
        hit = level_by_name.get(norm(level_name))
        if hit is not None:
            return hit

    loc = record.get("location") or record.get("location_xyz") or record.get("position")
    pt = point_from_payload(loc)
    if pt is not None and levels:
        z = float(pt.Z)
        best = None
        best_dist = None
        for elev, lv in levels:
            dist = abs(elev - z)
            if best is None or dist < best_dist:
                best = lv
                best_dist = dist
        return best

    if levels:
        return levels[0][1]
    return None


def get_param_string(elem, bip):
    try:
        p = elem.get_Parameter(bip)
        if p:
            return safe_text(p.AsString())
    except Exception:
        pass
    return ""


def set_param_string(elem, bip, value):
    if not value:
        return False
    try:
        p = elem.get_Parameter(bip)
        if p and not p.IsReadOnly and p.StorageType == DB.StorageType.String:
            current = safe_text(p.AsString())
            value = safe_text(value)
            if current != value:
                p.Set(value)
                return True
    except Exception:
        pass
    return False


def type_label(symbol):
    try:
        return safe_text(symbol.Name)
    except Exception:
        try:
            p = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            return safe_text(p.AsString()) if p else ""
        except Exception:
            return ""


def family_label(symbol):
    try:
        return safe_text(getattr(symbol, "FamilyName", "") or "")
    except Exception:
        return ""


def category_label(elem):
    try:
        cat = elem.Category
        return safe_text(cat.Name) if cat else ""
    except Exception:
        return ""


def symbol_signature(symbol):
    return "|".join([
        norm(category_label(symbol)),
        norm(family_label(symbol)),
        norm(type_label(symbol)),
        norm(get_param_string(symbol, DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)),
        norm(get_param_string(symbol, DB.BuiltInParameter.KEYNOTE_PARAM)),
    ])


def record_signature(record):
    category = get_record_text(record, "category", "category_name", "category_label")
    family = get_record_text(record, "family", "family_name")
    type_name = get_record_text(record, "type", "type_name", "symbol", "name")
    level = get_record_text(record, "level", "level_name", "level_id")

    loc = record.get("location") or record.get("location_xyz") or record.get("position")
    pt = point_from_payload(loc)
    if pt is not None:
        loc_sig = "P:{0:.3f}:{1:.3f}:{2:.3f}".format(pt.X, pt.Y, pt.Z)
    else:
        curve = curve_from_payload(loc)
        if curve is not None:
            s = curve.GetEndPoint(0)
            e = curve.GetEndPoint(1)
            loc_sig = "C:{0:.3f}:{1:.3f}:{2:.3f}:{3:.3f}:{4:.3f}:{5:.3f}".format(
                s.X, s.Y, s.Z, e.X, e.Y, e.Z
            )
        else:
            loc_sig = ""

    return "|".join([
        norm(category),
        norm(family),
        norm(type_name),
        norm(level),
        loc_sig,
    ])


def find_symbol(record, symbol_index):
    category = get_record_text(record, "category", "category_name", "category_label")
    family = get_record_text(record, "family", "family_name")
    type_name = get_record_text(record, "type", "type_name", "symbol", "name")
    type_mark = get_record_text(record, "type_mark", "marca", "codigo")
    keynote = get_record_text(record, "keynote", "csi", "clave_csi")
    codigo = get_record_text(record, "codigo", "type_mark", "marca")

    keys = [
        norm(category) + "|" + norm(family) + "|" + norm(type_name),
        norm(family) + "|" + norm(type_name),
        norm(type_name),
        norm(type_mark),
        norm(codigo),
        norm(keynote),
    ]
    for key in keys:
        if key and key in symbol_index:
            return symbol_index[key]

    return None


def build_symbol_index():
    index = {}
    collisions = 0
    symbols = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).ToElements()
    for sym in symbols:
        try:
            cat = category_label(sym)
            fam = family_label(sym)
            typ = type_label(sym)
            tm = get_param_string(sym, DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
            kn = get_param_string(sym, DB.BuiltInParameter.KEYNOTE_PARAM)
            candidates = [
                norm(cat) + "|" + norm(fam) + "|" + norm(typ),
                norm(fam) + "|" + norm(typ),
                norm(typ),
                norm(tm),
                norm(kn),
            ]
            for key in candidates:
                if not key:
                    continue
                if key in index:
                    collisions += 1
                else:
                    index[key] = sym
        except Exception:
            continue
    return index, collisions


def build_existing_signatures():
    sigs = set()
    instances = DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance).WhereElementIsNotElementType().ToElements()
    for e in instances:
        try:
            cat = category_label(e)
            fam = safe_text(getattr(e, "FamilyName", "") or "")
            typ = ""
            try:
                t = doc.GetElement(e.GetTypeId())
                if t is not None:
                    typ = type_label(t)
            except Exception:
                pass
            level = safe_text(get_param_string(e, DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM))
            loc = None
            try:
                loc_obj = e.Location
                if isinstance(loc_obj, DB.LocationPoint):
                    loc = loc_obj.Point
                elif isinstance(loc_obj, DB.LocationCurve):
                    loc = loc_obj.Curve
            except Exception:
                pass

            if isinstance(loc, DB.XYZ):
                loc_sig = "P:{0:.3f}:{1:.3f}:{2:.3f}".format(loc.X, loc.Y, loc.Z)
            elif loc is not None:
                try:
                    s = loc.GetEndPoint(0)
                    ept = loc.GetEndPoint(1)
                    loc_sig = "C:{0:.3f}:{1:.3f}:{2:.3f}:{3:.3f}:{4:.3f}:{5:.3f}".format(
                        s.X, s.Y, s.Z, ept.X, ept.Y, ept.Z
                    )
                except Exception:
                    loc_sig = ""
            else:
                loc_sig = ""

            sigs.add("|".join([norm(cat), norm(fam), norm(typ), norm(level), loc_sig]))
        except Exception:
            continue
    return sigs


def structural_type_for_category(name):
    n = norm(name)
    try:
        st = DB.Structure.StructuralType
    except Exception:
        return None

    if "column" in n or "columna" in n or "pillar" in n:
        return getattr(st, "Column", None)
    if "beam" in n or "viga" in n or "framing" in n or "armazon" in n:
        return getattr(st, "Beam", None)
    if "brace" in n or "arriost" in n:
        return getattr(st, "Brace", None)
    return getattr(st, "NonStructural", None)


def load_csi_map():
    if not os.path.isfile(CSI_MAP_PATH):
        return {}, {}
    try:
        forward = load_json(CSI_MAP_PATH)
        inverse = {}
        for csi, codigo in forward.items():
            if codigo and codigo not in inverse:
                inverse[codigo] = csi
        return forward, inverse
    except Exception:
        return {}, {}


def activate_symbol(symbol):
    try:
        if not symbol.IsActive:
            symbol.Activate()
            try:
                doc.Regenerate()
            except Exception:
                pass
    except Exception:
        pass


def place_point_instance(record, symbol, level):
    pt = point_from_payload(record.get("location") or record.get("location_xyz") or record.get("position"))
    if pt is None:
        return None, "no_point"

    st = structural_type_for_category(record.get("category") or record.get("category_name") or record.get("category_label"))
    if st is None:
        st = getattr(DB.Structure.StructuralType, "NonStructural", None)

    activate_symbol(symbol)

    try:
        return doc.Create.NewFamilyInstance(pt, symbol, level, st), "point"
    except Exception as ex1:
        try:
            return doc.Create.NewFamilyInstance(pt, symbol, level), "point"
        except Exception as ex2:
            return None, "point_fail:{}|{}".format(str(ex1)[:80], str(ex2)[:80])


def place_curve_instance(record, symbol, level):
    curve = curve_from_payload(record.get("location") or record.get("location_xyz") or record.get("position"))
    if curve is None:
        return None, "no_curve"

    st = structural_type_for_category(record.get("category") or record.get("category_name") or record.get("category_label"))
    if st is None:
        st = getattr(DB.Structure.StructuralType, "NonStructural", None)

    activate_symbol(symbol)

    try:
        return doc.Create.NewFamilyInstance(curve, symbol, level, st), "curve"
    except Exception as ex1:
        try:
            return doc.Create.NewFamilyInstance(curve, symbol, level), "curve"
        except Exception as ex2:
            return None, "curve_fail:{}|{}".format(str(ex1)[:80], str(ex2)[:80])


def maybe_copy_metadata_to_symbol(record, symbol, codigo_to_csi):
    csi = get_record_text(record, "csi", "clave_csi", "keynote")
    codigo = get_record_text(record, "codigo", "type_mark", "marca")

    changed = []
    if not csi and codigo:
        csi = codigo_to_csi.get(codigo, "")
    if csi:
        if set_param_string(symbol, DB.BuiltInParameter.KEYNOTE_PARAM, csi):
            changed.append("keynote")
    if codigo:
        if set_param_string(symbol, DB.BuiltInParameter.ALL_MODEL_TYPE_MARK, codigo):
            changed.append("type_mark")
    return changed


source_path, payload = load_source_payload()
if not source_path:
    print("ERROR: no JSON source found for metadata.")
    raise Exception("No source metadata JSON found.")

records = extract_records(payload)
if not records:
    print("ERROR: JSON found but no usable record list was detected.")
    print("Source:", source_path)
    raise Exception("No usable records in source JSON.")

codigo_map, codigo_to_csi = load_csi_map()
symbol_index, duplicate_hits = build_symbol_index()
level_by_name, levels = get_doc_level_index()
existing = build_existing_signatures()

summary = {
    "source": source_path,
    "records": len(records),
    "candidate_records": 0,
    "created": 0,
    "dry_run": DRY_RUN,
    "skipped_existing": 0,
    "skipped_no_symbol": 0,
    "skipped_no_location": 0,
    "skipped_no_level": 0,
    "skipped_create_failed": 0,
    "metadata_applied": 0,
    "symbol_duplicates": duplicate_hits,
    "codigo_map_size": len(codigo_map),
}

print("Source:", source_path)
print("Records:", len(records))
print("Dry run:", DRY_RUN)

for record in records:
    try:
        category = get_record_text(record, "category", "category_name", "category_label")
        family = get_record_text(record, "family", "family_name")
        type_name = get_record_text(record, "type", "type_name", "symbol", "name")
        if not (category or family or type_name):
            continue

        summary["candidate_records"] += 1

        sig = record_signature(record)
        if sig in existing:
            summary["skipped_existing"] += 1
            continue

        symbol = find_symbol(record, symbol_index)
        if symbol is None:
            summary["skipped_no_symbol"] += 1
            if summary["skipped_no_symbol"] <= MAX_SKIP_LOGS:
                print("SKIP no symbol -> {} / {} / {}".format(category, family, type_name))
            continue

        level = resolve_level(record, level_by_name, levels)
        if level is None:
            summary["skipped_no_level"] += 1
            if summary["skipped_no_level"] <= MAX_SKIP_LOGS:
                print("SKIP no level -> {} / {} / {}".format(category, family, type_name))
            continue

        loc = record.get("location") or record.get("location_xyz") or record.get("position")
        pt = point_from_payload(loc)
        curve = curve_from_payload(loc)
        if pt is None and curve is None:
            summary["skipped_no_location"] += 1
            if summary["skipped_no_location"] <= MAX_SKIP_LOGS:
                print("SKIP no location -> {} / {} / {}".format(category, family, type_name))
            continue

        if DRY_RUN:
            print("DRY RUN create -> {} / {} / {} / level {}".format(category, family, type_name, safe_text(level.Name)))
            continue

        changed = maybe_copy_metadata_to_symbol(record, symbol, codigo_to_csi)
        summary["metadata_applied"] += len(changed)

        if curve is not None:
            created, mode = place_curve_instance(record, symbol, level)
        else:
            created, mode = place_point_instance(record, symbol, level)

        if created is None:
            summary["skipped_create_failed"] += 1
            print("FAIL create -> {} / {} / {} ({})".format(category, family, type_name, mode))
            continue

        existing.add(sig)
        summary["created"] += 1
        print("CREATED -> {} / {} / {} / mode {}".format(category, family, type_name, mode))

    except Exception as ex:
        summary["skipped_create_failed"] += 1
        if summary["skipped_create_failed"] <= MAX_SKIP_LOGS:
            print("ERROR record -> {}".format(str(ex)[:200]))

print("=== SUMMARY ===")
for key in sorted(summary.keys()):
    print("{}: {}".format(key, summary[key]))
'''


if __name__ == "__main__":
    print("Paste CODE into execute_revit_code on the Revit MCP bridge.")
    print("Default mode inside the snippet is DRY_RUN = True.")
    print("Change DRY_RUN to False only after you verify the source JSON and the target template.")
