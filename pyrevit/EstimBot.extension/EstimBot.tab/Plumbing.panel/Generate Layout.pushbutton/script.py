# -*- coding: utf-8 -*-
"""
EstimBot - Generate Layout

Base scaffold for the new MEP layout generator.
Validates selection, detects valid family instances with physical piping connectors,
and lets the user choose a target system before any layout logic runs.
"""

import os
import sys
import traceback
from math import acos, fabs, pi

from pyrevit import DB, forms, revit, script

from System import Int64


# Raiz de CODIGO (repo git canon): contiene el paquete `scripts`.
SCRIPT_ROOT = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\pyrevit"
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

# Raiz de DATOS/logs: sigue en OneDrive a proposito (no es codigo versionable).
DATA_ROOT = r"D:\OneDrive\Bots\Estimbot"
LOG_DIR = os.path.join(DATA_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "generate_layout.log")
MIN_PIPE_LENGTH_MM = 3.5

from scripts.generate_layout_core import (  # noqa: E402
    ConnectorSnapshot,
    LayoutSettings,
    calculate_pipe_diameter_mm,
    build_layout_plan,
    build_preview_report,
    ft_to_mm,
    find_unique_pipe_for_point,
    mm_to_ft,
    infer_system_labels,
    resolve_piping_system_classification,
    select_pipe_type_name,
)


doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
output.set_title("EstimBot - Generate Layout")

ALLOWED_SYSTEM_LABELS = [
    "Domestic Cold Water",
    "Domestic Hot Water",
    "Sanitary",
    "Vent",
]
ENABLE_TEE_ROUTE = True
AUTOMATION_FLAG = "ESTIMBOT_GL_AUTOMATION"
AUTOMATION_PICK = "ESTIMBOT_GL_AUTOPICK"
AUTOMATION_SYSTEM = "ESTIMBOT_GL_SYSTEM"
AUTOMATION_MODE = "ESTIMBOT_GL_MODE"
AUTOMATION_CONFIRM = "ESTIMBOT_GL_CONFIRM"


def clean(value):
    if value is None:
        return ""
    try:
        return str(value).replace("_x000D_", "").strip()
    except Exception:
        return ""


def compact_text(value):
    text = clean(value).lower()
    return "".join(ch for ch in text if ch.isalnum())


def automation_enabled():
    return clean(os.environ.get(AUTOMATION_FLAG)).lower() in ("1", "true", "yes", "on")


def automation_value(name, default=""):
    return clean(os.environ.get(name) or default)


def automation_confirm_default():
    value = automation_value(AUTOMATION_CONFIRM, "yes").lower()
    return value not in ("0", "false", "no", "off", "cancel")


def alert(message, title="Generate Layout", **kwargs):
    if automation_enabled():
        write_log(
            "AUTOMATION ALERT | title={0} | response={1} | message={2}\n".format(
                title,
                automation_confirm_default(),
                clean(message),
            )
        )
        return automation_confirm_default()
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
    try:
        text = clean(elem_id.ToString())
        if text and text.lstrip("-").isdigit():
            return int(text)
    except Exception:
        pass
    try:
        return int(elem_id)
    except Exception:
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


def is_family_instance(elem):
    return isinstance(elem, DB.FamilyInstance)


def is_in_place_family(elem):
    try:
        symbol = elem.Symbol
        if symbol and symbol.Family and getattr(symbol.Family, "IsInPlace", False):
            return True
    except Exception:
        pass
    return False


def get_connectors(elem):
    connectors = []
    try:
        mep_model = elem.MEPModel
        if mep_model is None:
            return connectors
        connector_manager = mep_model.ConnectorManager
        if connector_manager is None:
            return connectors
        for connector in connector_manager.Connectors:
            connectors.append(connector)
    except Exception:
        return []
    return connectors


def get_connector_owner_name(elem):
    try:
        return safe_name(elem)
    except Exception:
        return ""


def get_category_name(elem):
    try:
        if elem and elem.Category:
            return clean(elem.Category.Name)
    except Exception:
        pass
    return ""


def _append_unique_text(tokens, value):
    text = clean(value)
    if text and text not in tokens:
        tokens.append(text)


def _connector_system_tokens(connector):
    tokens = []
    try:
        pipe_system_type = connector.PipeSystemType
        if pipe_system_type is not None:
            _append_unique_text(tokens, pipe_system_type.ToString())
    except Exception:
        pass
    try:
        mep_system = connector.MEPSystem
        if mep_system is not None:
            for attr_name in ("SystemType", "SystemClassification", "Name"):
                try:
                    _append_unique_text(tokens, getattr(mep_system, attr_name))
                except Exception:
                    pass
            try:
                _append_unique_text(tokens, mep_system.GetType().Name)
            except Exception:
                pass
    except Exception:
        pass
    for attr_name in ("Name", "Description"):
        try:
            _append_unique_text(tokens, getattr(connector, attr_name))
        except Exception:
            pass
    return tokens


def collect_wall_segments():
    segments = []
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.Wall).WhereElementIsNotElementType().ToElements()
    except Exception:
        collector = []

    for wall in collector:
        try:
            location = wall.Location
            if location is None:
                continue
            curve = location.Curve
            if curve is None:
                continue
            start = curve.GetEndPoint(0)
            end = curve.GetEndPoint(1)
            segments.append(
                (
                    ft_to_mm(start.X),
                    ft_to_mm(start.Y),
                    ft_to_mm(end.X),
                    ft_to_mm(end.Y),
                )
            )
        except Exception as ex:
            write_log(
                "WALL SKIP | element={0} | error={1}\n".format(
                    element_id_value(getattr(wall, "Id", None)),
                    ex,
                )
            )
            continue
    return segments


def get_system_kind(connector):
    tokens = _connector_system_tokens(connector)
    return " | ".join(tokens)


def snapshot_connector(elem, connector):
    origin = get_connector_origin(connector)
    owner_name = get_connector_owner_name(elem)
    category_name = get_category_name(elem)
    system_kind = get_system_kind(connector)
    return ConnectorSnapshot(
        element_id=element_id_value(elem.Id),
        family_name=owner_name,
        category_name=category_name,
        system_kind=system_kind,
        is_connected=bool(connector.IsConnected),
        x=ft_to_mm(origin.X),
        y=ft_to_mm(origin.Y),
        z=ft_to_mm(origin.Z),
        flow=float(getattr(connector, "Flow", 0.0) or 0.0),
        fixture_units=float(getattr(connector, "AssignedFixtureUnits", 0.0) or 0.0),
    )


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
    raise ValueError("No se pudo leer el origen del conector.")


def is_physical_piping_connector(connector):
    if connector is None:
        return False
    try:
        if connector.Domain.ToString() != "DomainPiping":
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
    if not is_physical_piping_connector(connector):
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


def get_automation_elements():
    if not automation_enabled():
        return []
    mode = automation_value(AUTOMATION_PICK, "active_view_plumbing").lower()
    elements = []
    if mode == "active_view_plumbing":
        try:
            collector = (
                DB.FilteredElementCollector(doc, doc.ActiveView.Id)
                .OfCategory(DB.BuiltInCategory.OST_PlumbingFixtures)
                .WhereElementIsNotElementType()
            )
            for elem in collector:
                if elem is not None:
                    elements.append(elem)
        except Exception as ex:
            write_log("AUTOMATION PICK FAIL | mode={0} | error={1}\n".format(mode, ex))
            return []
    write_log(
        "AUTOMATION PICK | mode={0} | count={1} | ids={2}\n".format(
            mode,
            len(elements),
            [element_id_value(getattr(elem, "Id", None)) for elem in elements],
        )
    )
    return elements


def get_selected_elements():
    selected_ids = list(uidoc.Selection.GetElementIds())
    if not selected_ids:
        return get_automation_elements()
    elements = []
    for elem_id in selected_ids:
        elem = doc.GetElement(elem_id)
        if elem is not None:
            elements.append(elem)
    return elements


def collect_valid_families(elements):
    valid = []
    skipped = []
    for elem in elements:
        if not is_family_instance(elem):
            skipped.append((elem, "No es FamilyInstance"))
            continue
        if is_in_place_family(elem):
            skipped.append((elem, "Familia in-place"))
            continue
        connectors = get_connectors(elem)
        available = [c for c in connectors if connector_is_available(c)]
        if not available:
            skipped.append((elem, "Sin conectores fisicos disponibles"))
            continue
        valid.append((elem, available))
    return valid, skipped


def _snapshot_dedupe_key(snapshot):
    return (
        snapshot.element_id,
        round(snapshot.x, 0),
        round(snapshot.y, 0),
        round(snapshot.z, 0),
    )


def collect_connector_snapshots(valid_items):
    snapshots = []
    seen_keys = set()
    dropped_by_element = {}
    for elem, connectors in valid_items:
        for connector in connectors:
            if connector is None:
                continue
            try:
                snapshot = snapshot_connector(elem, connector)
            except Exception as ex:
                write_log(
                    "SNAPSHOT FAIL | element={0} | family={1} | category={2} | error={3}\n".format(
                        element_id_value(getattr(elem, "Id", None)),
                        safe_name(elem),
                        get_category_name(elem),
                        ex,
                    )
                )
                continue

            key = _snapshot_dedupe_key(snapshot)
            if key in seen_keys:
                dropped_by_element[snapshot.element_id] = dropped_by_element.get(snapshot.element_id, 0) + 1
                continue
            seen_keys.add(key)
            snapshots.append(snapshot)

    for element_id, dropped_count in dropped_by_element.items():
        write_log(
            "SNAPSHOT DEDUPE | element={0} | dropped={1}\n".format(
                element_id,
                dropped_count,
            )
        )
    return snapshots


def infer_system_options(valid_items):
    snapshots = collect_connector_snapshots(valid_items)
    options = infer_system_labels(snapshots)
    merged = []
    for label in options + list(ALLOWED_SYSTEM_LABELS):
        if label not in merged:
            merged.append(label)
    return merged


def choose_system(options):
    if automation_enabled():
        wanted = automation_value(AUTOMATION_SYSTEM)
        for option in options:
            if compact_text(option) == compact_text(wanted):
                write_log("AUTOMATION SYSTEM | selected={0}\n".format(option))
                return clean(option)
        write_log(
            "AUTOMATION SYSTEM FAIL | wanted={0} | options={1}\n".format(
                wanted,
                options,
            )
        )
        return None
    selected = forms.SelectFromList.show(
        options,
        multiselect=False,
        title="Seleccionar sistema",
        button_name="Continuar",
    )
    if not selected:
        return None
    return clean(selected)


def _system_text_matches(system_label, text):
    target = clean(system_label).lower()
    value = clean(text).lower()
    if not target or not value:
        return False
    compact_target = compact_text(system_label)
    compact_value = compact_text(text)
    if compact_target and compact_target == compact_value:
        return True
    if target in ("domestic cold water", "cold water", "dcw", "potable"):
        return any(
            keyword in value or compact_text(keyword) in compact_value
            for keyword in ("domestic cold water", "cold water", "dcw", "potable")
        )
    if target in ("domestic hot water", "hot water", "dhw"):
        return any(
            keyword in value or compact_text(keyword) in compact_value
            for keyword in ("domestic hot water", "hot water", "dhw")
        )
    if target in ("sanitary", "drenaje", "drainage", "drain", "dw", "waste", "sewer", "soil"):
        return any(
            keyword in value or compact_text(keyword) in compact_value
            for keyword in ("sanitary", "drenaje", "drainage", "drain", "dw", "waste", "sewer", "soil")
        )
    if target == "vent":
        return "vent" in value or "vent" in compact_value
    return target == value or compact_target == compact_value


def connector_matches_system(elem, connector, system_label):
    try:
        kind = get_system_kind(connector)
        if _system_text_matches(system_label, kind):
            return True
        for token in _connector_system_tokens(connector):
            if _system_text_matches(system_label, token):
                return True
        if not clean(kind):
            family = safe_name(elem)
            category = get_category_name(elem)
            return _system_text_matches(system_label, family) or _system_text_matches(system_label, category)
    except Exception:
        pass
    return False


def filter_valid_items_for_system(valid_items, system_label):
    filtered = []
    skipped = []
    for elem, connectors in valid_items:
        matched = [connector for connector in connectors if connector_matches_system(elem, connector, system_label)]
        if matched:
            filtered.append((elem, matched))
            continue
        connector_summaries = []
        for connector in connectors:
            try:
                connector_summaries.append(get_system_kind(connector) or "sin sistema")
            except Exception:
                connector_summaries.append("sin sistema")
        reason = "No connectors match selected system ({0})".format(", ".join(connector_summaries[:3]) or "sin sistema")
        write_log(
            "SYSTEM FILTER SKIP | system={0} | element={1} | family={2} | category={3} | connectors={4} | reason={5}\n".format(
                system_label,
                element_id_value(getattr(elem, "Id", None)),
                safe_name(elem),
                get_category_name(elem),
                connector_summaries,
                reason,
            )
        )
        skipped.append((
            elem,
            reason,
        ))
    return filtered, skipped


def build_summary(valid_items, skipped_items, system_label):
    lines = []
    lines.append("## Generate Layout - validacion base")
    lines.append("- Sistema elegido: `{0}`".format(system_label or "sin seleccionar"))
    lines.append("- Familias validas: `{0}`".format(len(valid_items)))
    lines.append("- Familias omitidas: `{0}`".format(len(skipped_items)))

    if skipped_items:
        lines.append("### Omitidos")
        for elem, reason in skipped_items:
            lines.append("- `{0}`: {1}".format(safe_name(elem) or "Elemento", reason))

    return "\n".join(lines)


def build_plan_summary(plan):
    return build_preview_report(plan)


def write_log(text):
    try:
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        with open(LOG_FILE, "a") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
    except Exception:
        pass


def choose_execution_mode():
    if automation_enabled():
        wanted = automation_value(AUTOMATION_MODE, "crear").lower()
        if wanted in ("preview", "vista previa", "vista previa segura"):
            write_log("AUTOMATION MODE | selected=Vista previa segura\n")
            return "vista previa segura"
        write_log("AUTOMATION MODE | selected=Crear geometria real\n")
        return "crear geometria real"
    mode = forms.SelectFromList.show(
        ["Vista previa segura", "Crear geometria real"],
        multiselect=False,
        title="Modo de ejecucion",
        button_name="Continuar",
    )
    if not mode:
        return ""
    return clean(mode)


def _pipe_type_preference_keywords(system_label):
    return _pipe_type_rules(system_label, "")["preferred"]


def _pipe_type_rules(system_label, classification_name):
    label = clean(system_label).lower()
    classification = clean(classification_name).lower()

    if classification == "domestichotwater":
        return {
            "preferred": ["domestic hot water", "hot water", "dhw", "cpvc", "copper", "pex", "default"],
            "forbidden": ["chilled", "hydronic", "sanitary", "dwv", "waste", "drain", "sewer", "soil", "vent", "cold water", "dcw", "potable"],
        }
    if classification == "domesticcoldwater":
        return {
            "preferred": ["potable", "domestic cold water", "cold water", "dcw", "pvc normal", "pvc", "pex", "copper", "cpvc", "default"],
            "forbidden": ["chilled", "hydronic", "sanitary", "dwv", "waste", "drain", "sewer", "soil", "vent", "hot water", "dhw"],
        }
    if classification == "sanitary":
        return {
            "preferred": ["pvc - sanitario", "pvc sanitario", "sanitario", "pvc - dwv", "dwv", "waste", "drain", "sewer", "soil", "pvc", "default"],
            "forbidden": ["chilled", "hydronic", "hot water", "dhw", "cold water", "dcw", "potable", "vent"],
        }
    if classification == "vent":
        return {
            "preferred": ["vent", "pvc", "default"],
            "forbidden": ["chilled", "hydronic", "hot water", "dhw", "cold water", "dcw", "potable", "sanitary", "dwv", "waste", "drain", "sewer", "soil"],
        }
    if label in ("domestic hot water", "dhw", "hot water"):
        return _pipe_type_rules(system_label, "DomesticHotWater")
    if label in ("domestic cold water", "dcw", "potable", "cold water"):
        return _pipe_type_rules(system_label, "DomesticColdWater")
    if label in ("sanitary", "drenaje", "drainage", "drain", "dw", "waste", "sewer", "soil"):
        return _pipe_type_rules(system_label, "Sanitary")
    if label == "vent":
        return _pipe_type_rules(system_label, "Vent")
    return {
        "preferred": [label, "default", "pvc", "cpvc", "copper"],
        "forbidden": ["chilled", "hydronic"],
    }


def _pipe_type_score(system_label, classification_name, pipe_type_name):
    name = clean(pipe_type_name).lower()
    score = 0
    classification = clean(classification_name).lower()
    rules = _pipe_type_rules(system_label, classification_name)
    prefs = rules["preferred"]
    forbidden = rules["forbidden"]

    if any(token and token in name for token in forbidden):
        return -1000

    if classification == "domestichotwater":
        score += 10 if any(keyword in name for keyword in ("domestic hot water", "hot water", "dhw", "cpvc")) else 0
    elif classification == "domesticcoldwater":
        score += 10 if any(keyword in name for keyword in ("potable", "domestic cold water", "cold water", "dcw", "pvc normal")) else 0
    elif classification == "sanitary":
        score += 10 if any(keyword in name for keyword in ("pvc - sanitario", "pvc sanitario", "sanitario", "pvc - dwv", "dwv", "drain", "waste", "sewer", "soil")) else 0
    elif classification == "vent":
        score += 10 if "vent" in name else 0

    for index, keyword in enumerate(prefs):
        if keyword and keyword in name:
            score += 100 - (index * 10)

    return score


def get_pipe_type(doc, system_label, snapshots):
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.Plumbing.PipeType).ToElements()
    except Exception:
        collector = []

    pipe_types = []
    for pipe_type in collector:
        if pipe_type is not None:
            pipe_types.append(pipe_type)

    if not pipe_types:
        return None

    names = [safe_name(pipe_type) for pipe_type in pipe_types]
    classification_name = build_piping_classification(system_label, snapshots)
    exact_names = {
        "domestichotwater": ["cpvc"],
        "domesticcoldwater": ["potable"],
        "sanitary": ["pvc - sanitario", "pvc sanitario", "sanitario"],
    }
    if classification_name:
        normalized_classification = clean(classification_name).lower()
        for exact_name in exact_names.get(normalized_classification, []):
            for pipe_type in pipe_types:
                pipe_type_name = clean(safe_name(pipe_type)).lower()
                if pipe_type_name == exact_name or exact_name in pipe_type_name:
                    write_log(
                        "PIPETYPE EXACT | system={0} | classification={1} | pipe_type={2}\n".format(
                            system_label,
                            classification_name,
                            safe_name(pipe_type),
                        )
                    )
                    return pipe_type

    candidates = []
    for pipe_type in pipe_types:
        pipe_type_name = safe_name(pipe_type)
        score = _pipe_type_score(system_label, classification_name, pipe_type_name)
        candidates.append((score, pipe_type_name, pipe_type))

    candidates.sort(key=lambda item: (item[0], clean(item[1])), reverse=True)
    selected_score, selected_name, selected_pipe_type = candidates[0]
    write_log(
        "PIPETYPE CANDIDATES | system={0} | classification={1} | top={2}\n".format(
            system_label,
            classification_name,
            ", ".join("{0}:{1}".format(name, score) for score, name, _pipe_type in candidates[:5]),
        )
    )

    if selected_score <= 0:
        safe_candidates = [pipe_type for score, _name, pipe_type in candidates if score > -1000]
        if safe_candidates:
            safe_candidates.sort(key=lambda item: clean(safe_name(item)))
            fallback = safe_candidates[0]
            write_log(
                "PIPETYPE FALLBACK SAFE | system={0} | classification={1} | pipe_type={2}\n".format(
                    system_label,
                    classification_name,
                    safe_name(fallback),
                )
            )
            return fallback
        write_log(
            "PIPETYPE FAIL | system={0} | classification={1} | reason=no safe PipeType candidate\n".format(
                system_label,
                classification_name,
            )
        )
        return None

    write_log(
        "PIPETYPE OK | system={0} | classification={1} | pipe_type={2}\n".format(
            system_label,
            classification_name,
            selected_name,
        )
    )
    return selected_pipe_type


def pipe_matches_system_label(pipe, system_label):
    tokens = []
    try:
        mep_system = pipe.MEPSystem
        if mep_system is not None:
            for attr_name in ("SystemType", "SystemClassification", "Name"):
                try:
                    tokens.append(getattr(mep_system, attr_name))
                except Exception:
                    pass
    except Exception:
        pass
    tokens = [clean(token) for token in tokens if clean(token)]
    if not tokens:
        return True
    return any(_system_text_matches(system_label, token) for token in tokens)


def get_piping_system_type_id(doc, system_label, snapshots):
    target_classification = None
    classification_name = ""
    try:
        classification_name = build_piping_classification(system_label, snapshots)
        target_classification = getattr(DB.MEPSystemClassification, classification_name)
    except Exception:
        return None

    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.Plumbing.PipingSystemType).ToElements()
    except Exception:
        collector = []

    for system_type in collector:
        try:
            if system_type.SystemClassification == target_classification:
                return system_type.Id
        except Exception:
            continue
    return None


def build_piping_classification(system_label, snapshots):
    return resolve_piping_system_classification(system_label, snapshots)


def get_element_by_id_value(elem_id):
    try:
        if isinstance(elem_id, DB.ElementId):
            return doc.GetElement(elem_id)
        if elem_id is None:
            return None
        return doc.GetElement(DB.ElementId(int(elem_id)))
    except Exception:
        return None


def resolve_level_id_for_element(elem, fallback_z_ft):
    try:
        level_id = elem.LevelId
        if level_id and element_id_value(level_id) not in (None, -1):
            return level_id
    except Exception:
        pass

    try:
        level_id = DB.Level.GetNearestLevelId(doc, fallback_z_ft)
        if isinstance(level_id, tuple):
            level_id = level_id[0]
        return level_id
    except Exception:
        return DB.ElementId.InvalidElementId


def mm_point_to_xyz(point):
    return DB.XYZ(
        point[0] / 304.8,
        point[1] / 304.8,
        point[2] / 304.8,
    )


def segment_length_mm(segment):
    try:
        return float(segment.length_mm)
    except Exception:
        return 0.0


def create_pipe_segment(doc, system_type_id, pipe_type_id, level_id, segment):
    if segment_length_mm(segment) < MIN_PIPE_LENGTH_MM:
        return None, "segment too short"

    start_xyz = mm_point_to_xyz(segment.start)
    end_xyz = mm_point_to_xyz(segment.end)
    pipe = DB.Plumbing.Pipe.Create(doc, system_type_id, pipe_type_id, level_id, start_xyz, end_xyz)
    return pipe, ""


def set_pipe_diameter(pipe, diameter_mm):
    if pipe is None:
        return False
    try:
        diameter_param = pipe.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if diameter_param is None or diameter_param.IsReadOnly:
            return False
        diameter_param.Set(mm_to_ft(diameter_mm))
        return True
    except Exception:
        return False


def get_pipe_connectors(pipe):
    connectors = []
    try:
        manager = pipe.ConnectorManager
    except Exception:
        manager = None
    if manager is None:
        try:
            manager = pipe.MEPModel.ConnectorManager
        except Exception:
            manager = None
    if manager is None:
        return connectors
    try:
        for connector in manager.Connectors:
            connectors.append(connector)
    except Exception:
        return []
    return connectors


def connector_origin_mm(connector):
    origin = get_connector_origin(connector)
    return ft_to_mm(origin.X), ft_to_mm(origin.Y), ft_to_mm(origin.Z)


def get_connector_distance_ft(connector, point_xyz):
    try:
        return connector.Origin.DistanceTo(point_xyz)
    except Exception:
        try:
            origin = connector.Origin
            dx = origin.X - point_xyz.X
            dy = origin.Y - point_xyz.Y
            dz = origin.Z - point_xyz.Z
            return (dx * dx + dy * dy + dz * dz) ** 0.5
        except Exception:
            return 1e9


def pick_open_connector(pipe, point_xyz, system_label=None, require_system_match=False):
    connectors = get_pipe_connectors(pipe)
    candidates = []
    for connector in connectors:
        try:
            if connector.IsConnected:
                continue
        except Exception:
            pass
        candidates.append(connector)
    if not candidates:
        candidates = connectors
    if not candidates:
        return None
    if system_label:
        compatible = []
        token_present = False
        for connector in candidates:
            token = get_system_kind(connector)
            if clean(token):
                token_present = True
                if _system_text_matches(system_label, token):
                    compatible.append(connector)
        if compatible:
            candidates = compatible
        elif require_system_match and token_present:
            return None
    candidates.sort(key=lambda connector: get_connector_distance_ft(connector, point_xyz))
    return candidates[0]


def pipe_contains_point(pipe, point_xyz, tolerance_ft=0.01):
    try:
        curve = pipe.Location.Curve
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return False

    vx = end.X - start.X
    vy = end.Y - start.Y
    vz = end.Z - start.Z
    wx = point_xyz.X - start.X
    wy = point_xyz.Y - start.Y
    wz = point_xyz.Z - start.Z

    seg_len_sq = vx * vx + vy * vy + vz * vz
    if seg_len_sq <= 1e-12:
        dx = point_xyz.X - start.X
        dy = point_xyz.Y - start.Y
        dz = point_xyz.Z - start.Z
        return (dx * dx + dy * dy + dz * dz) ** 0.5 <= tolerance_ft

    t = (vx * wx + vy * wy + vz * wz) / seg_len_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0

    closest_x = start.X + t * vx
    closest_y = start.Y + t * vy
    closest_z = start.Z + t * vz
    dx = point_xyz.X - closest_x
    dy = point_xyz.Y - closest_y
    dz = point_xyz.Z - closest_z
    return (dx * dx + dy * dy + dz * dz) ** 0.5 <= tolerance_ft


def pipe_distance_to_point(pipe, point_xyz):
    try:
        curve = pipe.Location.Curve
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return 1e9

    vx = end.X - start.X
    vy = end.Y - start.Y
    vz = end.Z - start.Z
    wx = point_xyz.X - start.X
    wy = point_xyz.Y - start.Y
    wz = point_xyz.Z - start.Z

    seg_len_sq = vx * vx + vy * vy + vz * vz
    if seg_len_sq <= 1e-12:
        dx = point_xyz.X - start.X
        dy = point_xyz.Y - start.Y
        dz = point_xyz.Z - start.Z
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    t = (vx * wx + vy * wy + vz * wz) / seg_len_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0

    closest_x = start.X + t * vx
    closest_y = start.Y + t * vy
    closest_z = start.Z + t * vz
    dx = point_xyz.X - closest_x
    dy = point_xyz.Y - closest_y
    dz = point_xyz.Z - closest_z
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def find_pipe_id_for_point(pipe_ids, point_xyz):
    best_pipe_id = None
    best_distance = None
    for pipe_id in pipe_ids:
        try:
            pipe = get_element_by_id_value(pipe_id)
        except Exception:
            pipe = None
        if pipe is None:
            continue
        distance = pipe_distance_to_point(pipe, point_xyz)
        if pipe_contains_point(pipe, point_xyz):
            return pipe_id
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_pipe_id = pipe_id
    return best_pipe_id


def make_element_id(int_value):
    return DB.ElementId(int(int_value))


def nudge_point_inside_pipe(pipe, point_xyz, offset_ft=0.01):
    try:
        curve = pipe.Location.Curve
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
    except Exception:
        return point_xyz

    dx = end.X - start.X
    dy = end.Y - start.Y
    dz = end.Z - start.Z
    length_sq = dx * dx + dy * dy + dz * dz
    if length_sq <= 1e-12:
        return point_xyz

    px = point_xyz.X - start.X
    py = point_xyz.Y - start.Y
    pz = point_xyz.Z - start.Z
    t = (dx * px + dy * py + dz * pz) / length_sq

    if t <= 0.001:
        direction = 1.0
    elif t >= 0.999:
        direction = -1.0
    else:
        return point_xyz

    length = length_sq ** 0.5
    if length <= 1e-12:
        return point_xyz

    scale = offset_ft / length
    return DB.XYZ(
        point_xyz.X + (dx * scale * direction),
        point_xyz.Y + (dy * scale * direction),
        point_xyz.Z + (dz * scale * direction),
    )


def project_point_to_main_side(side, tie_point_xyz, main_segment):
    start = mm_point_to_xyz(main_segment.start)
    end = mm_point_to_xyz(main_segment.end)

    if side in ("north", "south"):
        x_min = min(start.X, end.X)
        x_max = max(start.X, end.X)
        return DB.XYZ(
            max(min(tie_point_xyz.X, x_max), x_min),
            start.Y,
            start.Z,
        )

    if side in ("east", "west"):
        y_min = min(start.Y, end.Y)
        y_max = max(start.Y, end.Y)
        return DB.XYZ(
            start.X,
            max(min(tie_point_xyz.Y, y_max), y_min),
            start.Z,
        )

    return tie_point_xyz


def get_point_level_mm(point_xyz):
    try:
        return ft_to_mm(point_xyz.Z)
    except Exception:
        return 0.0


def connect_two_pipes_with_elbow(pipe_a, pipe_b, point_xyz, label, detail, system_label=None):
    if pipe_a is None or pipe_b is None:
        return False
    connector_a = pick_open_connector(pipe_a, point_xyz, system_label=system_label, require_system_match=True if system_label else False)
    connector_b = pick_open_connector(pipe_b, point_xyz, system_label=system_label, require_system_match=True if system_label else False)
    if connector_a is None or connector_b is None:
        write_log(
            "FITTING FAIL | type=elbow | label={0} | detail={1} | reason=no connectors\n".format(
                label,
                detail,
            )
        )
        return False
    try:
        doc.Create.NewElbowFitting(connector_a, connector_b)
        write_log(
            "FITTING OK | type=elbow | label={0} | detail={1} | a={2} | b={3}\n".format(
                label,
                detail,
                element_id_value(pipe_a.Id),
                element_id_value(pipe_b.Id),
            )
        )
        return True
    except Exception as ex:
        try:
            connector_a.ConnectTo(connector_b)
            write_log(
                "FITTING FALLBACK OK | type=connectto | label={0} | detail={1} | a={2} | b={3}\n".format(
                    label,
                    detail,
                    element_id_value(pipe_a.Id),
                    element_id_value(pipe_b.Id),
                )
            )
            return True
        except Exception as fallback_ex:
            write_log(
                "FITTING FAIL | type=elbow | label={0} | detail={1} | error={2} | fallback={3}\n".format(
                    label,
                    detail,
                    ex,
                    fallback_ex,
                )
            )
        return False


def pick_main_pipe_for_point(main_pipes, tie_point_xyz, system_label=None):
    candidates = []
    for pipe in main_pipes:
        if pipe is None:
            continue
        if system_label and not pipe_matches_system_label(pipe, system_label):
            continue
        try:
            distance = pipe_distance_to_point(pipe, tie_point_xyz)
        except Exception:
            distance = 1e9
        candidates.append((distance, pipe))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def find_main_segment_by_point(main_pipes, tie_point_xyz):
    return find_unique_pipe_for_point(main_pipes, tie_point_xyz)


def get_pipe_diameter_mm(pipe):
    if pipe is None:
        return None
    try:
        diameter_param = pipe.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if diameter_param is None:
            return None
        return ft_to_mm(diameter_param.AsDouble())
    except Exception:
        return None


def log_pipe_state(label, pipe):
    if pipe is None:
        write_log("PIPE STATE | label={0} | pipe=None\n".format(label))
        return
    try:
        pipe_id = element_id_value(pipe.Id)
    except Exception:
        pipe_id = None
    try:
        diameter_mm = get_pipe_diameter_mm(pipe)
    except Exception:
        diameter_mm = None
    try:
        mep_system = safe_name(getattr(pipe, "MEPSystem", None))
    except Exception:
        mep_system = ""
    try:
        pipe_type_id = element_id_value(getattr(getattr(pipe, "PipeType", None), "Id", None))
    except Exception:
        pipe_type_id = None
    write_log(
        "PIPE STATE | label={0} | pipe_id={1} | diameter_mm={2} | mep_system={3} | pipe_type_id={4}\n".format(
            label,
            pipe_id,
            diameter_mm,
            mep_system,
            pipe_type_id,
        )
    )


def debug_connector_summary(connector):
    if connector is None:
        return "None"
    try:
        owner_id = element_id_value(getattr(getattr(connector, "Owner", None), "Id", None))
    except Exception:
        owner_id = "unknown"
    try:
        origin = connector.Origin
    except Exception:
        origin = None
    try:
        connected = connector.IsConnected
    except Exception:
        connected = "unknown"
    try:
        direction = connector.Direction
    except Exception:
        direction = None
    try:
        system_kind = get_system_kind(connector)
    except Exception:
        system_kind = None
    return "owner={0} | connected={1} | origin={2} | direction={3} | system={4} | type={5}".format(
        owner_id,
        connected,
        origin,
        direction,
        system_kind,
        type(connector).__name__,
    )


def _xyz_tuple(vec):
    if vec is None:
        return None
    try:
        return (vec.X, vec.Y, vec.Z)
    except Exception:
        return None


def _xyz_dot(a, b):
    return (a.X * b.X) + (a.Y * b.Y) + (a.Z * b.Z)


def _xyz_len(v):
    return (_xyz_dot(v, v)) ** 0.5


def angle_deg(v1, v2):
    try:
        len1 = _xyz_len(v1)
        len2 = _xyz_len(v2)
        if len1 <= 1e-12 or len2 <= 1e-12:
            return None
        ratio = _xyz_dot(v1, v2) / (len1 * len2)
        if ratio > 1.0:
            ratio = 1.0
        elif ratio < -1.0:
            ratio = -1.0
        return acos(ratio) * 180.0 / pi
    except Exception:
        return None


def tee_connector_diagnostics(connector):
    if connector is None:
        return "None"
    try:
        owner_id = element_id_value(getattr(getattr(connector, "Owner", None), "Id", None))
    except Exception:
        owner_id = None
    try:
        origin = connector.Origin
    except Exception:
        origin = None
    try:
        connector_type = connector.ConnectorType
    except Exception:
        connector_type = None
    try:
        is_connected = connector.IsConnected
    except Exception:
        is_connected = None
    try:
        radius = connector.Radius
    except Exception:
        radius = None
    try:
        diameter = connector.Diameter
    except Exception:
        diameter = None
    try:
        domain = connector.Domain
    except Exception:
        domain = None
    try:
        mep_system = getattr(connector, "MEPSystem", None)
    except Exception:
        mep_system = None
    try:
        cs = connector.CoordinateSystem
    except Exception:
        cs = None
    basis_x = _xyz_tuple(getattr(cs, "BasisX", None)) if cs is not None else None
    basis_y = _xyz_tuple(getattr(cs, "BasisY", None)) if cs is not None else None
    basis_z = _xyz_tuple(getattr(cs, "BasisZ", None)) if cs is not None else None
    try:
        direction = connector.Direction
    except Exception:
        direction = None
    try:
        is_primary = connector.IsPrimary
    except Exception:
        is_primary = None
    try:
        is_secondary = connector.IsSecondary
    except Exception:
        is_secondary = None
    return (
        "owner={owner} | origin={origin} | ConnectorType={ctype} | IsConnected={connected} | "
        "Radius={radius} | Diameter={diameter} | Domain={domain} | MEPSystem={mep_system} | "
        "BasisX={bx} | BasisY={by} | BasisZ={bz} | Direction={direction} | "
        "IsPrimary={primary} | IsSecondary={secondary}"
    ).format(
        owner=owner_id,
        origin=origin,
        ctype=connector_type,
        connected=is_connected,
        radius=radius,
        diameter=diameter,
        domain=domain,
        mep_system=clean(mep_system) or mep_system,
        bx=basis_x,
        by=basis_y,
        bz=basis_z,
        direction=direction,
        primary=is_primary,
        secondary=is_secondary,
    )


def part_family_name(part):
    try:
        fam = getattr(part, "Family", None)
    except Exception:
        fam = None
    return safe_name(fam)


def part_content_part_type_text(part):
    try:
        fam = getattr(part, "Family", None)
    except Exception:
        fam = None
    if fam is None:
        return ""
    try:
        pt_param = fam.get_Parameter(DB.BuiltInParameter.FAMILY_CONTENT_PART_TYPE)
    except Exception:
        pt_param = None
    if pt_param is None:
        return ""
    try:
        return clean(pt_param.AsValueString())
    except Exception:
        return ""


def part_is_tee_like(part, part_name):
    """OR de 3 senales: type name, family name, y PartType (FAMILY_CONTENT_PART_TYPE).
    part_name = safe_name(part) es el TYPE name (ej. "Standard"), no el family name,
    por eso NO basta con revisar solo part_name."""
    try:
        if "tee" in clean(part_name).lower():
            return True
    except Exception:
        pass
    try:
        fam_name = part_family_name(part)
        if "tee" in clean(fam_name).lower():
            return True
    except Exception:
        pass
    try:
        pt_text = part_content_part_type_text(part)
        if "tee" in pt_text.lower():
            return True
    except Exception:
        pass
    return False


def get_preferred_junction_type(pipe_type):
    """Lee pipe_type.RoutingPreferenceManager.PreferredJunctionType.
    Devuelve el texto ("Tee", "Tap", ...) o "" si no se pudo leer."""
    if pipe_type is None:
        return ""
    try:
        rpm = pipe_type.RoutingPreferenceManager
    except Exception:
        return ""
    if rpm is None:
        return ""
    try:
        return clean(rpm.PreferredJunctionType.ToString())
    except Exception:
        return ""


def tee_routing_preflight(pipe_type, main_diameter_mm):
    if pipe_type is None:
        write_log("TEE PREFLIGHT FAIL | reason=missing pipe type | diameter_mm={0}\n".format(main_diameter_mm))
        return False
    try:
        rpm = pipe_type.RoutingPreferenceManager
    except Exception:
        rpm = None
    if rpm is None:
        write_log(
            "TEE PREFLIGHT FAIL | reason=missing routing preference manager | pipe_type={0} | diameter_mm={1}\n".format(
                safe_name(pipe_type),
                main_diameter_mm,
            )
        )
        return False

    try:
        junction_count = rpm.GetNumberOfRules(DB.RoutingPreferenceRuleGroupType.Junctions)
    except Exception as ex:
        write_log(
            "TEE PREFLIGHT FAIL | reason=cannot read junction rules | pipe_type={0} | error={1}\n".format(
                safe_name(pipe_type),
                ex,
            )
        )
        return False

    write_log(
        "TEE PREFLIGHT | pipe_type={0} | diameter_mm={1} | junction_rules={2}\n".format(
            safe_name(pipe_type),
            main_diameter_mm,
            junction_count,
        )
    )

    found_loaded_tee = False
    for index in range(junction_count):
        try:
            rule = rpm.GetRule(DB.RoutingPreferenceRuleGroupType.Junctions, index)
        except Exception as ex:
            write_log(
                "TEE PREFLIGHT RULE FAIL | index={0} | error={1}\n".format(index, ex)
            )
            continue

        try:
            part_id = getattr(rule, "MEPPartId", DB.ElementId.InvalidElementId)
        except Exception:
            part_id = DB.ElementId.InvalidElementId
        part = get_element_by_id_value(part_id)
        part_name = safe_name(part)
        part_id_value = element_id_value(part_id)
        part_exists = part is not None
        part_is_tee = part_exists and part_is_tee_like(part, part_name)
        if part_is_tee:
            found_loaded_tee = True

        write_log(
            "TEE PREFLIGHT RULE | index={0} | part_id={1} | part_name={2} | family_name={3} | part_type={4} | exists={5} | tee_like={6}\n".format(
                index,
                part_id_value,
                part_name,
                part_family_name(part) if part_exists else "",
                part_content_part_type_text(part) if part_exists else "",
                part_exists,
                part_is_tee,
            )
        )

    if not found_loaded_tee:
        write_log(
            "TEE PREFLIGHT FAIL | reason=no loaded tee family in junctions | pipe_type={0} | diameter_mm={1}\n".format(
                safe_name(pipe_type),
                main_diameter_mm,
            )
        )
        return False

    write_log(
        "TEE PREFLIGHT OK | pipe_type={0} | diameter_mm={1}\n".format(
            safe_name(pipe_type),
            main_diameter_mm,
        )
    )
    return True


def _try_takeoff(branch_pipe, main_pipe, tie_point_xyz, system_label):
    """Conecta el ramal al main con NewTakeoffFitting (tap) — NO rompe la curva del main.
    Via limpia (no requiere tee family en routing prefs). Devuelve (ok, info)."""
    if branch_pipe is None or main_pipe is None:
        return False, "missing pipe"
    branch_conn = pick_open_connector(
        branch_pipe, tie_point_xyz,
        system_label=system_label, require_system_match=bool(system_label),
    )
    if branch_conn is None:
        return False, "no open branch connector"
    sub_tx = DB.SubTransaction(doc)
    sub_tx.Start()
    try:
        fitting = doc.Create.NewTakeoffFitting(branch_conn, main_pipe)
        if fitting is None:
            sub_tx.RollBack()
            return False, "takeoff returned None"
        sub_tx.Commit()
        return True, element_id_value(getattr(fitting, "Id", None))
    except Exception as ex:
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "takeoff error: {0}".format(ex)


def connect_branch_to_main(main_pipes, branch_tie_pipe, tie_point_xyz, system_label, main_diameter_mm, pipe_type=None):
    try:
        main_segment = find_main_segment_by_point(main_pipes, tie_point_xyz)
    except ValueError:
        write_log(
            "TEE FAIL | reason=ambiguous main segment | point={0}\n".format(tie_point_xyz)
        )
        return False

    if main_segment is None:
        write_log(
            "TEE FAIL | reason=main pipe not found | point={0}\n".format(tie_point_xyz)
        )
        return False

    target_pipe = main_segment
    target_pipe_id = element_id_value(target_pipe.Id)

    write_log(
        "IDEA 1 OK | pipe_id={0} | point={1}\n".format(
            target_pipe_id,
            tie_point_xyz,
        )
    )

    branch_connector_debug = None
    main_connector_debug = None
    try:
        branch_connector_debug = pick_open_connector(branch_tie_pipe, tie_point_xyz, system_label=system_label, require_system_match=True)
    except Exception:
        branch_connector_debug = None
    try:
        main_connector_debug = pick_open_connector(target_pipe, tie_point_xyz, system_label=system_label, require_system_match=True)
    except Exception:
        main_connector_debug = None

    write_log(
        "CONNECT DEBUG |\n  branch_id={0}\n  main_id={1}\n  type(branch_connector)={2}\n  type(main_connector)={3}\n  type(branch_id)={4}\n  type(main_id)={5}\n".format(
            element_id_value(branch_tie_pipe.Id),
            target_pipe_id,
            type(branch_connector_debug).__name__ if branch_connector_debug is not None else "NoneType",
            type(main_connector_debug).__name__ if main_connector_debug is not None else "NoneType",
            type(branch_tie_pipe.Id).__name__,
            type(target_pipe.Id).__name__,
        )
    )

    if not set_pipe_diameter(branch_tie_pipe, main_diameter_mm):
        write_log(
            "TEE FAIL | reason=branch diameter not aligned | main={0} | branch={1} | diameter_mm={2}\n".format(
                target_pipe_id,
                element_id_value(branch_tie_pipe.Id),
                main_diameter_mm,
            )
        )
        return False

    preferred_junction = get_preferred_junction_type(pipe_type)
    tee_first = preferred_junction == "tee"
    write_log(
        "JUNCTION ORDER | pipe_type={0} | preferred_junction={1} | order={2}\n".format(
            safe_name(pipe_type),
            preferred_junction or "unknown",
            "tee-first" if tee_first else "takeoff-first",
        )
    )

    def _attempt_takeoff():
        ok, info = _try_takeoff(branch_tie_pipe, target_pipe, tie_point_xyz, system_label)
        if ok:
            write_log(
                "TAKEOFF OK | main={0} | branch={1} | fitting={2} | point={3}\n".format(
                    target_pipe_id,
                    element_id_value(branch_tie_pipe.Id),
                    info,
                    tie_point_xyz,
                )
            )
        else:
            write_log(
                "TAKEOFF FAIL | main={0} | branch={1} | reason={2}\n".format(
                    target_pipe_id,
                    element_id_value(branch_tie_pipe.Id),
                    info,
                )
            )
        return ok, info

    def _attempt_tee():
        ok, info = _try_tee(
            main_pipes, target_pipe, branch_tie_pipe, tie_point_xyz,
            system_label, main_diameter_mm, pipe_type, target_pipe_id,
        )
        return ok, info

    if tee_first:
        ok_tee, tee_info = _attempt_tee()
        if ok_tee:
            return True
        write_log(
            "TEE FALLBACK -> takeoff | main={0} | branch={1} | reason={2}\n".format(
                target_pipe_id,
                element_id_value(branch_tie_pipe.Id),
                tee_info,
            )
        )
        ok_takeoff, takeoff_info = _attempt_takeoff()
        return bool(ok_takeoff)

    ok_takeoff, takeoff_info = _attempt_takeoff()
    if ok_takeoff:
        return True
    write_log(
        "TAKEOFF FALLBACK -> tee | main={0} | branch={1} | reason={2}\n".format(
            target_pipe_id,
            element_id_value(branch_tie_pipe.Id),
            takeoff_info,
        )
    )
    ok_tee, tee_info = _attempt_tee()
    return bool(ok_tee)


def _try_tee(main_pipes, target_pipe, branch_tie_pipe, tie_point_xyz, system_label, main_diameter_mm, pipe_type, target_pipe_id):
    """Conecta el ramal al main con BreakCurve + NewTeeFitting (rompe la curva del main).
    Devuelve (ok, info)."""
    if not tee_routing_preflight(pipe_type, main_diameter_mm):
        return False, "tee preflight failed"

    sub_tx = DB.SubTransaction(doc)
    sub_tx.Start()
    break_point_xyz = nudge_point_inside_pipe(target_pipe, tie_point_xyz)
    if break_point_xyz != tie_point_xyz:
        write_log(
            "IDEA 2 OK | nudged_point={0}\n".format(break_point_xyz)
        )
    else:
        write_log(
            "IDEA 2 OK | no_nudge\n"
        )
    try:
        doc.Regenerate()
    except Exception:
        pass

    try:
        break_result = DB.Plumbing.PlumbingUtils.BreakCurve(doc, target_pipe.Id, break_point_xyz)
    except Exception as ex:
        write_log(
            "TEE FAIL | reason=break curve failed | pipe={0} | error={1}\n".format(
                target_pipe_id,
                ex,
            )
        )
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "break curve failed: {0}".format(ex)

    new_main_id = break_result
    if not isinstance(new_main_id, DB.ElementId) or element_id_value(new_main_id) in (None, -1):
        write_log(
            "IDEA 3 FAIL | reason=invalid break result | break_id={0}\n".format(new_main_id)
        )
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "invalid break result"
    write_log(
        "IDEA 3 OK | break_id={0}\n".format(element_id_value(new_main_id))
    )

    try:
        new_main_element = doc.GetElement(new_main_id)
    except Exception:
        new_main_element = None

    new_main_value = element_id_value(new_main_id)
    try:
        doc.Regenerate()
    except Exception:
        pass

    main_pipe_a = doc.GetElement(target_pipe.Id)
    main_pipe_b = doc.GetElement(new_main_id)
    if main_pipe_a is None or main_pipe_b is None:
        write_log(
            "IDEA 4 FAIL | reason=split main pipe missing | pipe={0}\n".format(
                target_pipe_id,
            )
        )
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "split main pipe missing"

    main_conn_a = pick_open_connector(main_pipe_a, tie_point_xyz, system_label=system_label, require_system_match=True)
    main_conn_b = pick_open_connector(main_pipe_b, tie_point_xyz, system_label=system_label, require_system_match=True)
    branch_conn = pick_open_connector(branch_tie_pipe, tie_point_xyz, system_label=system_label, require_system_match=True)
    connectors_found = 0
    for conn in (main_conn_a, main_conn_b, branch_conn):
        if conn is not None:
            connectors_found += 1
    if connectors_found < 3:
        write_log(
            "IDEA 4 FAIL | reason=missing connectors | pipe={0}\n".format(new_main_value)
        )
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "missing connectors after break"
    write_log(
        "IDEA 4 OK | connectors_found={0}\n".format(connectors_found)
    )
    write_log(
        "TEE CONNECTORS DEBUG |\n  main_a={0}\n  main_b={1}\n  branch={2}\n".format(
            debug_connector_summary(main_conn_a),
            debug_connector_summary(main_conn_b),
            debug_connector_summary(branch_conn),
        )
    )
    try:
        main_a_dir = getattr(main_conn_a, "Direction", None)
    except Exception:
        main_a_dir = None
    try:
        main_b_dir = getattr(main_conn_b, "Direction", None)
    except Exception:
        main_b_dir = None
    try:
        branch_dir = getattr(branch_conn, "Direction", None)
    except Exception:
        branch_dir = None
    write_log(
        "TEE DIRECTIONS |\n  main_a={0}\n  main_b={1}\n  branch={2}\n".format(
            main_a_dir,
            main_b_dir,
            branch_dir,
        )
    )
    try:
        v_main_a = main_conn_a.CoordinateSystem.BasisZ
    except Exception:
        v_main_a = None
    try:
        v_main_b = main_conn_b.CoordinateSystem.BasisZ
    except Exception:
        v_main_b = None
    try:
        v_branch = branch_conn.CoordinateSystem.BasisZ
    except Exception:
        v_branch = None
    angle_ab = angle_deg(v_main_a, v_main_b) if v_main_a is not None and v_main_b is not None else None
    angle_a_br = angle_deg(v_main_a, v_branch) if v_main_a is not None and v_branch is not None else None
    angle_b_br = angle_deg(v_main_b, v_branch) if v_main_b is not None and v_branch is not None else None
    write_log(
        "TEE ANGLES | ab={0} | a_branch={1} | b_branch={2}\n".format(
            angle_ab,
            angle_a_br,
            angle_b_br,
        )
    )
    diam_main_a = get_pipe_diameter_mm(main_pipe_a)
    diam_main_b = get_pipe_diameter_mm(main_pipe_b)
    diam_branch = get_pipe_diameter_mm(branch_tie_pipe)
    write_log(
        "TEE SIZES | main_a={0} | main_b={1} | branch={2}\n".format(
            diam_main_a,
            diam_main_b,
            diam_branch,
        )
    )

    if main_conn_a is None or main_conn_b is None or branch_conn is None:
        write_log(
            "TEE FAIL | reason=missing connectors | pipe={0} | new={1}\n".format(
                target_pipe_id,
                new_main_value,
            )
        )
        try:
            sub_tx.RollBack()
        except Exception:
            pass
        return False, "missing connectors"

    tee_orders = (
        (main_conn_a, main_conn_b, branch_conn),
        (branch_conn, main_conn_a, main_conn_b),
        (branch_conn, main_conn_b, main_conn_a),
        (main_conn_b, branch_conn, main_conn_a),
        (main_conn_a, branch_conn, main_conn_b),
        (main_conn_b, main_conn_a, branch_conn),
    )
    last_error = None
    for conn_a, conn_b, conn_c in tee_orders:
        try:
            write_log(
                "TEE ORDER | main_in={0} | main_out={1} | branch={2}\n".format(
                    element_id_value(getattr(getattr(conn_a, "Owner", None), "Id", None)),
                    element_id_value(getattr(getattr(conn_b, "Owner", None), "Id", None)),
                    element_id_value(getattr(getattr(conn_c, "Owner", None), "Id", None)),
                )
            )
            write_log(
                "TEE CONNECTOR DETAIL |\n  conn_a={0}\n  conn_b={1}\n  conn_c={2}\n".format(
                    tee_connector_diagnostics(conn_a),
                    tee_connector_diagnostics(conn_b),
                    tee_connector_diagnostics(conn_c),
                )
            )
            tee = doc.Create.NewTeeFitting(conn_a, conn_b, conn_c)
            if tee is None:
                continue
            try:
                sub_tx.Commit()
            except Exception as commit_ex:
                write_log(
                    "TEE FAIL | reason=commit failed | main={0} | new={1} | branch={2} | error={3}\n".format(
                        target_pipe_id,
                        new_main_value,
                        element_id_value(branch_tie_pipe.Id),
                        commit_ex,
                    )
                )
                try:
                    sub_tx.RollBack()
                except Exception:
                    pass
                return False, "commit failed: {0}".format(commit_ex)
            if True:
                target_pipe_id_value = element_id_value(target_pipe.Id)
                main_pipes[:] = [
                    p for p in main_pipes
                    if element_id_value(p.Id) != target_pipe_id_value
                ]
                for fresh_id in (target_pipe.Id, new_main_id):
                    fresh_pipe = doc.GetElement(fresh_id)
                    if fresh_pipe is not None:
                        already_present = any(
                            element_id_value(existing.Id) == element_id_value(fresh_pipe.Id)
                            for existing in main_pipes
                        )
                        if not already_present:
                            main_pipes.append(fresh_pipe)
                write_log(
                    "MAIN UPDATE | old={0} | new={1} | count={2}\n".format(
                        target_pipe_id,
                        new_main_value,
                        len(main_pipes),
                    )
                )
                write_log(
                    "IDEA 5 OK | tee_id={0}\n".format(
                        element_id_value(tee.Id),
                    )
                )
            write_log(
                "TEE OK | main={0} | new={1} | branch={2} | point={3}\n".format(
                    target_pipe_id,
                    new_main_value,
                    element_id_value(branch_tie_pipe.Id),
                    tie_point_xyz,
                )
            )
            return True, element_id_value(getattr(tee, "Id", None))
        except Exception as ex:
            last_error = ex
            write_log(
                "TEE TRY FAIL | order={0},{1},{2} | error={3}\n".format(
                    debug_connector_summary(conn_a),
                    debug_connector_summary(conn_b),
                    debug_connector_summary(conn_c),
                    ex,
                )
            )
    write_log(
        "IDEA 5 FAIL | reason=tee creation failed | pipe={0}\n".format(new_main_value)
    )
    try:
        sub_tx.RollBack()
    except Exception:
        pass
    return False, "tee creation failed: {0}".format(last_error)


def log_segment_elevation(scope, label, segment, level_id, extra=""):
    write_log(
        "ELEVATION | scope={0} | label={1} | kind={2} | start_z_mm={3} | end_z_mm={4} | level={5} {6}\n".format(
            scope,
            label,
            segment.kind,
            segment.start[2],
            segment.end[2],
            element_id_value(level_id),
            extra,
        )
    )


def create_pipes_from_plan(plan, valid_items, snapshots):
    pipe_type = get_pipe_type(doc, plan.system_label, snapshots)
    if pipe_type is None:
        raise ValueError("No se encontro un PipeType disponible en el proyecto.")

    system_type_id = get_piping_system_type_id(doc, plan.system_label, snapshots)
    if system_type_id is None:
        raise ValueError("No se encontro un PipingSystemType compatible con el sistema elegido.")

    created = []
    failed = []
    created_ids = []
    fittings_created = 0
    main_pipe_objects = []
    elem_map = {}
    snapshot_map = {}
    for elem, _connectors in valid_items:
        try:
            elem_map[element_id_value(elem.Id)] = elem
        except Exception:
            continue
    for snapshot in snapshots:
        try:
            snapshot_map[element_id_value(getattr(snapshot, "element_id", None))] = snapshot
        except Exception:
            continue

    t = DB.Transaction(doc, "EstimBot - Generate Layout")
    t.Start()
    try:
        for segment in plan.main_segments:
            try:
                start_xyz = mm_point_to_xyz(segment.start)
                level_id = resolve_level_id_for_element(valid_items[0][0], start_xyz.Z)
                pipe, skip_reason = create_pipe_segment(doc, system_type_id, pipe_type.Id, level_id, segment)
                if pipe is None:
                    failed.append("main: {0}".format(skip_reason))
                    write_log(
                        "MAIN SKIP | system={0} | segment={1} | reason={2}\n".format(
                            plan.system_label,
                            segment.kind,
                            skip_reason,
                        )
                    )
                    continue
                if set_pipe_diameter(pipe, plan.main_diameter_mm):
                    write_log(
                        "DIAMETER OK | scope=main | diameter_mm={0} | pipe_id={1}\n".format(
                            plan.main_diameter_mm,
                            element_id_value(pipe.Id),
                        )
                    )
                else:
                    write_log(
                        "DIAMETER FAIL | scope=main | diameter_mm={0} | pipe_id={1}\n".format(
                            plan.main_diameter_mm,
                            element_id_value(pipe.Id),
                        )
                )
                created.append(pipe)
                created_ids.append(pipe.Id)
                main_pipe_objects.append(pipe)
                log_pipe_state("MAIN_BEFORE_BRANCHES", pipe)
                write_log(
                    "MAIN SYSTEM |\n  pipe_id={0}\n  mep_system={1}\n  pipe_type={2}\n".format(
                        element_id_value(pipe.Id),
                        safe_name(getattr(pipe, "MEPSystem", None)),
                        element_id_value(getattr(getattr(pipe, "PipeType", None), "Id", None)),
                    )
                )
                log_segment_elevation("main", plan.system_label, segment, level_id, extra="main_z_mm={0}".format(segment.start[2]))
                write_log(
                    "MAIN OK | system={0} | level={1} | start={2} | end={3} | pipe_id={4}\n".format(
                        plan.system_label,
                        element_id_value(level_id),
                        segment.start,
                        segment.end,
                        element_id_value(pipe.Id),
                    )
                )
            except Exception as ex:
                failed.append("main: {0}".format(ex))
                write_log(
                    "MAIN FAIL | system={0} | segment={1} | error={2}\n".format(
                        plan.system_label,
                        segment.kind,
                        ex,
                    )
                )

        for branch in plan.branches:
            elem = elem_map.get(branch.element_id)
            if elem is None:
                failed.append("branch {0}: elemento no encontrado".format(branch.element_id))
                continue

            try:
                level_id = resolve_level_id_for_element(elem, mm_to_ft(branch.segments[0].start[2]))
                branch_snapshot = snapshot_map.get(branch.element_id)
                branch_diameter_mm = plan.main_diameter_mm
                if branch_snapshot is not None:
                    branch_diameter_mm = calculate_pipe_diameter_mm(
                        plan.system_label,
                        float(getattr(branch_snapshot, "fixture_units", 0.0) or 0.0),
                        float(getattr(branch_snapshot, "flow", 0.0) or 0.0),
                    )
                branch_pipes = []
                for segment in branch.segments:
                    pipe, skip_reason = create_pipe_segment(doc, system_type_id, pipe_type.Id, level_id, segment)
                    if pipe is None:
                        failed.append("branch {0}: {1}".format(branch.element_id, skip_reason))
                        write_log(
                            "BRANCH SKIP | element={0} | kind={1} | reason={2}\n".format(
                                branch.element_id,
                                segment.kind,
                                skip_reason,
                            )
                        )
                        continue
                    segment_diameter_mm = branch_diameter_mm
                    if clean(segment.kind).startswith("tie-in-"):
                        segment_diameter_mm = plan.main_diameter_mm
                    if set_pipe_diameter(pipe, segment_diameter_mm):
                        write_log(
                            "DIAMETER OK | scope=branch | element={0} | diameter_mm={1} | pipe_id={2}\n".format(
                                branch.element_id,
                                segment_diameter_mm,
                                element_id_value(pipe.Id),
                            )
                        )
                    else:
                        write_log(
                            "DIAMETER FAIL | scope=branch | element={0} | diameter_mm={1} | pipe_id={2}\n".format(
                                branch.element_id,
                                segment_diameter_mm,
                                element_id_value(pipe.Id),
                            )
                        )
                    created.append(pipe)
                    created_ids.append(pipe.Id)
                    branch_pipes.append((segment, pipe))
                    log_segment_elevation(
                        "branch",
                        branch.element_id,
                        segment,
                        level_id,
                        extra="main_z_mm={0}".format(plan.main_segments[0].start[2]),
                    )
                    write_log(
                        "BRANCH OK | element={0} | level={1} | kind={2} | start={3} | end={4} | pipe_id={5}\n".format(
                            branch.element_id,
                            element_id_value(level_id),
                            segment.kind,
                            segment.start,
                            segment.end,
                            element_id_value(pipe.Id),
                        )
                    )
                for index in range(len(branch_pipes) - 1):
                    left_segment, left_pipe = branch_pipes[index]
                    right_segment, right_pipe = branch_pipes[index + 1]
                    shared_point = mm_point_to_xyz(left_segment.end)
                    if connect_two_pipes_with_elbow(
                        left_pipe,
                        right_pipe,
                        shared_point,
                        "branch",
                        "{0}->{1} | element={2}".format(left_segment.kind, right_segment.kind, branch.element_id),
                        system_label=plan.system_label,
                    ):
                        fittings_created += 1
                    else:
                        failed.append("branch {0} fitting {1}->{2}".format(branch.element_id, left_segment.kind, right_segment.kind))

                if branch_pipes:
                    tie_segment, tie_pipe = branch_pipes[-1]
                    tie_point = mm_point_to_xyz(tie_segment.end)
                    write_log(
                        "ELEVATION REVIEW | element={0} | main_z_mm={1} | tie_z_mm={2} | branch_start_z_mm={3}\n".format(
                            branch.element_id,
                            plan.main_segments[0].start[2],
                            tie_segment.end[2],
                            branch.segments[0].start[2],
                        )
                    )
                    if ENABLE_TEE_ROUTE:
                        if not connect_branch_to_main(main_pipe_objects, tie_pipe, tie_point, plan.system_label, plan.main_diameter_mm, pipe_type):
                            failed.append("branch {0} tee".format(branch.element_id))
                        else:
                            fittings_created += 1
                            try:
                                doc.Regenerate()
                            except Exception:
                                pass
                            if main_pipe_objects:
                                log_pipe_state("MAIN_AFTER_TEE", main_pipe_objects[-1])
                    else:
                        write_log(
                            "TEE SKIP | reason=disabled stable-route mode | branch={0} | point={1}\n".format(
                                branch.element_id,
                                tie_point,
                            )
                        )
            except Exception as ex:
                failed.append("branch {0}: {1}".format(branch.element_id, ex))
                write_log(
                    "BRANCH FAIL | element={0} | error={1}\n".format(
                        branch.element_id,
                        ex,
                    )
                )

        try:
            doc.Regenerate()
        except Exception:
            pass
        if main_pipe_objects:
            log_pipe_state("MAIN_FINAL", main_pipe_objects[-1])

        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise

    try:
        if created_ids:
            try:
                uidoc.Selection.SetElementIds(created_ids)
            except Exception:
                pass
            uidoc.ShowElements(created_ids)
    except Exception:
        pass

    write_log(
        "CREATE SUMMARY | system={0} | created={1} | fittings={2} | failed={3} | ids={4}\n".format(
            plan.system_label,
            len(created),
            fittings_created,
            len(failed),
            [element_id_value(pid) for pid in created_ids],
        )
    )

    return created, fittings_created, failed, created_ids


def main():
    if doc is None or uidoc is None:
        alert("No hay documento activo en Revit.", title="Generate Layout")
        return

    elements = get_selected_elements()
    if not elements:
        alert("Selecciona familias antes de correr el boton.", title="Generate Layout")
        return

    valid_items, skipped_items = collect_valid_families(elements)
    if not valid_items:
        output.print_md("## Generate Layout")
        output.print_md("- No hubo familias validas.")
        for elem, reason in skipped_items:
            output.print_md("- `{0}`: {1}".format(safe_name(elem) or "Elemento", reason))
        alert("No hay familias validas con conectores fisicos.", title="Generate Layout")
        return

    system_options = infer_system_options(valid_items)
    system_label = choose_system(system_options)
    if not system_label:
        alert("No se selecciono sistema.", title="Generate Layout")
        return

    filtered_items, filtered_skipped = filter_valid_items_for_system(valid_items, system_label)
    write_log(
        "SYSTEM FILTER OK | system={0} | valid={1} | filtered={2} | skipped={3}\n".format(
            system_label,
            len(valid_items),
            len(filtered_items),
            len(filtered_skipped),
        )
    )
    if not filtered_items:
        output.print_md("## Generate Layout")
        output.print_md("- No hubo conectores compatibles con el sistema seleccionado.")
        for elem, reason in filtered_skipped:
            output.print_md("- `{0}`: {1}".format(safe_name(elem) or "Elemento", reason))
        alert(
            "No hay conectores compatibles con el sistema seleccionado.",
            title="Generate Layout",
        )
        return

    mode = choose_execution_mode()
    if not mode:
        alert("No se selecciono modo de ejecucion.", title="Generate Layout")
        return

    connector_snapshots = collect_connector_snapshots(filtered_items)
    wall_segments = collect_wall_segments()
    write_log(
        "WALLS OK | count={0}\n".format(len(wall_segments))
    )
    try:
        plan = build_layout_plan(
            connector_snapshots,
            system_label,
            LayoutSettings(offset_mm=-150.0, sanitary_slope=0.02),
            wall_segments=wall_segments,
        )
    except Exception as ex:
        tb = traceback.format_exc()
        write_log("FAIL build_layout_plan | system={0} | valid={1} | snapshots={2}\n{3}\n".format(
            system_label,
            len(valid_items),
            len(connector_snapshots),
            tb,
        ))
        output.print_md(build_summary(valid_items, skipped_items, system_label))
        output.print_md("## Error al construir plan")
        output.print_md("```text")
        output.print_md(tb)
        output.print_md("```")
        output.print_md("- error: `{0}`".format(ex))
        alert(
            "No se pudo construir el plan preliminar.\nRevisa {0}".format(LOG_FILE),
            title="Generate Layout",
        )
        return

    output.print_md(build_summary(filtered_items, skipped_items + filtered_skipped, system_label))
    output.print_md(build_plan_summary(plan))

    if mode == "vista previa segura":
        write_log("PREVIEW OK | system={0} | valid={1} | snapshots={2} | main={3} | branches={4}\n".format(
            system_label,
            len(valid_items),
            len(connector_snapshots),
            len(plan.main_segments),
            len(plan.branches),
        ))
        alert(
            "Preview listo.\nSistema: {0}\nValidos: {1}\nOmitidos: {2}".format(
                system_label,
                len(valid_items),
                len(skipped_items),
            ),
            title="Generate Layout",
        )
        return

    if not alert(
        "Esto va a escribir tuberias reales en el modelo.\nContinuar?",
        title="Generate Layout",
        ok=True,
        cancel=True,
    ):
        return

    try:
        created, fittings, failed, created_ids = create_pipes_from_plan(plan, filtered_items, connector_snapshots)
    except Exception as ex:
        tb = traceback.format_exc()
        write_log("FAIL create_pipes_from_plan | system={0}\n{1}\n".format(system_label, tb))
        output.print_md("## Error en creacion real")
        output.print_md("```text")
        output.print_md(tb)
        output.print_md("```")
        output.print_md("- error: `{0}`".format(ex))
        alert(
            "La creacion real fallo.\nRevisa {0}".format(LOG_FILE),
            title="Generate Layout",
        )
        return

    output.print_md("## Creacion real")
    output.print_md("- Pipes creadas: `{0}`".format(len(created)))
    output.print_md("- Fallos: `{0}`".format(len(failed)))
    output.print_md("- IDs creados: `{0}`".format(len(created_ids)))
    output.print_md("- Fittings (codos+tees+takeoffs): `{0}`".format(fittings))
    if failed:
        output.print_md("### Fallos")
        for item in failed:
            output.print_md("- {0}".format(item))

    alert(
        "Creacion real terminada.\nPipes: {0}\nFittings: {1}\nFallos: {2}".format(
            len(created),
            fittings,
            len(failed),
        ),
        title="Generate Layout",
    )


if __name__ == "__main__":
    main()
