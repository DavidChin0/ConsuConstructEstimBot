# -*- coding: utf-8 -*-
"""
EstimBot - Generate HVAC Layout

Places duct main-trunk + branches for a selected set of duct terminals /
mechanical equipment sharing one system (SupplyAir/ReturnAir/ExhaustAir),
routed at the REAL ceiling height for the room/level the elements sit in
(read from the project's own Ceiling elements, not a hardcoded fallback).

Mirrors the architecture of Plumbing.panel/Generate Layout.pushbutton and
Electrical.panel/Conduit by Circuit -- see generate_hvac_layout_core.py
for the pure sizing/geometry logic and its design-decision docstring.
"""

import os
import sys
import json
from pyrevit import DB, forms, revit, script
from System import Int64

SCRIPT_ROOT = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\pyrevit"
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

DATA_ROOT = r"D:\OneDrive\Bots\Estimbot"
LOG_DIR = os.path.join(DATA_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "generate_hvac_layout.log")

from scripts.generate_hvac_layout_core import (  # noqa: E402
    DuctConnectorSnapshot,
    RoomHeightContext,
    build_duct_layout_plan,
    build_hvac_preview_report,
    select_duct_type_name,
    ft_to_mm,
    mm_to_ft,
    infer_duct_system_labels,
    normalize_duct_system_label,
    DUCT_SYSTEM_LABELS,
)

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
output.set_title("EstimBot - Generate HVAC Layout")

AUTOMATION_FLAG = "ESTIMBOT_HVAC_AUTOMATION"
AUTOMATION_PICK = "ESTIMBOT_HVAC_AUTOPICK"
AUTOMATION_SYSTEM = "ESTIMBOT_HVAC_SYSTEM"
AUTOMATION_CONFIRM = "ESTIMBOT_HVAC_CONFIRM"


def clean(value):
    if value is None:
        return ""
    try:
        return str(value).replace("_x000D_", "").strip()
    except Exception:
        return ""


def write_log(message):
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        with open(LOG_FILE, "a") as f:
            f.write(message)
    except Exception:
        pass


def automation_enabled():
    return clean(os.environ.get(AUTOMATION_FLAG)).lower() in ("1", "true", "yes", "on")


def automation_value(name, default=""):
    return clean(os.environ.get(name) or default)


def alert(message, title="Generate HVAC Layout", **kwargs):
    if automation_enabled():
        write_log("AUTOMATION ALERT | title={0} | message={1}\n".format(title, clean(message)))
        return True
    return forms.alert(message, title=title, **kwargs)


def element_id_value(elem_id):
    if elem_id is None:
        return None
    for attr in ("IntegerValue", "Value"):
        try:
            value = getattr(elem_id, attr)
            if value is not None:
                return int(value)
        except Exception:
            pass
    return None


def safe_name(elem):
    if elem is None:
        return ""
    try:
        value = DB.Element.Name.__get__(elem)
        if value:
            return clean(value)
    except Exception:
        pass
    try:
        value = elem.Name
        if value:
            return clean(value)
    except Exception:
        pass
    return ""


HVAC_CATEGORIES = [
    DB.BuiltInCategory.OST_DuctTerminal,
    DB.BuiltInCategory.OST_MechanicalEquipment,
    DB.BuiltInCategory.OST_DuctAccessory,
]


def is_hvac_connection_candidate(elem):
    if elem is None or elem.Category is None:
        return False
    try:
        cat_id_int = element_id_value(elem.Category.Id)
        for cat in HVAC_CATEGORIES:
            if cat_id_int == int(cat):
                return True
    except Exception:
        pass
    return False


def get_connectors(elem):
    connectors = []
    try:
        mep_model = elem.MEPModel
        if mep_model and mep_model.ConnectorManager:
            for connector in mep_model.ConnectorManager.Connectors:
                connectors.append(connector)
    except Exception:
        pass
    return connectors


def is_physical_hvac_connector(connector):
    if connector is None:
        return False
    try:
        if connector.Domain.ToString() != "DomainHvac":
            return False
    except Exception:
        return False
    try:
        if connector.ConnectorType.ToString() in ("Logical", "NonEnd"):
            return False
    except Exception:
        pass
    return True


def connector_is_available(connector):
    if not is_physical_hvac_connector(connector):
        return False
    try:
        if connector.IsConnected:
            return False
    except Exception:
        pass
    try:
        _ = connector.Origin
    except Exception:
        return False
    return True


def get_connector_origin(connector):
    try:
        origin = connector.Origin
        if origin is not None:
            return origin
    except Exception:
        pass
    try:
        return connector.CoordinateSystem.Origin
    except Exception:
        pass
    raise ValueError("No se pudo leer el origen del conector HVAC.")


def get_duct_system_type_string(connector):
    try:
        return str(connector.DuctSystemType)
    except Exception:
        return ""


def get_connector_shape(connector):
    try:
        return str(connector.Shape)
    except Exception:
        return "Round"


def snapshot_connector(elem, connector):
    origin = get_connector_origin(connector)
    return DuctConnectorSnapshot(
        element_id=element_id_value(elem.Id),
        family_name=safe_name(elem),
        category_name=elem.Category.Name if elem.Category else "",
        system_kind=get_duct_system_type_string(connector),
        is_connected=bool(connector.IsConnected),
        x=ft_to_mm(origin.X),
        y=ft_to_mm(origin.Y),
        z=ft_to_mm(origin.Z),
        flow_cfm=float(getattr(connector, "Flow", 0.0) or 0.0),
        shape=get_connector_shape(connector),
    )


def get_level_id(elem):
    for bip_name in [
        "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM",
        "FAMILY_LEVEL_PARAM",
        "INSTANCE_REFERENCE_LEVEL_PARAM",
        "SCHEDULE_LEVEL_PARAM",
        "LEVEL_PARAM",
    ]:
        try:
            bip = getattr(DB.BuiltInParameter, bip_name)
            param = elem.get_Parameter(bip)
            if param and param.StorageType == DB.StorageType.ElementId:
                level_id = param.AsElementId()
                if level_id and level_id != DB.ElementId.InvalidElementId:
                    if isinstance(doc.GetElement(level_id), DB.Level):
                        return level_id
        except Exception:
            pass
    try:
        if elem.LevelId and elem.LevelId != DB.ElementId.InvalidElementId:
            return elem.LevelId
    except Exception:
        pass
    return DB.ElementId.InvalidElementId


def find_real_ceiling_height_context(point_xyz):
    """Find the REAL ceiling height above the level containing point_xyz,
    by looking at actual Ceiling elements whose bounding box covers this
    XY location (matches the CEILING_HEIGHTABOVELEVEL_PARAM read by
    dump_architecture.py). Falls back to a project-wide median ceiling
    height if no ceiling covers this exact point (e.g. open corridor).
    """
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
    levels.sort(key=lambda lvl: lvl.Elevation)

    assigned_level = None
    for level in levels:
        if level.Elevation <= point_xyz.Z + 0.01:
            assigned_level = level
        else:
            break
    if assigned_level is None and levels:
        assigned_level = levels[0]

    ceilings = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType()
    best_offset_ft = None
    all_offsets_ft = []
    for ceiling in ceilings:
        try:
            offset_param = ceiling.get_Parameter(DB.BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
            offset_ft = offset_param.AsDouble() if offset_param else None
        except Exception:
            offset_ft = None
        if offset_ft is None:
            continue
        all_offsets_ft.append(offset_ft)
        bb = ceiling.get_BoundingBox(None)
        if not bb:
            continue
        inside_xy = bb.Min.X <= point_xyz.X <= bb.Max.X and bb.Min.Y <= point_xyz.Y <= bb.Max.Y
        if inside_xy:
            best_offset_ft = offset_ft
            break

    if best_offset_ft is None and all_offsets_ft:
        all_offsets_ft.sort()
        mid = len(all_offsets_ft) // 2
        best_offset_ft = all_offsets_ft[mid]
    if best_offset_ft is None:
        best_offset_ft = 9.0  # 2.74m hospital-standard fallback (matches real project median)

    level_name = safe_name(assigned_level) if assigned_level else "Unknown"
    level_elevation_mm = ft_to_mm(assigned_level.Elevation) if assigned_level else 0.0
    ceiling_offset_mm = ft_to_mm(best_offset_ft)
    return RoomHeightContext(level_name, level_elevation_mm, ceiling_offset_mm)


def collect_selection_or_view():
    selected_ids = list(uidoc.Selection.GetElementIds())
    if selected_ids:
        elems = [doc.GetElement(eid) for eid in selected_ids]
        return [e for e in elems if is_hvac_connection_candidate(e)]

    answer = forms.alert(
        "No hay seleccion activa.\n\nSi = usar elementos HVAC visibles en la vista activa.\nNo = cancelar.",
        yes=True,
        no=True,
    )
    if not answer:
        return []
    collector = DB.FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType()
    return [e for e in collector if is_hvac_connection_candidate(e)]


def collect_duct_type_families():
    """(family_name, type_name) pairs for every loaded DuctType."""
    pairs = []
    for dt in DB.FilteredElementCollector(doc).OfClass(DB.Mechanical.DuctType):
        try:
            fam_name = safe_name(dt) if False else None
        except Exception:
            fam_name = None
        try:
            fam_name = clean(dt.FamilyName)
        except Exception:
            fam_name = None
        type_name = safe_name(dt)
        pairs.append((fam_name or "", type_name or ""))
    return pairs


def choose_duct_type_element(shape, duct_type_families):
    """Resolve the actual DuctType Element matching a select_duct_type_name()
    result, by re-querying with the picked (family, type) pair."""
    picked = select_duct_type_name(shape, duct_type_families)
    if picked is None:
        return None
    fam_name, type_name = picked
    for dt in DB.FilteredElementCollector(doc).OfClass(DB.Mechanical.DuctType):
        try:
            this_fam = clean(dt.FamilyName)
        except Exception:
            this_fam = None
        this_type = safe_name(dt)
        if this_fam == fam_name and this_type == type_name:
            return dt
    return None


def choose_system_label(elems):
    if automation_enabled():
        wanted = automation_value(AUTOMATION_SYSTEM)
        for label in DUCT_SYSTEM_LABELS:
            if clean(label).lower() == wanted.lower():
                return label
        return None
    labels = list(DUCT_SYSTEM_LABELS)
    selected = forms.SelectFromList.show(
        labels,
        multiselect=False,
        title="Seleccionar sistema HVAC",
        button_name="Continuar",
    )
    if not selected:
        return None
    return clean(selected)


DUCT_SYSTEM_TYPE_ENUM = {
    "SupplyAir": "SupplyAir",
    "ReturnAir": "ReturnAir",
    "ExhaustAir": "ExhaustAir",
}


def find_mechanical_system_type_id(system_label):
    """Resolve the MechanicalSystemType ElementId matching SupplyAir/
    ReturnAir/ExhaustAir. Duct.Create requires this as its systemTypeId
    argument (6-arg overload: Document, systemTypeId, ductTypeId,
    levelId, startPoint, endPoint)."""
    target = DUCT_SYSTEM_TYPE_ENUM.get(system_label)
    if target is None:
        return None
    for mst in DB.FilteredElementCollector(doc).OfClass(DB.Mechanical.MechanicalSystemType):
        try:
            if str(mst.SystemClassification) == target:
                return mst.Id
        except Exception:
            continue
    # Fallback: first available MechanicalSystemType if exact classification
    # match fails (some templates name classifications slightly differently).
    all_types = list(DB.FilteredElementCollector(doc).OfClass(DB.Mechanical.MechanicalSystemType))
    return all_types[0].Id if all_types else None


def xyz_from_mm(x_mm, y_mm, z_mm):
    return DB.XYZ(mm_to_ft(x_mm), mm_to_ft(y_mm), mm_to_ft(z_mm))


def main():
    elems = collect_selection_or_view()
    if not elems:
        alert("No se encontraron elementos HVAC validos.")
        return

    system_label = choose_system_label(elems)
    if not system_label:
        alert("No se selecciono sistema HVAC.")
        return

    valid_snapshots = []
    for elem in elems:
        for connector in get_connectors(elem):
            if not connector_is_available(connector):
                continue
            normalized = normalize_duct_system_label(get_duct_system_type_string(connector))
            if normalized != system_label:
                continue
            try:
                valid_snapshots.append(snapshot_connector(elem, connector))
            except Exception as ex:
                write_log("SNAPSHOT FAIL | element={0} | error={1}\n".format(element_id_value(elem.Id), ex))

    if not valid_snapshots:
        alert("No hay conectores HVAC disponibles para el sistema '{0}'.".format(system_label))
        return

    sample_point = xyz_from_mm(valid_snapshots[0].x, valid_snapshots[0].y, valid_snapshots[0].z)
    height_ctx = find_real_ceiling_height_context(sample_point)

    duct_type_families = collect_duct_type_families()
    try:
        plan = build_duct_layout_plan(valid_snapshots, system_label, height_ctx.duct_centerline_z_mm)
    except ValueError as ex:
        alert(str(ex))
        return

    duct_type_elem = choose_duct_type_element(plan.shape, duct_type_families)
    if duct_type_elem is None:
        alert("No se encontro un DuctType cargado para la forma '{0}'.".format(plan.shape))
        return

    system_type_id = find_mechanical_system_type_id(system_label)
    if system_type_id is None:
        alert("No se encontro un MechanicalSystemType cargado para '{0}'.".format(system_label))
        return

    level_id = get_level_id(elems[0])
    if level_id == DB.ElementId.InvalidElementId:
        levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
        level_id = levels[0].Id if levels else None
    if level_id is None:
        alert("No se encontro Level valido para crear los ductos.")
        return

    stats = {"main_segments": 0, "branch_segments": 0, "failed": 0}

    t = DB.Transaction(doc, "EstimBot HVAC layout: {0}".format(system_label))
    t.Start()
    try:
        for seg in plan.main_segments:
            start = xyz_from_mm(*seg.start)
            end = xyz_from_mm(*seg.end)
            if start.DistanceTo(end) < 0.01:
                continue
            try:
                DB.Mechanical.Duct.Create(doc, system_type_id, duct_type_elem.Id, level_id, start, end)
                stats["main_segments"] += 1
            except Exception as ex:
                stats["failed"] += 1
                write_log("MAIN DUCT FAIL | error={0}\n".format(ex))

        for branch in plan.branches:
            for seg in branch.segments:
                start = xyz_from_mm(*seg.start)
                end = xyz_from_mm(*seg.end)
                if start.DistanceTo(end) < 0.01:
                    continue
                try:
                    DB.Mechanical.Duct.Create(doc, system_type_id, duct_type_elem.Id, level_id, start, end)
                    stats["branch_segments"] += 1
                except Exception as ex:
                    stats["failed"] += 1
                    write_log("BRANCH DUCT FAIL | error={0}\n".format(ex))

        t.Commit()
    except Exception as ex:
        t.RollBack()
        alert("Error creando layout HVAC:\n{0}".format(ex))
        return

    output.print_md(build_hvac_preview_report(plan))
    output.print_md("- Nivel: `{0}`  Ceiling ctx: `{1}` (z={2:.0f}mm)".format(
        safe_name(doc.GetElement(level_id)), height_ctx.level_name, height_ctx.duct_centerline_z_mm))
    output.print_md("- Segmentos main creados: `{0}`".format(stats["main_segments"]))
    output.print_md("- Segmentos branch creados: `{0}`".format(stats["branch_segments"]))
    output.print_md("- Fallidos: `{0}`".format(stats["failed"]))

    alert(
        "Layout HVAC terminado.\n\nSistema: {0}\nMain: {1}\nBranches: {2}\nFallidos: {3}".format(
            system_label, stats["main_segments"], stats["branch_segments"], stats["failed"]
        )
    )


main()

