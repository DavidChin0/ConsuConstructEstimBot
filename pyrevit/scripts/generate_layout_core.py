# -*- coding: utf-8 -*-
"""
Pure layout-planning core for EstimBot.

Compatible with both IronPython 2.7 and CPython.
"""

from math import fabs, sqrt


STANDARD_PIPE_SIZES_MM = [15, 20, 25, 32, 40, 50, 65, 80, 100, 125, 150, 200, 250, 300]
MM_PER_FOOT = 304.8
MIN_BRANCH_RUN_MM = 150.0


class ConnectorSnapshot(object):
    def __init__(self, element_id, family_name, category_name, system_kind, is_connected, x, y, z, flow, fixture_units):
        self.element_id = element_id
        self.family_name = family_name
        self.category_name = category_name
        self.system_kind = system_kind
        self.is_connected = is_connected
        self.x = x
        self.y = y
        self.z = z
        self.flow = flow
        self.fixture_units = fixture_units


class LayoutSettings(object):
    def __init__(self, offset_mm=-150.0, sanitary_slope=0.02):
        self.offset_mm = offset_mm
        self.sanitary_slope = sanitary_slope


class SegmentPlan(object):
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


class BranchPlan(object):
    def __init__(self, element_id, segments):
        self.element_id = element_id
        self.segments = tuple(segments)

    @property
    def length_mm(self):
        return sum(segment.length_mm for segment in self.segments)


class LayoutPlan(object):
    def __init__(self, system_label, main_segments, branches, main_diameter_mm):
        self.system_label = system_label
        self.main_segments = tuple(main_segments)
        self.branches = tuple(branches)
        self.main_diameter_mm = main_diameter_mm

    @property
    def total_main_length_mm(self):
        return sum(segment.length_mm for segment in self.main_segments)

    @property
    def total_branch_length_mm(self):
        return sum(branch.length_mm for branch in self.branches)


def build_preview_report(plan):
    lines = []
    lines.append("## Preview")
    lines.append("- Sistema: `{0}`".format(plan.system_label))
    lines.append("- Diametro main: `{0} mm`".format(plan.main_diameter_mm))
    lines.append("- Longitud main: `{0:.2f} mm`".format(plan.total_main_length_mm))
    lines.append("- Longitud branches: `{0:.2f} mm`".format(plan.total_branch_length_mm))
    lines.append("- Branches: `{0}`".format(len(plan.branches)))
    lines.append("### Main segments")
    for index, segment in enumerate(plan.main_segments, 1):
        lines.append(
            "- {0}. `{1}` desde `{2}` hasta `{3}`".format(
                index,
                segment.kind,
                segment.start,
                segment.end,
            )
        )
    lines.append("### Branches")
    for branch in plan.branches:
        lines.append("- Elemento `{0}`".format(branch.element_id))
        for segment in branch.segments:
            lines.append("  - `{0}` desde `{1}` hasta `{2}`".format(segment.kind, segment.start, segment.end))
    return "\n".join(lines)


def mm_to_ft(value_mm):
    return float(value_mm) / MM_PER_FOOT


def ft_to_mm(value_ft):
    return float(value_ft) * MM_PER_FOOT


def _clean(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _normalize_system_label(system_label):
    label = _clean(system_label)
    if _is_cold_water_label(label):
        return "Domestic Cold Water"
    if _is_hot_water_label(label):
        return "Domestic Hot Water"
    if _is_sanitary_label(label):
        return "Sanitary"
    if _is_vent_label(label):
        return "Vent"
    return system_label


def _is_cold_water_label(label):
    label = _clean(label)
    return label in ("domestic cold water", "dcw", "potable", "cold water")


def _is_hot_water_label(label):
    label = _clean(label)
    return label in ("domestic hot water", "dhw", "hot water")


def _is_sanitary_label(label):
    label = _clean(label)
    return label in ("sanitary", "drenaje", "drain", "drainage", "dw", "waste", "sewer", "soil")


def _is_vent_label(label):
    return _clean(label) == "vent"


def _pipe_type_rules(system_label, classification_name):
    label = _clean(system_label)
    classification = _clean(classification_name)

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
    if _is_cold_water_label(label):
        return _pipe_type_rules(system_label, "DomesticColdWater")
    if _is_hot_water_label(label):
        return _pipe_type_rules(system_label, "DomesticHotWater")
    if _is_sanitary_label(label):
        return _pipe_type_rules(system_label, "Sanitary")
    if _is_vent_label(label):
        return _pipe_type_rules(system_label, "Vent")
    return {
        "preferred": [label, "default", "pvc", "cpvc", "copper"],
        "forbidden": ["chilled", "hydronic"],
    }


def _next_standard_size(value_mm):
    for size in STANDARD_PIPE_SIZES_MM:
        if value_mm <= size:
            return size
    return STANDARD_PIPE_SIZES_MM[-1]


def calculate_pipe_diameter_mm(system_label, fixture_units, flow):
    d_fu = _lookup_diameter_from_fixture_units(system_label, fixture_units)
    d_flow = _lookup_diameter_from_flow(system_label, flow)
    return _next_standard_size(max(d_fu, d_flow))


def select_pipe_type_name(system_label, pipe_type_names, classification_name=None):
    rules = _pipe_type_rules(system_label, classification_name)
    preferred = rules["preferred"]
    forbidden = rules["forbidden"]

    allowed_names = []
    rejected_names = []
    for raw_name in pipe_type_names or []:
        name = _clean(raw_name)
        if any(token and token in name for token in forbidden):
            rejected_names.append(raw_name)
            continue
        allowed_names.append(raw_name)

    best_name = None
    best_score = -1
    for raw_name in allowed_names:
        name = _clean(raw_name)
        score = 0
        for index, keyword in enumerate(preferred):
            if keyword and keyword in name:
                score = max(score, len(preferred) - index)
        if score > best_score:
            best_score = score
            best_name = raw_name

    if best_score > 0:
        return best_name

    if allowed_names:
        allowed_names.sort(key=lambda item: _clean(item))
        return allowed_names[0]

    if rejected_names:
        rejected_names.sort(key=lambda item: _clean(item))
        return rejected_names[0]

    return None


def _lookup_diameter_from_fixture_units(system_label, total_fu):
    label = _clean(system_label)
    if _is_sanitary_label(label):
        table = [
            (1.0, 40),
            (2.0, 50),
            (4.0, 65),
            (8.0, 80),
            (15.0, 100),
            (30.0, 125),
            (60.0, 150),
        ]
    else:
        table = [
            (1.0, 15),
            (2.0, 20),
            (4.0, 25),
            (8.0, 32),
            (15.0, 40),
            (30.0, 50),
            (60.0, 65),
            (120.0, 80),
        ]

    for limit, size in table:
        if total_fu <= limit:
            return size
    return table[-1][1]


def _lookup_diameter_from_flow(system_label, total_flow):
    label = _clean(system_label)
    if _is_sanitary_label(label):
        table = [
            (0.10, 40),
            (0.25, 50),
            (0.50, 65),
            (1.00, 80),
            (2.00, 100),
            (4.00, 125),
            (8.00, 150),
        ]
    else:
        table = [
            (0.10, 15),
            (0.25, 20),
            (0.50, 25),
            (1.00, 32),
            (2.00, 40),
            (4.00, 50),
            (8.00, 65),
            (16.00, 80),
        ]

    for limit, size in table:
        if total_flow <= limit:
            return size
    return table[-1][1]


def infer_system_labels(connectors):
    labels = set()
    for connector in connectors:
        kind = _clean(connector.system_kind)
        category = _clean(connector.category_name)
        family = _clean(connector.family_name)

        if "dhw" in kind or "domestic hot water" in kind or "hot water" in kind:
            labels.add("Domestic Hot Water")
        if "dcw" in kind or "domestic cold water" in kind or "cold water" in kind:
            labels.add("Domestic Cold Water")
        if "sanitary" in kind or "drain" in kind or "dw" in kind or "waste" in kind or "sewer" in kind:
            labels.add("Sanitary")
        if "vent" in kind or "vent" in category or "vent" in family:
            labels.add("Vent")

    ordered = []
    for label in ("Domestic Cold Water", "Domestic Hot Water", "Sanitary", "Vent"):
        if label in labels:
            ordered.append(label)
    return ordered


def resolve_piping_system_classification(system_label, connectors):
    label = _clean(system_label)
    if _is_sanitary_label(label):
        return "Sanitary"
    if _is_vent_label(label):
        return "Vent"
    if _is_hot_water_label(label):
        return "DomesticHotWater"
    if _is_cold_water_label(label):
        return "DomesticColdWater"

    for connector in connectors:
        kind = _clean(connector.system_kind)
        if "dhw" in kind or "hot water" in kind or "domestic hot water" in kind:
            return "DomesticHotWater"
        if "dcw" in kind or "cold water" in kind or "domestic cold water" in kind:
            return "DomesticColdWater"

    return "DomesticColdWater"


def _pipe_endpoints(pipe):
    curve = pipe.Location.Curve
    return curve.GetEndPoint(0), curve.GetEndPoint(1)


def _point_to_segment_distance(point_xyz, start, end):
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
        return sqrt(dx * dx + dy * dy + dz * dz)

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
    return sqrt(dx * dx + dy * dy + dz * dz)


def _point_on_segment(point_xyz, start, end, tolerance_ft=0.01):
    return _point_to_segment_distance(point_xyz, start, end) <= tolerance_ft


def find_unique_pipe_for_point(pipes, point_xyz, tolerance_ft=0.01):
    candidates = []
    for pipe in pipes or []:
        if pipe is None:
            continue
        try:
            start, end = _pipe_endpoints(pipe)
        except Exception:
            continue
        if not _point_on_segment(point_xyz, start, end, tolerance_ft=tolerance_ft):
            continue
        candidates.append(( _point_to_segment_distance(point_xyz, start, end), pipe))

    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        raise ValueError("ambiguous main segment")
    return None


def _bbox(connectors):
    xs = [connector.x for connector in connectors]
    ys = [connector.y for connector in connectors]
    zs = [connector.z for connector in connectors]
    return min(xs), min(ys), max(xs), max(ys), sum(zs) / float(len(zs))


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _project_to_perimeter(x, y, bbox, wall_segments=None):
    if wall_segments:
        nearest = None
        nearest_distance = None
        for wall in wall_segments:
            if not wall:
                continue
            try:
                x1, y1, x2, y2 = wall
            except Exception:
                continue
            dx = x2 - x1
            dy = y2 - y1
            length_sq = dx * dx + dy * dy
            if length_sq <= 0.0:
                continue
            t = ((x - x1) * dx + (y - y1) * dy) / length_sq
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            px = x1 + t * dx
            py = y1 + t * dy
            dist_sq = (px - x) * (px - x) + (py - y) * (py - y)
            if nearest_distance is None or dist_sq < nearest_distance:
                nearest_distance = dist_sq
                nearest = (px, py, x1, y1, x2, y2)
        if nearest is not None:
            px, py, x1, y1, x2, y2 = nearest
            if fabs(x2 - x1) >= fabs(y2 - y1):
                side = "north" if py >= y else "south"
            else:
                side = "east" if px >= x else "west"
            return px, py, side

    min_x, min_y, max_x, max_y = bbox
    candidates = {
        "west": ((min_x, y), fabs(x - min_x)),
        "east": ((max_x, y), fabs(max_x - x)),
        "south": ((x, min_y), fabs(y - min_y)),
        "north": ((x, max_y), fabs(max_y - y)),
    }
    side, value = min(candidates.items(), key=lambda item: item[1][1])
    point = value[0]
    return point[0], point[1], side


def _interpolate_z(start_coord, end_coord, start_z, end_z, coord):
    span = end_coord - start_coord
    if fabs(span) <= 0.001:
        return start_z
    ratio = (coord - start_coord) / span
    return start_z + ((end_z - start_z) * ratio)


def _choose_main_anchor(valid, bbox, wall_segments=None):
    min_x, min_y, max_x, max_y, _average_z = bbox
    width = fabs(max_x - min_x)
    height = fabs(max_y - min_y)
    horizontal = width >= height
    center_x = _median([connector.x for connector in valid])
    center_y = _median([connector.y for connector in valid])

    if wall_segments:
        wall_x, wall_y, _ = _project_to_perimeter(center_x, center_y, (min_x, min_y, max_x, max_y), wall_segments)
        anchor = wall_y if horizontal else wall_x
    else:
        anchor = center_y if horizontal else center_x

    return horizontal, anchor, min_x, min_y, max_x, max_y


def _sanitize_branch_end(connector, horizontal_main, anchor, main_start_coord, main_end_coord, main_start_z, main_end_z, system_label):
    label = _clean(system_label)
    if horizontal_main:
        projected_coord = max(min(connector.x, main_end_coord), main_start_coord)
        projected_x = projected_coord
        projected_y = anchor
        projected_z = _interpolate_z(main_start_coord, main_end_coord, main_start_z, main_end_z, projected_coord)
    else:
        projected_coord = max(min(connector.y, main_end_coord), main_start_coord)
        projected_x = anchor
        projected_y = projected_coord
        projected_z = _interpolate_z(main_start_coord, main_end_coord, main_start_z, main_end_z, projected_coord)

    if _is_sanitary_label(label):
        return projected_x, projected_y, projected_z
    return projected_x, projected_y, main_start_z


def _branch_segments_for_connector(connector, system_label, settings, main_geom, wall_segments=None):
    horizontal_main = main_geom["horizontal"]
    anchor = main_geom["anchor"]
    main_start_coord = main_geom["start_coord"]
    main_end_coord = main_geom["end_coord"]
    main_start_z = main_geom["start_z"]
    main_end_z = main_geom["end_z"]

    projected_x, projected_y, projected_z = _sanitize_branch_end(
        connector,
        horizontal_main,
        anchor,
        main_start_coord,
        main_end_coord,
        main_start_z,
        main_end_z,
        system_label,
    )

    if _is_sanitary_label(system_label):
        floor_z = main_start_z
        return tuple([
            SegmentPlan(
                (connector.x, connector.y, connector.z),
                (connector.x, connector.y, floor_z),
                "drop-to-floor",
            ),
            SegmentPlan(
                (connector.x, connector.y, floor_z),
                (projected_x, projected_y, projected_z),
                "floor-run",
            ),
        ])

    floor_z = main_start_z
    return tuple([
        SegmentPlan(
            (connector.x, connector.y, connector.z),
            (connector.x, connector.y, floor_z),
            "drop-to-floor",
        ),
        SegmentPlan(
            (connector.x, connector.y, floor_z),
            (projected_x, projected_y, projected_z),
            "floor-run",
        ),
    ])


def build_layout_plan(connectors, system_label, settings=None, wall_segments=None):
    if settings is None:
        settings = LayoutSettings()

    valid = [connector for connector in connectors if not connector.is_connected]
    if not valid:
        raise ValueError("No hay conectores validos para construir el layout.")

    min_x, min_y, max_x, max_y, average_z = _bbox([ConnectorSnapshot(
        element_id=0,
        family_name="",
        category_name="",
        system_kind="",
        is_connected=False,
        x=point[0],
        y=point[1],
        z=point[2],
        flow=0.0,
        fixture_units=0.0,
    ) for point in [(connector.x, connector.y, connector.z) for connector in valid]])
    label = _normalize_system_label(system_label)
    horizontal_main, anchor, min_x, min_y, max_x, max_y = _choose_main_anchor(valid, (min_x, min_y, max_x, max_y, average_z), wall_segments)
    main_start_coord = min_x if horizontal_main else min_y
    main_end_coord = max_x if horizontal_main else max_y
    main_start_z = min(connector.z for connector in valid) + settings.offset_mm
    if _is_sanitary_label(label):
        axis_length = fabs(main_end_coord - main_start_coord)
        main_end_z = main_start_z - (axis_length * settings.sanitary_slope)
    else:
        main_end_z = main_start_z

    if horizontal_main:
        main_segments = (
            SegmentPlan((main_start_coord, anchor, main_start_z), (main_end_coord, anchor, main_end_z), "main-floor-horizontal"),
        )
    else:
        main_segments = (
            SegmentPlan((anchor, main_start_coord, main_start_z), (anchor, main_end_coord, main_end_z), "main-floor-vertical"),
        )

    main_geom = {
        "horizontal": horizontal_main,
        "anchor": anchor,
        "start_coord": main_start_coord,
        "end_coord": main_end_coord,
        "start_z": main_start_z,
        "end_z": main_end_z,
    }

    branches = []
    total_fu = 0.0
    total_flow = 0.0
    for connector in valid:
        total_fu += float(getattr(connector, "fixture_units", 0.0) or 0.0)
        total_flow += float(getattr(connector, "flow", 0.0) or 0.0)
        branch_segments = _branch_segments_for_connector(connector, label, settings, main_geom, wall_segments)
        branches.append(BranchPlan(connector.element_id, branch_segments))

    main_diameter = calculate_pipe_diameter_mm(label, total_fu, total_flow)

    return LayoutPlan(label, main_segments, branches, main_diameter)
