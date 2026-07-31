# -*- coding: utf-8 -*-
"""
PYR_S9 - Electrical conduit by circuit for pyRevit.

Creates conduit drops from electrical devices/equipment to 10 cm below ceiling,
groups elements by electrical circuit, creates one real trunk per circuit, and
branches each element to that trunk. Designed for Revit 2024+ / API 2027
compatibility while still tolerating older ElementId APIs.

Construction box rules used by this script:
- receptacles, switches, data, communication, security, fire alarm and similar
  wall devices get a 2x4/device box;
- lighting fixtures get an octagonal/round fixture box;
- panels and electrical equipment are connected by conduit but do not get a
  new device box by default.
"""

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.DB.Electrical import Conduit, ConduitType


doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

CM_TO_FT = 0.03280839895
M_TO_FT = 3.280839895
MM_TO_FT = 1.0 / 304.8
OFFSET_BELOW_CEILING = 10.0 * CM_TO_FT
DEFAULT_FALLBACK_HEIGHT_M = 2.40
HARDCODED_CEILING_HEIGHT_M = DEFAULT_FALLBACK_HEIGHT_M
DEFAULT_CONDUIT_DIAMETER_MM = 20.0
MIN_CONDUIT_LENGTH_FT = 0.12
TRUNK_EXTENSION_FT = 0.50
ROUND_TOL = 0.0001
FLOOR_ROUTE_OFFSET_FT = 10.0 * CM_TO_FT


def element_id_value(element_id):
    """Return an ElementId value across old and new Revit APIs."""
    if element_id is None:
        return None
    if hasattr(element_id, "Value"):
        return element_id.Value
    if hasattr(element_id, "IntegerValue"):
        return element_id.IntegerValue
    return int(element_id)


def bic_value(built_in_category):
    return int(built_in_category)


ELECTRICAL_CATEGORIES = set([
    bic_value(DB.BuiltInCategory.OST_ElectricalFixtures),
    bic_value(DB.BuiltInCategory.OST_LightingDevices),
    bic_value(DB.BuiltInCategory.OST_LightingFixtures),
    bic_value(DB.BuiltInCategory.OST_ElectricalEquipment),
    bic_value(DB.BuiltInCategory.OST_CommunicationDevices),
    bic_value(DB.BuiltInCategory.OST_DataDevices),
    bic_value(DB.BuiltInCategory.OST_FireAlarmDevices),
    bic_value(DB.BuiltInCategory.OST_NurseCallDevices),
    bic_value(DB.BuiltInCategory.OST_SecurityDevices),
    bic_value(DB.BuiltInCategory.OST_TelephoneDevices),
])

DEVICE_BOX_CATEGORIES = set([
    bic_value(DB.BuiltInCategory.OST_ElectricalFixtures),
    bic_value(DB.BuiltInCategory.OST_LightingDevices),
    bic_value(DB.BuiltInCategory.OST_CommunicationDevices),
    bic_value(DB.BuiltInCategory.OST_DataDevices),
    bic_value(DB.BuiltInCategory.OST_FireAlarmDevices),
    bic_value(DB.BuiltInCategory.OST_NurseCallDevices),
    bic_value(DB.BuiltInCategory.OST_SecurityDevices),
    bic_value(DB.BuiltInCategory.OST_TelephoneDevices),
])

OCTAGONAL_BOX_CATEGORIES = set([
    bic_value(DB.BuiltInCategory.OST_LightingFixtures),
])


class ElectricalConnectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return is_electrical_connection_candidate(elem)

    def AllowReference(self, ref, point):
        return False


def safe_name(elem):
    if elem is None:
        return ""
    try:
        value = DB.Element.Name.__get__(elem)
        if value:
            return value
    except Exception:
        pass
    try:
        value = elem.Name
        if value:
            return value
    except Exception:
        pass
    return ""


def get_param_string(elem, built_in_parameter):
    try:
        param = elem.get_Parameter(built_in_parameter)
        if param:
            value = param.AsString()
            if value:
                return value
            value = param.AsValueString()
            if value:
                return value
    except Exception:
        pass
    return ""


def lookup_string(elem, names):
    for name in names:
        try:
            param = elem.LookupParameter(name)
            if param:
                value = param.AsString()
                if value:
                    return value
                value = param.AsValueString()
                if value:
                    return value
        except Exception:
            pass
    return ""


def is_electrical_connection_candidate(elem):
    if elem is None or elem.Category is None:
        return False
    return element_id_value(elem.Category.Id) in ELECTRICAL_CATEGORIES


def is_electrical_system_element(elem):
    try:
        return elem.GetType().Name == "ElectricalSystem"
    except Exception:
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
    try:
        if elem.ConnectorManager:
            for connector in elem.ConnectorManager.Connectors:
                connectors.append(connector)
    except Exception:
        pass
    return connectors


def get_element_systems(elem):
    systems = []

    try:
        mep_model = elem.MEPModel
        if mep_model and hasattr(mep_model, "GetElectricalSystems"):
            for system in mep_model.GetElectricalSystems():
                systems.append(system)
    except Exception:
        pass

    try:
        mep_model = elem.MEPModel
        if mep_model and mep_model.ElectricalSystems:
            for system in mep_model.ElectricalSystems:
                systems.append(system)
    except Exception:
        pass

    for connector in get_connectors(elem):
        try:
            for ref in connector.AllRefs:
                owner = ref.Owner
                if is_electrical_system_element(owner):
                    systems.append(owner)
        except Exception:
            pass

    unique = []
    seen = set()
    for system in systems:
        sid = element_id_value(system.Id)
        if sid not in seen:
            seen.add(sid)
            unique.append(system)
    return unique


def get_point(elem):
    loc = elem.Location
    if loc and hasattr(loc, "Point"):
        return loc.Point

    bb = elem.get_BoundingBox(None)
    if bb:
        return DB.XYZ(
            (bb.Min.X + bb.Max.X) / 2.0,
            (bb.Min.Y + bb.Max.Y) / 2.0,
            (bb.Min.Z + bb.Max.Z) / 2.0
        )
    return None


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

    point = get_point(elem)
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
    if not point or not levels:
        return DB.ElementId.InvalidElementId

    levels.sort(key=lambda level: level.Elevation)
    assigned_level = None
    for level in levels:
        if level.Elevation <= point.Z + ROUND_TOL:
            assigned_level = level
        else:
            break
    return assigned_level.Id if assigned_level else levels[0].Id


def get_system_label(system):
    if system is None:
        return ""

    name = safe_name(system)
    if name:
        return name

    for bip in [
        DB.BuiltInParameter.RBS_ELEC_CIRCUIT_NAME,
        DB.BuiltInParameter.RBS_ELEC_CIRCUIT_NUMBER,
        DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
    ]:
        value = get_param_string(system, bip)
        if value:
            return value

    return "Circuit {0}".format(element_id_value(system.Id))


def get_panel_from_system(system):
    try:
        panel = system.BaseEquipment
        if panel:
            return panel
    except Exception:
        pass
    return None


def get_circuit_info(elem):
    systems = get_element_systems(elem)
    if systems:
        system = systems[0]
        system_id = element_id_value(system.Id)
        panel = get_panel_from_system(system)
        panel_name = safe_name(panel) if panel else ""
        label = get_system_label(system)
        return {
            "key": "circuit:{0}".format(system_id),
            "label": label,
            "system": system,
            "panel": panel,
            "panel_name": panel_name,
            "circuit_number": lookup_string(elem, ["Circuit Number", "Circuit"]),
        }

    panel_name = lookup_string(elem, ["Panel", "Panel Name", "Tablero"])
    circuit_number = lookup_string(elem, ["Circuit Number", "Circuit", "Circuito"])
    if panel_name or circuit_number:
        label = "{0}-{1}".format(panel_name or "NO_PANEL", circuit_number or "NO_CIRCUIT")
        return {
            "key": "param:{0}".format(label),
            "label": label,
            "system": None,
            "panel": None,
            "panel_name": panel_name,
            "circuit_number": circuit_number,
        }

    return {
        "key": "uncircuited",
        "label": "Uncircuited",
        "system": None,
        "panel": None,
        "panel_name": "",
        "circuit_number": "",
    }


def is_lighting_fixture(elem):
    if elem is None or elem.Category is None:
        return False
    return element_id_value(elem.Category.Id) == bic_value(DB.BuiltInCategory.OST_LightingFixtures)


def find_ceiling_bottom_z(point):
    ceilings = DB.FilteredElementCollector(doc) \
        .OfCategory(DB.BuiltInCategory.OST_Ceilings) \
        .WhereElementIsNotElementType()

    best_z = None
    for ceiling in ceilings:
        bb = ceiling.get_BoundingBox(None)
        if not bb:
            continue
        inside_xy = bb.Min.X <= point.X <= bb.Max.X and bb.Min.Y <= point.Y <= bb.Max.Y
        if inside_xy and bb.Min.Z > point.Z:
            candidate = bb.Min.Z
            if best_z is None or candidate < best_z:
                best_z = candidate

    return best_z


def find_ceiling_target_z(elem, point, fallback_z):
    return fallback_z


def get_floor_route_z(elem, point):
    level_id = get_level_id(elem)
    level = doc.GetElement(level_id)
    if level:
        return level.Elevation + FLOOR_ROUTE_OFFSET_FT
    return point.Z - (DEFAULT_FALLBACK_HEIGHT_M * M_TO_FT)


def resolve_route_target(elem, point, fallback_z):
    return find_ceiling_target_z(elem, point, fallback_z), "ceiling"


def get_route_base_point(elem, point, target_z, route_mode):
    if is_lighting_fixture(elem) and route_mode == "ceiling":
        return DB.XYZ(point.X, point.Y, target_z)
    if point.Z > target_z:
        return DB.XYZ(point.X, point.Y, target_z)
    return point


def symbol_display_name(symbol):
    family = ""
    try:
        family = symbol.FamilyName
    except Exception:
        try:
            family = safe_name(symbol.Family)
        except Exception:
            family = ""

    type_name = get_param_string(symbol, DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    if not type_name:
        type_name = safe_name(symbol)

    if family and type_name:
        return "{0} : {1}".format(family, type_name)
    return family or type_name or "Symbol {0}".format(element_id_value(symbol.Id))


def choose_from_elements(title, elements, allow_none=False, none_label="<No colocar>"):
    labels = []
    label_to_element = {}

    if allow_none:
        labels.append(none_label)
        label_to_element[none_label] = None

    for elem in elements:
        label = symbol_display_name(elem) if isinstance(elem, DB.FamilySymbol) else safe_name(elem)
        label = "{0}  [id:{1}]".format(label, element_id_value(elem.Id))
        labels.append(label)
        label_to_element[label] = elem

    labels = sorted(labels)
    selected = forms.SelectFromList.show(labels, title=title, multiselect=False, button_name="Seleccionar")
    if not selected:
        return None
    return label_to_element.get(selected)


def choose_conduit_type():
    conduit_types = list(DB.FilteredElementCollector(doc).OfClass(ConduitType))
    if not conduit_types:
        return None
    return choose_from_elements("Selecciona tipo de conduit", conduit_types)


def find_box_symbols(search_terms, allow_single_digit=False):
    symbols = list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol))
    matches = []
    for symbol in symbols:
        text = symbol_display_name(symbol).lower()
        if is_box_symbol_match(text, search_terms, allow_single_digit):
            matches.append(symbol)
    return matches


def is_box_symbol_match(text, search_terms, allow_single_digit=False):
    excluded = [
        "switch",
        "interruptor",
        "tomacorriente",
        "receptacle",
        "outlet",
        "duplex",
        "gfci",
        "lighting fixture",
        "light fixture",
        "luminaire",
        "luminaria",
        "panel",
        "tablero",
    ]
    for token in excluded:
        if token in text:
            return False

    box_words = ["box", "caja", "junction", "registro", "conexiones", "conexion", "device box", "pull box"]
    has_box_word = any([word in text for word in box_words])
    has_term = any([term.lower() in text for term in search_terms])
    if allow_single_digit and has_box_word and "2" in text:
        has_term = True
    return has_box_word and has_term


def choose_optional_box(title, terms, help_text, allow_single_digit=False):
    matches = find_box_symbols(terms, allow_single_digit)
    if not matches:
        forms.alert(
            "No encontre tipos de caja para: {0}\n\n{1}\n\nSe continuara sin colocar esta caja.".format(
                ", ".join(terms),
                help_text
            )
        )
        return None
    return choose_from_elements(title, matches, allow_none=True)


def collect_selection_or_view():
    selected_ids = list(uidoc.Selection.GetElementIds())
    if selected_ids:
        elems = [doc.GetElement(element_id) for element_id in selected_ids]
        return [elem for elem in elems if is_electrical_connection_candidate(elem)]

    answer = forms.alert(
        "No hay seleccion activa.\n\nSi = seleccionar manualmente.\nNo = usar elementos electricos visibles en la vista activa.",
        yes=True,
        no=True
    )

    if answer:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                ElectricalConnectionFilter(),
                "Selecciona interruptores, tomas, lamparas, paneles y equipos electricos"
            )
            return [doc.GetElement(ref.ElementId) for ref in refs]
        except Exception:
            return []

    collector = DB.FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType()
    return [elem for elem in collector if is_electrical_connection_candidate(elem)]


def group_by_circuit(elems, fallback_height_ft):
    groups = {}
    for elem in elems:
        point = get_point(elem)
        if not point:
            continue

        systems = get_element_systems(elem)
        if not systems:
            continue

        level_id = get_level_id(elem)
        level = doc.GetElement(level_id)
        fallback_z = level.Elevation + fallback_height_ft if level else point.Z + fallback_height_ft
        target_z, route_mode = resolve_route_target(elem, point, fallback_z)
        route_base = get_route_base_point(elem, point, target_z, route_mode)
        circuit = get_circuit_info(elem)
        if not circuit["system"]:
            continue
        level_key = str(element_id_value(level_id))
        target_key = str(round(target_z, 4))
        key = "{0}:{1}:{2}:{3}".format(circuit["key"], level_key, target_key, route_mode)

        if key not in groups:
            groups[key] = {
                "label": circuit["label"],
                "system": circuit["system"],
                "panel": circuit["panel"],
                "panel_name": circuit["panel_name"],
                "circuit_number": circuit["circuit_number"],
                "level_id": level_id,
                "target_z": target_z,
                "route_mode": route_mode,
                "items": [],
            }

        groups[key]["items"].append({
            "element": elem,
            "base": point,
            "route_base": route_base,
            "level_id": level_id,
            "target_z": target_z,
            "route_mode": route_mode,
        })
    return groups


def distance(a, b):
    return a.DistanceTo(b)


def is_short(a, b):
    return distance(a, b) < MIN_CONDUIT_LENGTH_FT


def create_conduit(conduit_type, start, end, level_id, diameter_mm, metadata, stats):
    if is_short(start, end):
        stats["skipped_short"] += 1
        return None
    try:
        conduit = Conduit.Create(doc, conduit_type.Id, start, end, level_id)
        set_conduit_diameter(conduit, diameter_mm)
        write_conduit_metadata(conduit, metadata)
        stats["conduits"] += 1
        return conduit
    except Exception as ex:
        stats["conduit_failed"] += 1
        stats["errors"].append("Conduit failed: {0}".format(ex))
        return None


def set_conduit_diameter(conduit, diameter_mm):
    param = conduit.get_Parameter(DB.BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
    if param and not param.IsReadOnly:
        param.Set(diameter_mm * MM_TO_FT)


def set_param_text(elem, names, value):
    for name in names:
        try:
            param = elem.LookupParameter(name)
            if param and not param.IsReadOnly:
                param.Set(value or "")
                return True
        except Exception:
            pass
    return False


def write_conduit_metadata(conduit, metadata):
    set_param_text(conduit, ["CONS_CircuitId", "Circuit Id"], metadata.get("circuit_id", ""))
    set_param_text(conduit, ["CONS_CircuitName", "Circuit Name"], metadata.get("circuit_name", ""))
    set_param_text(conduit, ["CONS_Panel", "Panel"], metadata.get("panel_name", ""))
    set_param_text(conduit, ["CONS_SourceElementId", "Source Element Id"], metadata.get("source_id", ""))
    set_param_text(conduit, ["CONS_SourceCategory", "Source Category"], metadata.get("source_category", ""))

    comment = "CONS circuit={0}; panel={1}; source={2}".format(
        metadata.get("circuit_name", ""),
        metadata.get("panel_name", ""),
        metadata.get("source_id", "")
    )
    try:
        param = conduit.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if param and not param.IsReadOnly:
            param.Set(comment)
    except Exception:
        pass


def closest_connector(conduit, point):
    if not conduit:
        return None
    try:
        connectors = list(conduit.ConnectorManager.Connectors)
    except Exception:
        return None
    connectors.sort(key=lambda connector: connector.Origin.DistanceTo(point))
    return connectors[0] if connectors else None


def point_key(point):
    return (
        int(round(point.X / ROUND_TOL)),
        int(round(point.Y / ROUND_TOL)),
        int(round(point.Z / ROUND_TOL)),
    )


def place_oct_box_once(symbol, point, level_id, stats):
    if not symbol:
        return None
    key = point_key(point)
    if key in stats["_oct_fallback_points"]:
        return None
    stats["_oct_fallback_points"].add(key)
    return place_family(symbol, point, level_id, stats, "oct_boxes")


def set_element_id_builtin(elem, bip_name, value_id):
    try:
        bip = getattr(DB.BuiltInParameter, bip_name)
        param = elem.get_Parameter(bip)
        if param and not param.IsReadOnly and param.StorageType == DB.StorageType.ElementId:
            param.Set(value_id)
            return True
    except Exception:
        pass
    return False


def set_double_builtin(elem, bip_name, value):
    try:
        bip = getattr(DB.BuiltInParameter, bip_name)
        param = elem.get_Parameter(bip)
        if param and not param.IsReadOnly and param.StorageType == DB.StorageType.Double:
            param.Set(value)
            return True
    except Exception:
        pass
    return False


def set_double_lookup(elem, names, value):
    for name in names:
        try:
            param = elem.LookupParameter(name)
            if param and not param.IsReadOnly and param.StorageType == DB.StorageType.Double:
                param.Set(value)
                return True
        except Exception:
            pass
    return False


def force_family_instance_to_point(inst, point, level_id):
    level = doc.GetElement(level_id)
    if not inst or not level:
        return

    for bip_name in [
        "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM",
        "FAMILY_LEVEL_PARAM",
        "INSTANCE_REFERENCE_LEVEL_PARAM",
        "SCHEDULE_LEVEL_PARAM",
        "LEVEL_PARAM",
    ]:
        set_element_id_builtin(inst, bip_name, level_id)

    offset = point.Z - level.Elevation
    for bip_name in [
        "INSTANCE_FREE_HOST_OFFSET_PARAM",
        "INSTANCE_ELEVATION_PARAM",
        "RBS_OFFSET_PARAM",
        "INSTANCE_SILL_HEIGHT_PARAM",
    ]:
        set_double_builtin(inst, bip_name, offset)

    set_double_lookup(inst, [
        "Offset",
        "Elevation",
        "Elevation from Level",
        "Default Elevation",
        "Altura",
        "Elevacion",
        "Desfase",
        "Desfase de altura",
    ], offset)

    doc.Regenerate()
    current = get_point(inst)
    if current and current.DistanceTo(point) > ROUND_TOL:
        try:
            DB.ElementTransformUtils.MoveElement(doc, inst.Id, point - current)
        except Exception:
            pass


def try_elbow(conduit_a, point_a, conduit_b, point_b, stats):
    key = point_key(point_a)
    if key in stats["_elbow_points"]:
        stats["elbows_skipped_safe"] += 1
        return False
    stats["_elbow_points"].add(key)

    c1 = closest_connector(conduit_a, point_a)
    c2 = closest_connector(conduit_b, point_b)
    if not c1 or not c2:
        stats["elbows_failed"] += 1
        return False
    try:
        doc.Create.NewElbowFitting(c1, c2)
        stats["elbows"] += 1
        return True
    except Exception:
        stats["elbows_failed"] += 1
        return False


def try_tee(conduit_a, point_a, conduit_b, point_b, conduit_branch, point_branch, stats):
    key = point_key(point_branch)
    if key in stats["_tee_points"]:
        stats["tees_skipped_safe"] += 1
        return False
    stats["_tee_points"].add(key)

    c1 = closest_connector(conduit_a, point_a)
    c2 = closest_connector(conduit_b, point_b)
    c3 = closest_connector(conduit_branch, point_branch)
    if not c1 or not c2 or not c3:
        stats["tees_failed"] += 1
        return False
    try:
        doc.Create.NewTeeFitting(c1, c2, c3)
        stats["tees"] += 1
        return True
    except Exception:
        stats["tees_failed"] += 1
        return False


def place_family(symbol, point, level_id, stats, stat_key):
    if not symbol:
        return None
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    level = doc.GetElement(level_id)
    try:
        inst = doc.Create.NewFamilyInstance(point, symbol, level, DB.Structure.StructuralType.NonStructural)
        force_family_instance_to_point(inst, point, level_id)
        stats[stat_key] += 1
        return inst
    except Exception:
        stats["boxes_failed"] += 1
        return None


def category_name(elem):
    try:
        return elem.Category.Name
    except Exception:
        return ""


def route_axis(points):
    xs = [p.X for p in points]
    ys = [p.Y for p in points]
    return "X" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "Y"


def projection_on_trunk(point, axis, const_value, z_value):
    if axis == "X":
        return DB.XYZ(point.X, const_value, z_value)
    return DB.XYZ(const_value, point.Y, z_value)


def coord_on_axis(point, axis):
    return point.X if axis == "X" else point.Y


def make_point_on_axis(coord, axis, const_value, z_value):
    if axis == "X":
        return DB.XYZ(coord, const_value, z_value)
    return DB.XYZ(const_value, coord, z_value)


def unique_sorted_coords(coords):
    result = []
    for coord in sorted(coords):
        if not result or abs(coord - result[-1]) > ROUND_TOL:
            result.append(coord)
    return result


def count_branch_points(branch_records):
    counts = {}
    for projection, branch in branch_records:
        if not branch:
            continue
        key = point_key(projection)
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_metadata(group, elem=None):
    source_id = ""
    source_category = ""
    if elem:
        source_id = str(element_id_value(elem.Id))
        source_category = category_name(elem)
    circuit_id = ""
    if group.get("system"):
        circuit_id = str(element_id_value(group["system"].Id))
    return {
        "circuit_id": circuit_id,
        "circuit_name": group.get("label", ""),
        "panel_name": group.get("panel_name", ""),
        "source_id": source_id,
        "source_category": source_category,
    }


def route_group(group, conduit_type, diameter_mm, box_2x4, box_oct, stats):
    items = group["items"]
    if not items:
        return

    base_points = [item.get("route_base", item["base"]) for item in items]
    panel = group.get("panel")
    panel_point = get_point(panel) if panel else None
    route_points = list(base_points)
    if panel_point:
        route_points.append(panel_point)

    axis = route_axis(route_points)
    route_mode = group.get("route_mode", "ceiling")
    common_z = group.get("target_z") or max([item["target_z"] for item in items])
    stats["ceiling_groups"] += 1

    if axis == "X":
        const_value = sum([p.Y for p in route_points]) / len(route_points)
    else:
        const_value = sum([p.X for p in route_points]) / len(route_points)

    projections = []
    for item in items:
        route_base = item.get("route_base", item["base"])
        item["top"] = DB.XYZ(route_base.X, route_base.Y, common_z)
        item["projection"] = projection_on_trunk(item["top"], axis, const_value, common_z)
        projections.append(item["projection"])

    panel_projection = None
    if panel_point:
        panel_projection = projection_on_trunk(DB.XYZ(panel_point.X, panel_point.Y, common_z), axis, const_value, common_z)
        projections.append(panel_projection)

    coords = [coord_on_axis(p, axis) for p in projections]
    min_coord = min(coords) - TRUNK_EXTENSION_FT
    max_coord = max(coords) + TRUNK_EXTENSION_FT
    node_coords = unique_sorted_coords([min_coord, max_coord] + coords)

    trunk_segments = []
    trunk_by_span = {}
    metadata = build_metadata(group)
    level_id = items[0]["level_id"]

    for idx in range(len(node_coords) - 1):
        start = make_point_on_axis(node_coords[idx], axis, const_value, common_z)
        end = make_point_on_axis(node_coords[idx + 1], axis, const_value, common_z)
        conduit = create_conduit(conduit_type, start, end, level_id, diameter_mm, metadata, stats)
        if conduit:
            trunk_segments.append((node_coords[idx], node_coords[idx + 1], conduit))
            trunk_by_span[(node_coords[idx], node_coords[idx + 1])] = conduit

    branch_records = []

    for item in items:
        elem = item["element"]
        base = item["base"]
        route_base = item.get("route_base", base)
        top = item["top"]
        projection = item["projection"]
        item_level_id = item["level_id"]
        elem_metadata = build_metadata(group, elem)

        if should_place_2x4_box(elem):
            place_family(box_2x4, route_base, item_level_id, stats, "boxes_2x4")
        elif should_place_octagonal_box(elem):
            place_family(box_oct, route_base, item_level_id, stats, "oct_boxes")

        vertical = create_conduit(conduit_type, route_base, top, item_level_id, diameter_mm, elem_metadata, stats)
        branch = create_conduit(conduit_type, top, projection, item_level_id, diameter_mm, elem_metadata, stats)

        if vertical and branch:
            if not try_elbow(vertical, top, branch, top, stats):
                place_oct_box_once(box_oct, top, item_level_id, stats)
        branch_records.append((projection, branch if branch else vertical))

    if panel_point and panel_projection:
        panel_level_id = get_level_id(panel)
        panel_base = panel_point if panel_point.Z <= common_z else DB.XYZ(panel_point.X, panel_point.Y, common_z)
        panel_top = DB.XYZ(panel_base.X, panel_base.Y, common_z)
        panel_metadata = build_metadata(group, panel)
        panel_drop = create_conduit(conduit_type, panel_base, panel_top, panel_level_id, diameter_mm, panel_metadata, stats)
        panel_branch = create_conduit(conduit_type, panel_top, panel_projection, panel_level_id, diameter_mm, panel_metadata, stats)
        if panel_drop and panel_branch:
            if not try_elbow(panel_drop, panel_top, panel_branch, panel_top, stats):
                place_oct_box_once(box_oct, panel_top, panel_level_id, stats)
        branch_records.append((panel_projection, panel_branch if panel_branch else panel_drop))

    doc.Regenerate()

    branch_point_counts = count_branch_points(branch_records)
    for projection, branch in branch_records:
        if not branch:
            continue
        if branch_point_counts.get(point_key(projection), 0) > 1:
            place_oct_box_once(box_oct, projection, level_id, stats)
            stats["tees_skipped_safe"] += 1
            continue
        coord = coord_on_axis(projection, axis)
        left = None
        right = None
        for start_coord, end_coord, conduit in trunk_segments:
            if abs(end_coord - coord) <= ROUND_TOL:
                left = conduit
            if abs(start_coord - coord) <= ROUND_TOL:
                right = conduit
        if left and right:
            if not try_tee(left, projection, right, projection, branch, projection, stats):
                place_oct_box_once(box_oct, projection, level_id, stats)

    stats["circuits"] += 1


def is_panel_or_equipment(elem):
    if elem is None or elem.Category is None:
        return False
    return element_id_value(elem.Category.Id) == bic_value(DB.BuiltInCategory.OST_ElectricalEquipment)


def should_place_2x4_box(elem):
    if elem is None or elem.Category is None:
        return False
    return element_id_value(elem.Category.Id) in DEVICE_BOX_CATEGORIES


def should_place_octagonal_box(elem):
    if elem is None or elem.Category is None:
        return False
    return element_id_value(elem.Category.Id) in OCTAGONAL_BOX_CATEGORIES


def main():
    elems = collect_selection_or_view()
    elems = [elem for elem in elems if get_point(elem)]

    if not elems:
        forms.alert("No se encontraron elementos electricos validos.")
        return

    conduit_type = choose_conduit_type()
    if not conduit_type:
        forms.alert("No se selecciono tipo de conduit.")
        return

    box_2x4 = choose_optional_box(
        "Selecciona caja 2x4 para tomas/switches/dispositivos",
        ["2x4", "2 x 4", "2-4", "4x2", "4 x 2", "4-2", "rectangular", "device", "carga", "sin carga", "conexiones"],
        "Debe ser una familia/tipo de caja, no un tomacorriente ni un interruptor. Tus familias M_Caja de conexiones - Carga/Sin carga ahora aparecen aqui.",
        True
    )
    box_oct = choose_optional_box(
        "Selecciona caja octagonal/redonda para luminarias",
        ["oct", "octagonal", "octogonal", "round", "redonda", "hexagonal", "conexiones"],
        "Debe ser una familia/tipo de caja octagonal/redonda/hexagonal, no una luminaria. Tus familias M_Caja de conexiones simple redonda/hexagonal ahora aparecen aqui.",
        False
    )

    fallback_height_ft = HARDCODED_CEILING_HEIGHT_M * M_TO_FT

    diameter_text = forms.ask_for_string(
        default=str(int(DEFAULT_CONDUIT_DIAMETER_MM)),
        prompt="Diametro nominal de conduit, en mm:",
        title="Conduit por circuito"
    )
    try:
        diameter_mm = float(diameter_text)
    except Exception:
        diameter_mm = DEFAULT_CONDUIT_DIAMETER_MM

    groups = group_by_circuit(elems, fallback_height_ft)
    grouped_count = sum([len(groups[key]["items"]) for key in groups])
    if not groups:
        forms.alert("No se encontraron elementos con ElectricalSystem real.\n\nPara esta prueba se omitieron elementos sin circuito electrico.")
        return

    stats = {
        "circuits": 0,
        "conduits": 0,
        "boxes_2x4": 0,
        "oct_boxes": 0,
        "boxes_failed": 0,
        "elbows": 0,
        "elbows_failed": 0,
        "elbows_skipped_safe": 0,
        "tees": 0,
        "tees_failed": 0,
        "tees_skipped_safe": 0,
        "skipped_short": 0,
        "skipped_uncircuited": len(elems) - grouped_count,
        "conduit_failed": 0,
        "ceiling_groups": 0,
        "floor_fallback_groups": 0,
        "_elbow_points": set(),
        "_tee_points": set(),
        "_oct_fallback_points": set(),
        "errors": [],
    }

    t = DB.Transaction(doc, "PYR_S9 conduit electrico por circuito")
    t.Start()
    try:
        for key in sorted(groups.keys()):
            route_group(groups[key], conduit_type, diameter_mm, box_2x4, box_oct, stats)
        t.Commit()
    except Exception as ex:
        t.RollBack()
        forms.alert("Error creando conduit por circuito:\n{0}".format(ex))
        return

    output.print_md("## PYR_S9 conduit electrico por circuito")
    output.print_md("- Elementos procesados: `{0}`".format(len(elems)))
    output.print_md("- Elementos con circuito real: `{0}`".format(grouped_count))
    output.print_md("- Elementos omitidos sin circuito: `{0}`".format(stats["skipped_uncircuited"]))
    output.print_md("- Circuitos/grupos: `{0}`".format(stats["circuits"]))
    output.print_md("- Conduits creados: `{0}`".format(stats["conduits"]))
    output.print_md("- Cajas 2x4: `{0}`".format(stats["boxes_2x4"]))
    output.print_md("- Cajas octogonales: `{0}`".format(stats["oct_boxes"]))
    output.print_md("- Codos creados/fallidos: `{0}` / `{1}`".format(stats["elbows"], stats["elbows_failed"]))
    output.print_md("- Tees creadas/fallidas: `{0}` / `{1}`".format(stats["tees"], stats["tees_failed"]))
    output.print_md("- Codos omitidos por seguridad: `{0}`".format(stats["elbows_skipped_safe"]))
    output.print_md("- Tees omitidas por seguridad: `{0}`".format(stats["tees_skipped_safe"]))
    output.print_md("- Segmentos omitidos por longitud minima: `{0}`".format(stats["skipped_short"]))
    output.print_md("- Fallos de conduit atrapados: `{0}`".format(stats["conduit_failed"]))
    output.print_md("- Grupos por cielo / suelo: `{0}` / `{1}`".format(stats["ceiling_groups"], stats["floor_fallback_groups"]))
    if stats["errors"]:
        output.print_md("### Errores atrapados")
        for message in stats["errors"][:20]:
            output.print_md("- `{0}`".format(message))

    forms.alert(
        "Conduit por circuito terminado.\n\n"
        "Elementos: {0}\n"
        "Elementos con circuito: {1}\n"
        "Omitidos sin circuito: {2}\n"
        "Circuitos/grupos: {3}\n"
        "Conduits: {4}\n"
        "Cajas 2x4 / octogonales: {5}/{6}\n"
        "Codos omitidos por seguridad: {7}\n"
        "Tees omitidas por seguridad: {8}\n"
        "Grupos cielo/suelo: {9}/{10}\n\n"
        "Revisa el output de pyRevit para detalle.".format(
            len(elems),
            grouped_count,
            stats["skipped_uncircuited"],
            stats["circuits"],
            stats["conduits"],
            stats["boxes_2x4"],
            stats["oct_boxes"],
            stats["elbows_skipped_safe"],
            stats["tees_skipped_safe"],
            stats["ceiling_groups"],
            stats["floor_fallback_groups"]
        )
    )


main()
