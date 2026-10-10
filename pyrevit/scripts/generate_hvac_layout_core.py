# -*- coding: utf-8 -*-
"""
Pure layout-planning core for EstimBot HVAC ductwork.

Mirrors generate_layout_core.py's architecture (piping) but for ducts:
- system classification: SupplyAir / ReturnAir / ExhaustAir (confirmed
live via connector.DuctSystemType against a real hospital HVAC model,
2026-08-28).
- duct sizing: connector.Flow returns CFM directly. Real project data
showed ROUND ducts at 6/10/12 inch nominal (imperial, SMACNA round
series) -- this core sizes against the full SMACNA round nominal
series (4-30 inch) using a velocity-based CFM->diameter approximation.
- duct TYPE selection: Revit duct TYPES are named by fitting style
(e.g. "Taps") under a FAMILY name of "Round Duct"/"Rectangular Duct"/
"Oval Duct". Duct type selection matches connector.Shape against the
duct type FAMILY name, not keywords inside the type name.

Compatible with both IronPython 2.7 and CPython (no Revit API imports).
"""

from math import fabs, sqrt, pi


MM_PER_FOOT = 304.8
MM_PER_INCH = 25.4
CFM_PER_M3S = 2118.88

STANDARD_ROUND_SIZES_IN = [4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
STANDARD_ROUND_SIZES_MM = [round(v * MM_PER_INCH, 1) for v in STANDARD_ROUND_SIZES_IN]

TARGET_VELOCITY_FPM = {
    "SupplyAir": 800.0,
    "ReturnAir": 700.0,
    "ExhaustAir": 600.0,
}
DEFAULT_TARGET_VELOCITY_FPM = 700.0

DEFAULT_CEILING_OFFSET_MM = -150.0
MIN_BRANCH_RUN_MM = 150.0


class DuctConnectorSnapshot(object):
    def __init__(self, element_id, family_name, category_name, system_kind,
                 is_connected, x, y, z, flow_cfm, shape):
        self.element_id = element_id
        self.family_name = family_name
        self.category_name = category_name
        self.system_kind = system_kind
        self.is_connected = is_connected
        self.x = x
        self.y = y
        self.z = z
        self.flow_cfm = flow_cfm
        self.shape = shape


class RoomHeightContext(object):
    """Per-room/per-level ceiling height context from a live architecture
    metadata dump. Used to place duct runs at the correct real height
    instead of a single hardcoded fallback."""
    def __init__(self, level_name, level_elevation_mm, ceiling_height_above_level_mm):
        self.level_name = level_name
        self.level_elevation_mm = level_elevation_mm
        self.ceiling_height_above_level_mm = ceiling_height_above_level_mm

    @property
    def ceiling_z_mm(self):
        return self.level_elevation_mm + self.ceiling_height_above_level_mm

    @property
    def duct_centerline_z_mm(self):
        return self.ceiling_z_mm + DEFAULT_CEILING_OFFSET_MM


class DuctSegmentPlan(object):
    def __init__(self, start, end, kind):
        self.start = start
        self.end = end
        self.kind = kind

    @property
    def length_mm(self):
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        dz = self.end[2] - self.start[2]
        return sqrt(dx * dx + dy * dy + dz * dz)


class DuctBranchPlan(object):
    def __init__(self, element_id, segments):
        self.element_id = element_id
        self.segments = tuple(segments)

    @property
    def length_mm(self):
        return sum(segment.length_mm for segment in self.segments)


class DuctLayoutPlan(object):
    def __init__(self, system_label, main_segments, branches, main_diameter_mm, shape):
        self.system_label = system_label
        self.main_segments = tuple(main_segments)
        self.branches = tuple(branches)
        self.main_diameter_mm = main_diameter_mm
        self.shape = shape

    @property
    def total_main_length_mm(self):
        return sum(segment.length_mm for segment in self.main_segments)

    @property
    def total_branch_length_mm(self):
        return sum(branch.length_mm for branch in self.branches)


def mm_to_ft(value_mm):
    return float(value_mm) / MM_PER_FOOT


def ft_to_mm(value_ft):
    return float(value_ft) * MM_PER_FOOT


def cfm_to_m3s(cfm):
    return float(cfm) / CFM_PER_M3S


def _clean(value):
    if value is None:
        return ""
    return str(value).strip().lower()


DUCT_SYSTEM_LABELS = ("SupplyAir", "ReturnAir", "ExhaustAir")


def normalize_duct_system_label(system_label):
    """Normalize a raw connector.DuctSystemType (or free text like
    'DUCT - SUPPLY AIR' seen in some legacy-imported models) to the
    canonical SupplyAir/ReturnAir/ExhaustAir label."""
    label = _clean(system_label).replace("-", " ").replace("_", " ")
    compact = "".join(label.split())
    if "supply" in label or compact == "supplyair":
        return "SupplyAir"
    if "return" in label or compact == "returnair":
        return "ReturnAir"
    if "exhaust" in label or compact == "exhaustair":
        return "ExhaustAir"
    return system_label


def infer_duct_system_labels(connectors):
    labels = set()
    for connector in connectors:
        normalized = normalize_duct_system_label(connector.system_kind)
        if normalized in DUCT_SYSTEM_LABELS:
            labels.add(normalized)
    ordered = []
    for label in DUCT_SYSTEM_LABELS:
        if label in labels:
            ordered.append(label)
    return ordered


def select_duct_type_name(shape, duct_type_families):
    """Pick a duct TYPE by matching connector.Shape ('Round'/'Rectangular'/
    'Oval') against the loaded DuctType FAMILY name ('Round Duct' /
    'Rectangular Duct' / 'Oval Duct'). Does NOT search for system-
    classification keywords inside the type name -- real duct type names
    are fitting-style names ('Taps', 'Mitered Elbows / Taps'), not system
    labels; that distinction lives on the connector/system, not the duct
    type.

    duct_type_families: list of (family_name, type_name) tuples for all
    loaded DuctType elements in the document.
    """
    shape_clean = _clean(shape)
    shape_to_family_keyword = {
        "round": "round duct",
        "rectangular": "rectangular duct",
        "oval": "oval duct",
    }
    keyword = shape_to_family_keyword.get(shape_clean)
    if keyword is None:
        if duct_type_families:
            return duct_type_families[0]
        return None

    matches = [pair for pair in duct_type_families if keyword in _clean(pair[0])]
    if matches:
        return matches[0]
    if duct_type_families:
        return duct_type_families[0]
    return None


def _next_standard_round_size_mm(value_mm):
    for size in STANDARD_ROUND_SIZES_MM:
        if value_mm <= size:
            return size
    return STANDARD_ROUND_SIZES_MM[-1]


def calculate_round_duct_diameter_mm(system_label, total_flow_cfm):
    """Size a round duct by target face velocity: Q = V * A -> A = Q / V
    -> diameter from area (all imperial, consistent units).

    total_flow_cfm: sum of connector.Flow (CFM) for everything on this
    branch/trunk.
    """
    normalized = normalize_duct_system_label(system_label)
    velocity_fpm = TARGET_VELOCITY_FPM.get(normalized, DEFAULT_TARGET_VELOCITY_FPM)
    if total_flow_cfm <= 0 or velocity_fpm <= 0:
        return STANDARD_ROUND_SIZES_MM[0]

    area_sqft = float(total_flow_cfm) / velocity_fpm
    diameter_ft = 2.0 * sqrt(area_sqft / pi)
    diameter_in = diameter_ft * 12.0
    diameter_mm = diameter_in * MM_PER_INCH
    return _next_standard_round_size_mm(diameter_mm)


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return min(xs), min(ys), max(xs), max(ys), sum(zs) / float(len(zs))


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _choose_main_anchor(valid_points, bbox):
    min_x, min_y, max_x, max_y, _avg_z = bbox
    width = fabs(max_x - min_x)
    height = fabs(max_y - min_y)
    horizontal = width >= height
    center_x = _median([p[0] for p in valid_points])
    center_y = _median([p[1] for p in valid_points])
    anchor = center_y if horizontal else center_x
    return horizontal, anchor


def build_duct_layout_plan(connectors, system_label, ceiling_z_mm, duct_type_families=None):
    """Build a main-trunk + branch layout plan for duct terminal/equipment
    connectors sharing one system (Supply/Return/Exhaust). ceiling_z_mm is
    the absolute Z (project coords, mm) of the duct run plane -- pass
    RoomHeightContext.duct_centerline_z_mm for a real per-room height
    instead of a single hardcoded fallback.
    """
    valid = [c for c in connectors if not c.is_connected]
    if not valid:
        raise ValueError("No hay conectores validos para construir el layout de ductos.")

    points = [(c.x, c.y, c.z) for c in valid]
    min_x, min_y, max_x, max_y, _avg_z = _bbox(points)
    horizontal_main, anchor = _choose_main_anchor(points, (min_x, min_y, max_x, max_y, _avg_z))

    main_start_coord = min_x if horizontal_main else min_y
    main_end_coord = max_x if horizontal_main else max_y

    if horizontal_main:
        main_segments = (
            DuctSegmentPlan((main_start_coord, anchor, ceiling_z_mm), (main_end_coord, anchor, ceiling_z_mm), "main-ceiling-horizontal"),
        )
    else:
        main_segments = (
            DuctSegmentPlan((anchor, main_start_coord, ceiling_z_mm), (anchor, main_end_coord, ceiling_z_mm), "main-ceiling-vertical"),
        )

    branches = []
    total_flow = 0.0
    shape_votes = {}
    for connector in valid:
        total_flow += float(connector.flow_cfm or 0.0)
        shape_votes[connector.shape] = shape_votes.get(connector.shape, 0) + 1

        if horizontal_main:
            projected = (connector.x, anchor, ceiling_z_mm)
        else:
            projected = (anchor, connector.y, ceiling_z_mm)

        segments = (
            DuctSegmentPlan((connector.x, connector.y, connector.z), (connector.x, connector.y, ceiling_z_mm), "drop-to-ceiling"),
            DuctSegmentPlan((connector.x, connector.y, ceiling_z_mm), projected, "ceiling-run"),
        )
        branches.append(DuctBranchPlan(connector.element_id, segments))

    dominant_shape = max(shape_votes.items(), key=lambda kv: kv[1])[0] if shape_votes else "Round"
    main_diameter = calculate_round_duct_diameter_mm(system_label, total_flow)

    return DuctLayoutPlan(system_label, main_segments, branches, main_diameter, dominant_shape)


def build_hvac_preview_report(plan):
    lines = []
    lines.append("## Preview HVAC")
    lines.append("- Sistema: `{0}`".format(plan.system_label))
    lines.append("- Forma dominante: `{0}`".format(plan.shape))
    lines.append("- Diametro main: `{0:.0f} mm`".format(plan.main_diameter_mm))
    lines.append("- Longitud main: `{0:.2f} mm`".format(plan.total_main_length_mm))
    lines.append("- Longitud branches: `{0:.2f} mm`".format(plan.total_branch_length_mm))
    lines.append("- Branches: `{0}`".format(len(plan.branches)))
    return "\n".join(lines)
