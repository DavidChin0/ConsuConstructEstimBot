"""revit_full_dump_snippet.py — COMPREHENSIVE Revit model dump for EstimaStruct.

Run via MCP execute_revit_code (IronPython 2.7, inside Revit/pyRevit).
NOT run standalone with regular Python.

Supersedes revit_dump_snippet.py (which stays for the fast audit-only path).
This dump is the source of truth for:
  - Viewer construction (levels, views, geometry, materials)
  - EstimaStruct sync (keynotes, compound layers, schedule quantities)
  - Project metadata (project_info, sheets, grids, rooms)

Output: D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\project_full_dump.json

Sections (non-redundant with XLSX audit):
  project_info        — ProjectInformation fields + doc path + filename
  levels              — all levels: name, elevation_m, is_structural
  grids               — all grid lines: name, start/end XY in meters
  views               — all views grouped by type (plans, sections, 3D, sheets)
  sheets              — sheet list: number, name, view_ids on sheet
  rooms               — all rooms: name, number, level, area_m2, perimeter_m, location
  all_instances       — ALL placed instances: id, category, family, type, level,
                        keynote, type_mark, marca, location_xyz, bb_min/max
  materials_full      — all materials: id, name, keynote, color_rgb, category
  objects             — (reused) element types + materials + instances WITH keynote
  keynote_table       — (reused) project keynote .txt table
  compound_elements   — (reused) Wall/Floor/Roof/Ceiling compound layer stacks
  unplaced_types      — (reused) loaded-but-unplaced types
  schedule_quantities — (reused) material takeoff schedules m² per CSI

GOTCHAS (inherited from revit_dump_snippet.py + new ones):
- ElementId.Value vs .IntegerValue: use eid() helper for compat across Revit versions.
- KEYNOTE_PARAM BuiltInParameter is language-independent; LookupParameter("Keynote") is not.
- XYZ.X/Y/Z are in internal Revit units (decimal feet). Multiply by 0.3048 to get meters.
- BoundingBox may be None for non-geometric elements — guard with try/except.
- doc.ProjectInformation may throw for corrupt files — guard each field individually.
- Rooms: use SpatialElement filter; unplaced rooms have Location == None.
- GetCellText can be slow on large schedules — cap at MAX_SCHED_ROWS per schedule.
- All floats rounded to 4 decimals to keep JSON size manageable.
- Output path is fixed to EXPORTS/project_full_dump.json — do NOT print the full JSON back.

Paste this into execute_revit_code as-is.
"""

CODE = r'''
from pyrevit import revit, DB
import json, io, math

doc = revit.doc

OUT_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\project_full_dump.json"
MAX_SCHED_ROWS = 2000   # cap per schedule to avoid token blowout

FT_TO_M = 0.3048        # internal Revit units (feet) -> meters

# ────────────────────────────────────────────────────────────────────────────
# HELPERS  (reused from revit_dump_snippet.py)
# ────────────────────────────────────────────────────────────────────────────

def eid(element_id):
    if element_id is None:
        return -1
    v = getattr(element_id, "Value", None)
    if v is not None:
        return int(v)
    return int(getattr(element_id, "IntegerValue", -1))

def get_keynote(elem):
    p = elem.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
    if p:
        v = p.AsString()
        if v:
            return v
    return None

def get_type_mark(elem):
    p = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
    if p:
        v = p.AsString()
        if v:
            return v
    return None

def get_marca(elem):
    for bip in (DB.BuiltInParameter.ALL_MODEL_MARK, DB.BuiltInParameter.ALL_MODEL_TYPE_MARK):
        p = elem.get_Parameter(bip)
        if p:
            v = p.AsString()
            if v:
                return v
    return None

def elem_name(e):
    try:
        return DB.Element.Name.__get__(e)
    except Exception:
        try:
            return e.Name
        except Exception:
            return None

def xyz_to_m(xyz):
    if xyz is None:
        return None
    try:
        return [round(xyz.X * FT_TO_M, 4),
                round(xyz.Y * FT_TO_M, 4),
                round(xyz.Z * FT_TO_M, 4)]
    except Exception:
        return None

def bb_to_dict(bb):
    if bb is None:
        return None
    try:
        return {
            "min": xyz_to_m(bb.Min),
            "max": xyz_to_m(bb.Max),
        }
    except Exception:
        return None

def get_level_of(elem):
    for bip in (DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM):
        try:
            p = elem.get_Parameter(bip)
            if p and p.StorageType == DB.StorageType.ElementId:
                lid = p.AsElementId()
                if lid and lid != DB.ElementId.InvalidElementId:
                    lvl = doc.GetElement(lid)
                    if lvl:
                        return elem_name(lvl)
        except Exception:
            pass
    try:
        lvl = doc.GetElement(elem.LevelId)
        if lvl:
            return elem_name(lvl)
    except Exception:
        pass
    return None

def get_location(elem):
    try:
        loc = elem.Location
        if loc is None:
            return None
        if isinstance(loc, DB.LocationPoint):
            return {"kind": "point", "xyz": xyz_to_m(loc.Point)}
        if isinstance(loc, DB.LocationCurve):
            c = loc.Curve
            return {
                "kind": "curve",
                "start": xyz_to_m(c.GetEndPoint(0)),
                "end":   xyz_to_m(c.GetEndPoint(1)),
                "length_m": round(c.Length * FT_TO_M, 4),
            }
    except Exception:
        pass
    return None

# ────────────────────────────────────────────────────────────────────────────
# PLACED TYPE IDS  (needed for "placed" flag, reused in compound_elements)
# ────────────────────────────────────────────────────────────────────────────

all_instances_raw = DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
placed_type_ids = set()
for _e in all_instances_raw:
    try:
        tid = _e.GetTypeId()
        if tid != DB.ElementId.InvalidElementId:
            placed_type_ids.add(eid(tid))
    except Exception:
        continue

# ────────────────────────────────────────────────────────────────────────────
# 1. PROJECT INFO
# ────────────────────────────────────────────────────────────────────────────

def dump_project_info():
    pi = {}
    try:
        info = doc.ProjectInformation
        for field in ("Name", "Number", "Status", "ClientName", "Address",
                      "Author", "BuildingName", "IssueDate", "OrganizationName"):
            try:
                pi[field.lower()] = getattr(info, field, None)
            except Exception:
                pi[field.lower()] = None
    except Exception:
        pass
    try:
        pi["file_path"] = doc.PathName or None
    except Exception:
        pi["file_path"] = None
    try:
        pi["file_name"] = doc.Title or None
    except Exception:
        pi["file_name"] = None
    return pi

# ────────────────────────────────────────────────────────────────────────────
# 2. LEVELS
# ────────────────────────────────────────────────────────────────────────────

def dump_levels():
    levels_out = []
    try:
        lvl_elems = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
        for lv in sorted(lvl_elems, key=lambda x: x.Elevation):
            try:
                is_struct = False
                try:
                    p = lv.get_Parameter(DB.BuiltInParameter.LEVEL_IS_STRUCTURAL)
                    if p:
                        is_struct = bool(p.AsInteger())
                except Exception:
                    pass
                levels_out.append({
                    "id":           eid(lv.Id),
                    "name":         elem_name(lv),
                    "elevation_m":  round(lv.Elevation * FT_TO_M, 4),
                    "is_structural": is_struct,
                })
            except Exception:
                continue
    except Exception:
        pass
    return levels_out

# ────────────────────────────────────────────────────────────────────────────
# 3. GRIDS
# ────────────────────────────────────────────────────────────────────────────

def dump_grids():
    grids_out = []
    try:
        grid_elems = DB.FilteredElementCollector(doc).OfClass(DB.Grid).ToElements()
        for g in grid_elems:
            try:
                curve = g.Curve
                grids_out.append({
                    "id":    eid(g.Id),
                    "name":  elem_name(g),
                    "start": xyz_to_m(curve.GetEndPoint(0)),
                    "end":   xyz_to_m(curve.GetEndPoint(1)),
                })
            except Exception:
                continue
    except Exception:
        pass
    return grids_out

# ────────────────────────────────────────────────────────────────────────────
# 4. VIEWS
# ────────────────────────────────────────────────────────────────────────────

VIEW_TYPE_NAMES = {
    DB.ViewType.FloorPlan:       "FloorPlan",
    DB.ViewType.CeilingPlan:     "CeilingPlan",
    DB.ViewType.Elevation:       "Elevation",
    DB.ViewType.Section:         "Section",
    DB.ViewType.ThreeD:          "3D",
    DB.ViewType.Schedule:        "Schedule",
    DB.ViewType.DrawingSheet:    "Sheet",
    DB.ViewType.Legend:          "Legend",
    DB.ViewType.Detail:          "Detail",
    DB.ViewType.DraftingView:    "Drafting",
    DB.ViewType.AreaPlan:        "AreaPlan",
    DB.ViewType.EngineeringPlan: "EngineeringPlan",
}

def dump_views():
    views_out = []
    try:
        view_elems = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
        for v in view_elems:
            try:
                if v.IsTemplate:
                    continue
                vtype = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
                level_name = None
                try:
                    lvl = doc.GetElement(v.GenLevel.Id) if v.GenLevel else None
                    if lvl:
                        level_name = elem_name(lvl)
                except Exception:
                    pass
                scale = None
                try:
                    scale = v.Scale
                except Exception:
                    pass
                views_out.append({
                    "id":         eid(v.Id),
                    "name":       elem_name(v),
                    "view_type":  vtype,
                    "level":      level_name,
                    "scale":      scale,
                    "is_sheet":   isinstance(v, DB.ViewSheet),
                })
            except Exception:
                continue
    except Exception:
        pass
    return views_out

# ────────────────────────────────────────────────────────────────────────────
# 5. SHEETS
# ────────────────────────────────────────────────────────────────────────────

def dump_sheets():
    sheets_out = []
    try:
        sheet_elems = DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements()
        for s in sheet_elems:
            try:
                view_ids = [eid(vid) for vid in s.GetAllPlacedViews()]
                sheets_out.append({
                    "id":           eid(s.Id),
                    "sheet_number": s.SheetNumber,
                    "name":         elem_name(s),
                    "view_ids":     view_ids,
                })
            except Exception:
                continue
    except Exception:
        pass
    return sheets_out

# ────────────────────────────────────────────────────────────────────────────
# 6. ROOMS
# ────────────────────────────────────────────────────────────────────────────

def dump_rooms():
    rooms_out = []
    try:
        room_elems = (
            DB.FilteredElementCollector(doc)
            .OfClass(DB.Architecture.Room)
            .ToElements()
        )
        for r in room_elems:
            try:
                loc = r.Location
                if loc is None:
                    continue  # unplaced room
                loc_pt = xyz_to_m(loc.Point) if isinstance(loc, DB.LocationPoint) else None
                area_m2 = None
                try:
                    p = r.get_Parameter(DB.BuiltInParameter.ROOM_AREA)
                    if p:
                        area_m2 = round(p.AsDouble() * (FT_TO_M ** 2), 4)
                except Exception:
                    pass
                perim_m = None
                try:
                    p = r.get_Parameter(DB.BuiltInParameter.ROOM_PERIMETER)
                    if p:
                        perim_m = round(p.AsDouble() * FT_TO_M, 4)
                except Exception:
                    pass
                rooms_out.append({
                    "id":          eid(r.Id),
                    "name":        r.Name,
                    "number":      r.Number,
                    "level":       get_level_of(r),
                    "area_m2":     area_m2,
                    "perimeter_m": perim_m,
                    "location":    loc_pt,
                })
            except Exception:
                continue
    except Exception:
        pass
    return rooms_out

# ────────────────────────────────────────────────────────────────────────────
# 7. ALL PLACED INSTANCES  (geometry + identification — every model element)
# ────────────────────────────────────────────────────────────────────────────

def _dump_element_params(e):
    """Collect ALL readable parameters from element as {name: value} dict.
    Skips internal/empty values; coerces to JSON-safe types."""
    params = {}
    try:
        for p in e.Parameters:
            try:
                pname = p.Definition.Name
                if not pname:
                    continue
                st = str(p.StorageType)
                if st == "String":
                    val = p.AsString()
                    if val:
                        params[pname] = val
                elif st == "Integer":
                    params[pname] = p.AsInteger()
                elif st == "Double":
                    params[pname] = round(p.AsDouble(), 6)
                elif st == "ElementId":
                    eid_val = p.AsElementId()
                    if eid_val and eid_val != DB.ElementId.InvalidElementId:
                        params[pname] = eid_val.IntegerValue
                # ElementId.InvalidElementId and None → skip
            except Exception:
                continue
    except Exception:
        pass
    return params

def dump_all_instances():
    instances_out = []
    for e in all_instances_raw:
        try:
            cat = e.Category
            if cat is None or cat.CategoryType != DB.CategoryType.Model:
                continue
            bb = None
            try:
                bb = bb_to_dict(e.get_BoundingBox(None))
            except Exception:
                pass
            instances_out.append({
                "id":       eid(e.Id),
                "category": cat.Name,
                "family":   getattr(e, "FamilyName", None) or None,
                "type":     elem_name(doc.GetElement(e.GetTypeId())) if e.GetTypeId() != DB.ElementId.InvalidElementId else None,
                "type_id":  eid(e.GetTypeId()),
                "level":    get_level_of(e),
                "keynote":  get_keynote(e),
                "type_mark": get_type_mark(e),
                "marca":    get_marca(e),
                "location": get_location(e),
                "bb":       bb,
                "params":   _dump_element_params(e),
            })
        except Exception:
            continue
    return instances_out

# ────────────────────────────────────────────────────────────────────────────
# 8. MATERIALS FULL  (all materials: name + color + keynote + class + textures)
# ────────────────────────────────────────────────────────────────────────────

def _get_appearance_asset(m):
    """Extract AppearanceAssetElement from material (Revit 2019+)."""
    try:
        asset_id = m.AppearanceAssetId
        if asset_id and asset_id != DB.ElementId.InvalidElementId:
            return doc.GetElement(asset_id)
    except Exception:
        pass
    return None

def _extract_textures(asset_elem):
    """Walk AppearanceAsset (Visual.Asset) properties, collect texture file paths.
    IronPython 2.7 safe: no f-strings, no Visual namespace import, no GetConnectedProperties(0)."""
    textures = {}
    if asset_elem is None:
        return textures
    try:
        ra = asset_elem.GetRenderingAsset()
        if ra is None:
            return textures
        for i in range(ra.Size):
            try:
                prop = ra[i]
                name = getattr(prop, "Name", "") or ""
                # ── connected properties (nested texture assets e.g. UnifiedBitmap) ──
                # GetConnectedProperties() takes NO argument — returns IList<AssetProperty>
                get_connected = getattr(prop, "GetConnectedProperties", None)
                if get_connected is not None:
                    try:
                        connected_list = get_connected()
                    except Exception:
                        connected_list = None
                    if connected_list:
                        for cp in connected_list:
                            try:
                                cp_name = getattr(cp, "Name", "") or ""
                                # nested asset also supports Size/index (e.g. UnifiedBitmap sub-props)
                                cp_size = getattr(cp, "Size", None)
                                if cp_size is not None:
                                    for j in range(cp_size):
                                        try:
                                            sub = cp[j]
                                            sub_name = getattr(sub, "Name", "") or ""
                                            sub_val = getattr(sub, "Value", None)
                                            if sub_val is None:
                                                continue
                                            sval = str(sub_val)
                                            low = sval.lower()
                                            if sval and (low.endswith(".png") or low.endswith(".jpg")
                                                    or low.endswith(".jpeg") or low.endswith(".bmp")
                                                    or low.endswith(".tif") or low.endswith(".tiff")
                                                    or "\\" in sval or "/" in sval):
                                                slot = "{0}.{1}".format(name or cp_name, sub_name) if sub_name else (name or cp_name)
                                                textures[slot] = sval
                                        except Exception:
                                            continue
                                else:
                                    cp_val = getattr(cp, "Value", None)
                                    if cp_val is not None:
                                        sval = str(cp_val)
                                        low = sval.lower()
                                        if sval and (low.endswith(".png") or low.endswith(".jpg")
                                                or low.endswith(".jpeg") or low.endswith(".bmp")
                                                or low.endswith(".tif") or low.endswith(".tiff")
                                                or "\\" in sval or "/" in sval):
                                            textures[name if name else cp_name] = sval
                            except Exception:
                                continue
                # ── direct string value on prop itself ──
                direct_val = getattr(prop, "Value", None)
                if direct_val is not None:
                    sval = str(direct_val)
                    low = sval.lower()
                    if sval and (low.endswith(".png") or low.endswith(".jpg")
                            or low.endswith(".jpeg") or low.endswith(".bmp")
                            or low.endswith(".tif") or low.endswith(".tiff")):
                        textures[name] = sval
            except Exception:
                continue
    except Exception:
        # fallback: scan Parameters on AppearanceAssetElement directly
        try:
            for p in asset_elem.Parameters:
                try:
                    if str(p.StorageType) == "String":
                        val = p.AsString() or ""
                        low = val.lower()
                        if val and (low.endswith(".png") or low.endswith(".jpg")
                                or low.endswith(".jpeg") or low.endswith(".bmp")
                                or low.endswith(".tif") or low.endswith(".tiff")
                                or (":\\" in val and "." in val)):
                            textures[p.Definition.Name] = val
                except Exception:
                    continue
        except Exception:
            pass
    return textures

def _get_pattern_name(pattern_id):
    try:
        if pattern_id and pattern_id != DB.ElementId.InvalidElementId:
            pe = doc.GetElement(pattern_id)
            if pe:
                return pe.Name
    except Exception:
        pass
    return None

def _rgb(color_obj):
    try:
        c = color_obj
        if c is None:
            return None
        is_valid = getattr(c, "IsValid", True)
        if not is_valid:
            return None
        return [int(c.Red), int(c.Green), int(c.Blue)]
    except Exception:
        pass
    return None

def _bip_int(m, bip):
    try:
        if bip is None:
            return None
        p = m.get_Parameter(bip)
        if p:
            return p.AsInteger()
    except Exception:
        pass
    return None

def _safe_bip(name):
    """Resolve DB.BuiltInParameter.<name> safely — returns None if missing in this Revit build."""
    try:
        return getattr(DB.BuiltInParameter, name, None)
    except Exception:
        return None

def dump_materials_full():
    mats_out = []
    try:
        mat_elems = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
        for m in mat_elems:
            try:
                # ── identity ──────────────────────────────────────
                mat_class = None
                try:
                    p = m.get_Parameter(DB.BuiltInParameter.MATERIAL_PARAM_CLASS)
                    if p:
                        mat_class = p.AsValueString()
                except Exception:
                    pass

                # ── shading color (viewport) ──────────────────────
                color_rgb = None
                try:
                    color_rgb = _rgb(m.Color)
                except Exception:
                    pass

                # ── render/appearance color ───────────────────────
                render_color = None
                try:
                    rp = m.get_Parameter(DB.BuiltInParameter.MATERIAL_PARAM_COLOR)
                    if rp:
                        render_color = _rgb(rp.AsColor())
                except Exception:
                    pass

                # ── optical properties ────────────────────────────
                transparency = _bip_int(m, DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY)
                shininess    = _bip_int(m, DB.BuiltInParameter.MATERIAL_PARAM_SHININESS)
                smoothness   = _bip_int(m, _safe_bip("MATERIAL_PARAM_SMOOTHNESS"))

                reflectivity = None
                try:
                    p = m.get_Parameter(DB.BuiltInParameter.MATERIAL_PARAM_REFRACTION)
                    if p:
                        reflectivity = p.AsInteger()
                except Exception:
                    pass

                # ── surface pattern ───────────────────────────────
                surf_pat_name = None
                surf_color    = None
                try:
                    surf_pat_name = _get_pattern_name(getattr(m, "SurfaceForegroundPatternId", None))
                except Exception:
                    pass
                try:
                    surf_color = _rgb(getattr(m, "SurfaceForegroundPatternColor", None))
                except Exception:
                    pass

                # ── cut pattern ───────────────────────────────────
                cut_pat_name = None
                cut_color    = None
                try:
                    cut_pat_name = _get_pattern_name(getattr(m, "CutForegroundPatternId", None))
                except Exception:
                    pass
                try:
                    cut_color = _rgb(getattr(m, "CutForegroundPatternColor", None))
                except Exception:
                    pass

                # ── appearance asset / textures ───────────────────
                asset_elem    = _get_appearance_asset(m)
                texture_paths = _extract_textures(asset_elem)
                asset_name    = None
                try:
                    if asset_elem:
                        asset_name = asset_elem.Name
                except Exception:
                    pass

                # ── appearance asset parameters (all) ────────────
                appearance_params = {}
                try:
                    if asset_elem:
                        for p in asset_elem.Parameters:
                            try:
                                pname = p.Definition.Name
                                st = str(p.StorageType)  # str() safer than .ToString() in IPy2.7
                                if st == "String":
                                    appearance_params[pname] = p.AsString()
                                elif st == "Integer":
                                    appearance_params[pname] = p.AsInteger()
                                elif st == "Double":
                                    appearance_params[pname] = round(p.AsDouble(), 6)
                            except Exception:
                                continue
                except Exception:
                    pass

                mats_out.append({
                    "id":                eid(m.Id),
                    "name":              elem_name(m),
                    "keynote":           get_keynote(m),
                    "type_mark":         get_type_mark(m),
                    "marca":             get_marca(m),
                    "material_class":    mat_class,
                    "color_rgb":         color_rgb,
                    "render_color_rgb":  render_color,
                    "transparency":      transparency,
                    "shininess":         shininess,
                    "smoothness":        smoothness,
                    "reflectivity":      reflectivity,
                    "surface_pattern":   surf_pat_name,
                    "surface_color_rgb": surf_color,
                    "cut_pattern":       cut_pat_name,
                    "cut_color_rgb":     cut_color,
                    "appearance_asset":  asset_name,
                    "texture_paths":     texture_paths,
                    "appearance_params": appearance_params,
                })
            except Exception:
                continue
    except Exception:
        pass
    return mats_out

# ────────────────────────────────────────────────────────────────────────────
# 9-12. REUSED FROM revit_dump_snippet.py
#       objects / keynote_table / compound_elements / unplaced_types
# ────────────────────────────────────────────────────────────────────────────

# --- objects (types+materials+instances WITH keynote) ---
objects = []
all_types = DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements()
for t in all_types:
    try:
        kn = get_keynote(t)
        if not kn:
            continue
        cat = t.Category
        objects.append({
            "kind":      "type",
            "id":        eid(t.Id),
            "category":  cat.Name if cat else None,
            "family":    getattr(t, "FamilyName", None),
            "type":      elem_name(t),
            "keynote":   kn,
            "type_mark": get_type_mark(t),
            "marca":     get_marca(t),
            "placed":    eid(t.Id) in placed_type_ids,
        })
    except Exception:
        continue

mat_elems_kn = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
for m in mat_elems_kn:
    try:
        kn = get_keynote(m)
        if not kn:
            continue
        objects.append({
            "kind":      "material",
            "id":        eid(m.Id),
            "category":  "Materiales",
            "family":    None,
            "type":      elem_name(m),
            "keynote":   kn,
            "type_mark": get_type_mark(m),
            "marca":     get_marca(m),
            "placed":    True,
        })
    except Exception:
        continue

for e in all_instances_raw:
    try:
        cat = e.Category
        if not cat or cat.CategoryType != DB.CategoryType.Model:
            continue
        p = e.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
        kn = p.AsString() if p else None
        if not kn:
            continue
        objects.append({
            "kind":      "instance",
            "id":        eid(e.Id),
            "category":  cat.Name,
            "family":    None,
            "type":      elem_name(e),
            "keynote":   kn,
            "type_mark": get_type_mark(e),
            "marca":     get_marca(e),
            "placed":    True,
        })
    except Exception:
        continue

# --- keynote_table ---
keynote_table = {}
try:
    kt = DB.KeynoteTable.GetKeynoteTable(doc)
    for entry in kt.GetKeyBasedTreeEntries():
        try:
            key = entry.Key
            txt = entry.KeynoteText
            if key:
                keynote_table[str(key)] = txt or ""
        except Exception:
            continue
except Exception as ex:
    keynote_table["__error__"] = str(ex)

# --- compound_elements ---
COMPOUND_CATEGORIES = [
    (DB.WallType,    "Muros"),
    (DB.FloorType,   "Suelos"),
    (DB.RoofType,    "Cubiertas"),
    (DB.CeilingType, "Techos"),
]
compound_elements = []
for cls, label in COMPOUND_CATEGORIES:
    try:
        types_of_class = DB.FilteredElementCollector(doc).OfClass(cls).ToElements()
    except Exception:
        continue
    for t in types_of_class:
        try:
            cs = t.GetCompoundStructure()
            if cs is None:
                continue
            layers_out = []
            for layer in cs.GetLayers():
                mat_id = layer.MaterialId
                mat = doc.GetElement(mat_id) if mat_id and mat_id != DB.ElementId.InvalidElementId else None
                mat_kn = get_keynote(mat) if mat else None
                mat_color = None
                try:
                    if mat:
                        c = mat.Color
                        if c and c.IsValid:
                            mat_color = [int(c.Red), int(c.Green), int(c.Blue)]
                except Exception:
                    pass
                mat_transp = None
                try:
                    if mat:
                        p2 = mat.get_Parameter(DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY)
                        if p2:
                            mat_transp = p2.AsInteger()
                except Exception:
                    pass
                layers_out.append({
                    "function":         str(layer.Function),
                    "material_id":      eid(mat_id) if mat_id else -1,
                    "material_name":    elem_name(mat) if mat else None,
                    "material_keynote": mat_kn,
                    "material_color_rgb": mat_color,
                    "material_transparency": mat_transp,
                    "width_mm":         round(layer.Width * 304.8, 2),
                })
            compound_elements.append({
                "type_id":        eid(t.Id),
                "category_label": label,
                "type_name":      elem_name(t),
                "type_keynote":   get_keynote(t),
                "type_type_mark": get_type_mark(t),
                "type_marca":     get_marca(t),
                "placed":         eid(t.Id) in placed_type_ids,
                "layers":         layers_out,
            })
        except Exception:
            continue

try:
    sfs_types = DB.FilteredElementCollector(doc).OfClass(DB.Structure.StructuralFramingSystemType).ToElements()
except Exception:
    sfs_types = []
for t in sfs_types:
    try:
        compound_elements.append({
            "type_id":        eid(t.Id),
            "category_label": "Sistemas de vigas estructurales",
            "type_name":      elem_name(t),
            "type_keynote":   get_keynote(t),
            "type_type_mark": get_type_mark(t),
            "type_marca":     get_marca(t),
            "placed":         eid(t.Id) in placed_type_ids,
            "layers":         [],
        })
    except Exception:
        continue

# --- unplaced_types ---
unplaced_types = []
for t in all_types:
    try:
        if eid(t.Id) in placed_type_ids:
            continue
        cat = t.Category
        unplaced_types.append({
            "type_id":  eid(t.Id),
            "category": cat.Name if cat else None,
            "family":   getattr(t, "FamilyName", None),
            "type":     elem_name(t),
            "keynote":  get_keynote(t),
            "type_mark": get_type_mark(t),
        })
    except Exception:
        continue

# --- schedule_quantities ---
QUANTITY_SCHEDULES = [
    "T04Wall Material Takeoff",
    "T02Pisos",
    "T01Material Cielo Falso",
]
schedule_quantities = []
try:
    all_schedules = DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).ToElements()
    sched_map = {}
    for vs in all_schedules:
        try:
            sched_map[DB.Element.Name.__get__(vs)] = vs
        except Exception:
            pass
    for sname in QUANTITY_SCHEDULES:
        vs = sched_map.get(sname)
        if not vs:
            continue
        try:
            td  = vs.GetTableData()
            ssd = td.GetSectionData(DB.SectionType.Body)
            n_rows = min(ssd.NumberOfRows, MAX_SCHED_ROWS)
            n_cols = ssd.NumberOfColumns
            for r in range(n_rows):
                try:
                    csi_raw  = vs.GetCellText(DB.SectionType.Body, r, 0).strip()
                    if not csi_raw:
                        continue
                    area_str = vs.GetCellText(DB.SectionType.Body, r, 2).strip() if n_cols > 2 else ""
                    mat_name = vs.GetCellText(DB.SectionType.Body, r, 1).strip() if n_cols > 1 else ""
                    type_mark = vs.GetCellText(DB.SectionType.Body, r, n_cols - 1).strip() if n_cols > 0 else ""
                    clean_area = area_str.replace("m\xb2", "").replace("m2", "").strip()
                    area_m2 = 0.0
                    try:
                        area_m2 = float(clean_area.replace(",", ".")) if clean_area else 0.0
                    except ValueError:
                        area_m2 = 0.0
                    schedule_quantities.append({
                        "schedule":  sname,
                        "csi":       csi_raw,
                        "mat_name":  mat_name,
                        "area_m2":   area_m2,
                        "type_mark": type_mark,
                    })
                except Exception:
                    continue
        except Exception:
            continue
except Exception:
    pass

# ────────────────────────────────────────────────────────────────────────────
# ASSEMBLE + WRITE
# ────────────────────────────────────────────────────────────────────────────

project_info      = dump_project_info()
levels            = dump_levels()
grids             = dump_grids()
views             = dump_views()
sheets            = dump_sheets()
rooms             = dump_rooms()
all_instances_out = dump_all_instances()
materials_full    = dump_materials_full()

result = {
    "_meta": {
        "dump_version": "full_v2",
        "sections": [
            "project_info", "levels", "grids", "views", "sheets", "rooms",
            "all_instances", "materials_full",
            "objects", "keynote_table", "compound_elements",
            "unplaced_types", "schedule_quantities",
        ],
    },
    "project_info":       project_info,
    "levels":             levels,
    "grids":              grids,
    "views":              views,
    "sheets":             sheets,
    "rooms":              rooms,
    "all_instances":      all_instances_out,
    "materials_full":     materials_full,
    "objects":            objects,
    "keynote_table":      keynote_table,
    "compound_elements":  compound_elements,
    "unplaced_types":     unplaced_types,
    "schedule_quantities": schedule_quantities,
}

with io.open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(json.dumps(result, ensure_ascii=False))

print("WRITTEN: project_full_dump.json")
print("  project_info fields: {}".format(len(project_info)))
print("  levels: {}".format(len(levels)))
print("  grids: {}".format(len(grids)))
print("  views: {}".format(len(views)))
print("  sheets: {}".format(len(sheets)))
print("  rooms: {}".format(len(rooms)))
print("  all_instances: {}".format(len(all_instances_out)))
print("  materials_full: {}".format(len(materials_full)))
print("  objects (keynoted): {}".format(len(objects)))
print("  keynote_table entries: {}".format(len(keynote_table)))
print("  compound_elements: {}".format(len(compound_elements)))
print("  unplaced_types: {}".format(len(unplaced_types)))
print("  schedule_qty rows: {}".format(len(schedule_quantities)))
'''
