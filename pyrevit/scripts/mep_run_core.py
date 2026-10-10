# -*- coding: utf-8 -*-
"""
Pure on-demand run-planning core for EstimBot MEP piping (CICLO 2).

Sibling of generate_layout_core.py (which plans a full layout from a set of
disconnected fixture connectors). This module answers a narrower question:
given one system, one level and two points, produce a single point-to-point
run (create_mep_run) sized and positioned per the standards captured in
`00 Notes/plans/2026-08-29_mep-tuberias-estandares-params.md` (CICLO 1):
WSFU/DFU sizing, DWV slope 1/4"/ft (20.8 mm/m), trap seal 2-4", vent >= 1/2
drain diameter (min 1-1/4").

Reuses generate_layout_core for system classification, WSFU/DFU-based
diameter, and the SegmentPlan/BranchPlan/LayoutPlan shapes -- this module
does not re-implement sizing tables, only run geometry, clash detection and
the potable-above-drainage rule.

Compatible with both IronPython 2.7 and CPython (no Revit API imports).
"""

from math import sqrt

from generate_layout_core import (
    LayoutPlan,
    SegmentPlan,
    BranchPlan,
    STANDARD_PIPE_SIZES_MM,
    calculate_pipe_diameter_mm,
    resolve_piping_system_classification,
)


# 1/4" per foot, the CICLO 1 reference slope for DWV gravity drainage.
SANITARY_SLOPE_MM_PER_M = 20.8
DEFAULT_POTABLE_OFFSET_MM = -150.0
TRAP_SEAL_DEPTH_MM = 75.0  # mid-range of the 2-4" (50-100mm) allowed band
MIN_VENT_DIAMETER_MM = 31.75  # 1-1/4", the hard floor regardless of drain size
MIN_POTABLE_OVER_DRAIN_CLEARANCE_MM = 50.0


class ClashFinding(object):
    def __init__(self, kind, with_element_id, detail):
        self.kind = kind
        self.with_element_id = with_element_id
        self.detail = detail

    def to_dict(self):
        return {"kind": self.kind, "with_element_id": self.with_element_id, "detail": self.detail}


def _next_standard_size(value_mm):
    for size in STANDARD_PIPE_SIZES_MM:
        if value_mm <= size:
            return size
    return STANDARD_PIPE_SIZES_MM[-1]


def _is_sanitary(classification):
    return classification == "Sanitary"


def _is_vent(classification):
    return classification == "Vent"


def _is_potable(classification):
    return classification in ("DomesticColdWater", "DomesticHotWater")


def default_material_for(classification, norma="UPC"):
    """ASTM-backed material default per classification.

    norma is accepted but currently maps to the same ASTM tables for both
    'HN' and 'UPC': CICLO 1 could not confirm whether the Codigo Hondureno
    de Construccion has its own hidrosanitario chapter (NO_VERIFICADO), so
    until that PDF is read (CICLO 2 pending item #1) HN falls back to UPC's
    ASTM references rather than inventing Honduras-specific numbers.
    """
    if classification == "DomesticHotWater":
        return {"material": "CPVC", "astm": "D2846", "uso_final": "presion"}
    if classification == "DomesticColdWater":
        return {"material": "PVC-SDR", "astm": "D2241", "uso_final": "presion"}
    if classification in ("Sanitary", "Vent"):
        return {"material": "PVC Sch 40 DWV", "astm": "D2665", "uso_final": "gravedad"}
    return {"material": "PVC-SDR", "astm": "D2241", "uso_final": "presion"}


def resolve_run_elevation_mm(classification, from_point, to_point, level_elevation_mm=None,
                              offset_mm=None):
    """Returns (start_z_mm, end_z_mm) honoring the CICLO 1 elevation rules.

    Potable (DCW/DHW): flat run under the slab, offset below level elevation
    (default -150mm, matching generate_layout_core's LayoutSettings default).
    Explicit z on from_point/to_point wins when given; None means "derive
    from level".

    Sanitary: slopes DOWN from from_point to to_point at 1/4"/ft
    (20.8 mm/m) toward the collector -- the caller is expected to pass
    from_point=fixture end, to_point=collector end. If both z's are given
    explicitly, they are honored as-is (caller already computed the slope).
    """
    offset = DEFAULT_POTABLE_OFFSET_MM if offset_mm is None else offset_mm

    start_z = from_point[2]
    end_z = to_point[2]

    if start_z is None or end_z is None:
        if level_elevation_mm is None:
            raise ValueError("z faltante en from_point/to_point y no hay level_elevation_mm para derivarlo")

        if _is_sanitary(classification):
            base_z = level_elevation_mm + offset
            dx = to_point[0] - from_point[0]
            dy = to_point[1] - from_point[1]
            horizontal_m = sqrt(dx * dx + dy * dy) / 1000.0
            drop_mm = horizontal_m * SANITARY_SLOPE_MM_PER_M
            start_z = base_z if start_z is None else start_z
            end_z = (base_z - drop_mm) if end_z is None else end_z
        else:
            base_z = level_elevation_mm + offset
            start_z = base_z if start_z is None else start_z
            end_z = base_z if end_z is None else end_z

    return start_z, end_z


def build_sanitary_extras(from_point, drain_diameter_mm):
    """Trap + vent stub at the fixture end of a sanitary run (extras, not main).

    Trap seal: vertical drop of TRAP_SEAL_DEPTH_MM (within the 2-4" band).
    Vent: diameter = max(drain/2, 1-1/4"), rounded up to the next standard
    size, stubbed vertically upward from the trap.
    """
    x, y, z = from_point
    trap_bottom = (x, y, z - TRAP_SEAL_DEPTH_MM)
    trap_segment = SegmentPlan(from_point, trap_bottom, "trap-seal")

    vent_diameter_mm = _next_standard_size(max(drain_diameter_mm / 2.0, MIN_VENT_DIAMETER_MM))
    vent_top = (x, y, z + 1000.0)
    vent_segment = SegmentPlan(from_point, vent_top, "vent-stub")

    return (
        BranchPlan("trap-seal", (trap_segment,)),
        BranchPlan("vent-stub", (vent_segment,)),
        vent_diameter_mm,
    )


def _segment_distance_mm(a_start, a_end, b_start, b_end):
    """Closest distance between two 3D segments (coarse: sampled midpoints +
    endpoints -- adequate for clash *detection*, not authoritative routing)."""
    def point_seg_dist(p, s, e):
        vx, vy, vz = e[0] - s[0], e[1] - s[1], e[2] - s[2]
        wx, wy, wz = p[0] - s[0], p[1] - s[1], p[2] - s[2]
        seg_len_sq = vx * vx + vy * vy + vz * vz
        if seg_len_sq <= 1e-9:
            dx, dy, dz = p[0] - s[0], p[1] - s[1], p[2] - s[2]
            return sqrt(dx * dx + dy * dy + dz * dz)
        t = max(0.0, min(1.0, (vx * wx + vy * wy + vz * wz) / seg_len_sq))
        cx, cy, cz = s[0] + t * vx, s[1] + t * vy, s[2] + t * vz
        dx, dy, dz = p[0] - cx, p[1] - cy, p[2] - cz
        return sqrt(dx * dx + dy * dy + dz * dz)

    candidates = [
        point_seg_dist(a_start, b_start, b_end),
        point_seg_dist(a_end, b_start, b_end),
        point_seg_dist(b_start, a_start, a_end),
        point_seg_dist(b_end, a_start, a_end),
    ]
    return min(candidates)


def _axes_cross_in_plan(a_start, a_end, b_start, b_end):
    """2D (x,y) segment intersection test -- ignores z, used to find crossings
    that need the potable-above-drainage check even when 3D distance is large
    because the pipes are at very different elevations."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(b_start, b_end, a_start)
    d2 = cross(b_start, b_end, a_end)
    d3 = cross(a_start, a_end, b_start)
    d4 = cross(a_start, a_end, b_end)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def find_clashes(classification, run_start, run_end, run_radius_mm, existing_pipes_mm):
    """existing_pipes_mm: list of dicts with start/end (x,y,z mm), diameter_mm,
    system_label, element_id -- already unit-converted by the caller (the raw
    Revit dump in pipes.json is in feet)."""
    findings = []
    for pipe in existing_pipes_mm:
        p_start = pipe["start"]
        p_end = pipe["end"]
        if p_start is None or p_end is None:
            continue
        p_radius = (pipe.get("diameter_mm") or 0.0) / 2.0

        dist = _segment_distance_mm(run_start, run_end, p_start, p_end)
        if dist < (run_radius_mm + p_radius):
            findings.append(ClashFinding(
                "collision",
                pipe.get("element_id"),
                "distancia %.1fmm < suma radios %.1fmm (sistema existente: %s)" % (
                    dist, run_radius_mm + p_radius, pipe.get("system_label")),
            ))
            continue

        crosses = _axes_cross_in_plan(
            (run_start[0], run_start[1]), (run_end[0], run_end[1]),
            (p_start[0], p_start[1]), (p_end[0], p_end[1]),
        )
        if crosses:
            existing_classification = resolve_piping_system_classification(pipe.get("system_label") or "", [])
            findings.append(ClashFinding(
                "axis_crossing",
                pipe.get("element_id"),
                "cruce de ejes en planta con sistema '%s' (%s)" % (pipe.get("system_label"), existing_classification),
            ))

    return findings


def enforce_potable_over_drainage(classification, run_start, run_end, clashes):
    """Hard rule: potable siempre arriba de drenaje. If this run is potable and
    an axis_crossing clash exists against a system resolved as Sanitary, and
    this run's z is not comfortably above it, bump the run up and log the
    correction in the returned report list (never raises -- report only)."""
    corrections = []
    if not _is_potable(classification):
        return run_start, run_end, corrections

    for clash in clashes:
        if clash.kind != "axis_crossing":
            continue
        if "sanitary" not in clash.detail.lower():
            continue

        needs_lift = MIN_POTABLE_OVER_DRAIN_CLEARANCE_MM
        new_start = (run_start[0], run_start[1], run_start[2] + needs_lift)
        new_end = (run_end[0], run_end[1], run_end[2] + needs_lift)
        corrections.append({
            "type": "potable_above_drainage_correction",
            "with_element_id": clash.with_element_id,
            "lift_mm": needs_lift,
            "detail": clash.detail,
        })
        run_start, run_end = new_start, new_end

    return run_start, run_end, corrections


def create_mep_run(system, level, from_point, to_point, norma="UPC", material=None,
                    fixture_units=0.0, flow=0.0, level_elevation_mm=None,
                    offset_mm=None, existing_pipes_mm=None):
    """Plans a single point-to-point MEP run.

    system: pipe system label (e.g. 'Domestic Cold Water', 'Sanitary', 'Vent').
    level: level name (string, informational -- elevation comes from
        level_elevation_mm when z in from_point/to_point is None).
    from_point/to_point: (x, y, z) tuples in mm; z may be None to auto-derive.
    norma: 'HN' | 'UPC' -- see default_material_for() docstring for the
        current HN==UPC caveat.
    existing_pipes_mm: dataset for clash detection, already in mm (caller
        converts the raw Revit ft dump -- see mep_metadata/*/pipes.json).

    Returns a LayoutPlan (from generate_layout_core) with two extra
    attributes not in the base class: `.clash_report` (list of dicts) and
    `.material` (dict from default_material_for, or the material= override).
    """
    classification = resolve_piping_system_classification(system, [])
    diameter_mm = calculate_pipe_diameter_mm(system, fixture_units, flow)

    start_z, end_z = resolve_run_elevation_mm(
        classification, from_point, to_point, level_elevation_mm, offset_mm,
    )
    run_start = (from_point[0], from_point[1], start_z)
    run_end = (to_point[0], to_point[1], end_z)

    clashes = []
    if existing_pipes_mm:
        run_radius_mm = diameter_mm / 2.0
        clashes = find_clashes(classification, run_start, run_end, run_radius_mm, existing_pipes_mm)

    run_start, run_end, corrections = enforce_potable_over_drainage(classification, run_start, run_end, clashes)

    main_segments = [SegmentPlan(run_start, run_end, "main-run")]
    branches = []

    if _is_sanitary(classification):
        trap_branch, vent_branch, vent_diameter_mm = build_sanitary_extras(run_start, diameter_mm)
        branches.append(trap_branch)
        branches.append(vent_branch)
    else:
        vent_diameter_mm = None

    plan = LayoutPlan(classification, main_segments, branches, diameter_mm)
    plan.clash_report = [c.to_dict() for c in clashes] + corrections
    plan.material = material if material is not None else default_material_for(classification, norma)
    plan.norma = norma
    plan.level = level
    plan.vent_diameter_mm = vent_diameter_mm

    return plan
