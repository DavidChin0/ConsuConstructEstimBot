"""Construye un snapshot canónico del template Revit abierto vía bridge MCP.

Salidas:
- JSON técnico con coordenadas, scope boxes, niveles y buckets canónicos
- MD resumen legible para referencia futura
"""
from __future__ import annotations

import json
import urllib.request


STATUS_URL = "http://localhost:48884/revit_mcp/status/"
EXEC_URL = "http://localhost:48884/revit_mcp/execute_code/"

OUTPUT_DIR = (
    r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\revit-mcp-audit\output"
)
JSON_OUT = OUTPUT_DIR + r"\template_canon_snapshot_20260717.json"
MD_OUT = OUTPUT_DIR + r"\template_canon_snapshot_20260717.md"


SNAPSHOT_CODE = r"""# coding: utf-8
import json

def ft_to_m(v):
    try:
        return round(float(v) * 0.3048, 6)
    except:
        return None

def xyz_dict(pt):
    if pt is None:
        return None
    return {
        'x_ft': float(pt.X), 'y_ft': float(pt.Y), 'z_ft': float(pt.Z),
        'x_m': ft_to_m(pt.X), 'y_m': ft_to_m(pt.Y), 'z_m': ft_to_m(pt.Z)
    }

def safe_name(e):
    try:
        return e.Name
    except:
        try:
            p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
            return p.AsString() if p else None
        except:
            return None

def eid(e):
    try:
        return int(e.Id.Value)
    except:
        try:
            return int(e.Id.IntegerValue)
        except:
            return None

out = {}
out['document_title'] = doc.Title
try:
    out['document_path'] = doc.PathName
except:
    out['document_path'] = ''

levels = []
for lv in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Levels).WhereElementIsNotElementType().ToElements():
    try:
        levels.append({'id': eid(lv), 'name': safe_name(lv), 'elevation_ft': float(lv.Elevation), 'elevation_m': ft_to_m(lv.Elevation)})
    except:
        pass
out['levels'] = sorted(levels, key=lambda x: x.get('elevation_ft', 0))

scope_boxes = []
for sb in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_VolumeOfInterest).WhereElementIsNotElementType().ToElements():
    info = {'id': eid(sb), 'name': safe_name(sb)}
    try:
        bb = sb.get_BoundingBox(None)
        info['bbox_min'] = xyz_dict(bb.Min) if bb else None
        info['bbox_max'] = xyz_dict(bb.Max) if bb else None
    except Exception as ex:
        info['bbox_error'] = str(ex)
    scope_boxes.append(info)
out['scope_boxes'] = scope_boxes

views_by_scope = {}
all_views = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
for sb in scope_boxes:
    views_by_scope[str(sb['id'])] = []
for v in all_views:
    try:
        if v.IsTemplate:
            continue
    except:
        pass
    try:
        p = v.get_Parameter(DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
        if p:
            sid = p.AsElementId()
            sidv = int(sid.Value) if sid and sid != DB.ElementId.InvalidElementId else None
            if sidv is not None and str(sidv) in views_by_scope:
                views_by_scope[str(sidv)].append({'id': eid(v), 'name': safe_name(v), 'view_type': str(v.ViewType)})
    except:
        pass
out['views_by_scope_box'] = views_by_scope

base_points = []
for cat_name, bic in [('ProjectBasePoint', DB.BuiltInCategory.OST_ProjectBasePoint), ('SurveyPoint', DB.BuiltInCategory.OST_SharedBasePoint)]:
    elems = DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
    for bp in elems:
        item = {'kind': cat_name, 'id': eid(bp), 'name': safe_name(bp)}
        try:
            item['position'] = xyz_dict(bp.Position)
        except Exception as ex:
            item['position_error'] = str(ex)
        vals = {}
        for bip, label in [
            (DB.BuiltInParameter.BASEPOINT_EASTWEST_PARAM, 'east_west'),
            (DB.BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM, 'north_south'),
            (DB.BuiltInParameter.BASEPOINT_ELEVATION_PARAM, 'elevation'),
            (DB.BuiltInParameter.BASEPOINT_ANGLETON_PARAM, 'angle_to_true_north'),
        ]:
            try:
                p = bp.get_Parameter(bip)
                if p:
                    vals[label] = p.AsDouble()
            except:
                pass
        item['parameters_raw'] = vals
        base_points.append(item)
out['base_points'] = base_points

cats = [
    (DB.BuiltInCategory.OST_Walls, 'Muros'),
    (DB.BuiltInCategory.OST_Floors, 'Suelos'),
    (DB.BuiltInCategory.OST_Roofs, 'Cubiertas'),
    (DB.BuiltInCategory.OST_Ceilings, 'Techos'),
    (DB.BuiltInCategory.OST_StructuralColumns, 'Pilares estructurales'),
    (DB.BuiltInCategory.OST_StructuralFraming, 'Armazon estructural'),
    (DB.BuiltInCategory.OST_StructuralFoundation, 'Cimentacion estructural'),
    (DB.BuiltInCategory.OST_StructuralFramingSystem, 'Sistemas de vigas estructurales'),
]
buckets = []
for bic, label in cats:
    try:
        inst = list(DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements())
        typ = list(DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType().ToElements())
        buckets.append({'category': label, 'instance_count': len(inst), 'type_count': len(typ)})
    except Exception as ex:
        buckets.append({'category': label, 'error': str(ex)})
out['canonical_buckets'] = buckets

print(json.dumps(out))
"""


def http_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build():
    status = http_json(STATUS_URL)
    result = post_json(
        EXEC_URL,
        {
            "code": SNAPSHOT_CODE,
            "description": "Build template canon snapshot",
        },
    )
    output = json.loads(result["output"])
    payload = {
        "snapshot_date": "2026-07-17",
        "skill_reference": ["inventario-audit-tipos-revit-mcp", "revit-dual-mcp"],
        "bridge_status": status,
        "template_snapshot": output,
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    snap = payload["template_snapshot"]
    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write("# Template Canon Snapshot — 2026-07-17\n\n")
        f.write(f"- Documento activo: `{snap['document_title']}`\n")
        f.write(f"- Ruta: `{snap['document_path']}`\n")
        f.write(f"- Bridge health: `{status.get('health')}`\n")
        f.write(f"- Skill base: `inventario-audit-tipos-revit-mcp` + `revit-dual-mcp`\n\n")

        f.write("## Scope Boxes\n\n")
        for sb in snap.get("scope_boxes", []):
            f.write(f"- `{sb.get('name')}` (`{sb.get('id')}`)\n")
            f.write(f"  min: `{sb.get('bbox_min')}`\n")
            f.write(f"  max: `{sb.get('bbox_max')}`\n")
            linked = snap.get("views_by_scope_box", {}).get(str(sb.get("id")), [])
            f.write(f"  views: `{len(linked)}`\n")

        f.write("\n## Levels\n\n")
        for lv in snap.get("levels", []):
            f.write(f"- `{lv['name']}` | `{lv['elevation_m']} m` | `{lv['elevation_ft']} ft`\n")

        f.write("\n## Base / Survey\n\n")
        for bp in snap.get("base_points", []):
            f.write(f"- `{bp['kind']}` | pos `{bp.get('position')}` | raw `{bp.get('parameters_raw')}`\n")

        f.write("\n## Canonical Buckets\n\n")
        for bucket in snap.get("canonical_buckets", []):
            f.write(
                f"- `{bucket['category']}` | types `{bucket.get('type_count', 0)}` | "
                f"instances `{bucket.get('instance_count', 0)}`\n"
            )

        f.write("\n## Decision\n\n")
        f.write(
            "- Template canon snapshot guardado para futuras referencias de scope y baseline de contenido.\n"
        )
        f.write("- El template sigue vacío de instancias físicas en buckets canónicos complejos.\n")

    print(JSON_OUT)
    print(MD_OUT)
    return JSON_OUT, MD_OUT


if __name__ == "__main__":
    build()
