# -*- coding: utf-8 -*-
"""
CPython unit tests for mep_run_core.py -- no Revit required.

Run: D:/LLM/python/python.exe -m pytest pyrevit/scripts/test_mep_run_core.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mep_run_core import (
    create_mep_run,
    resolve_run_elevation_mm,
    build_sanitary_extras,
    find_clashes,
    enforce_potable_over_drainage,
    SANITARY_SLOPE_MM_PER_M,
    MIN_VENT_DIAMETER_MM,
)
from generate_layout_core import calculate_pipe_diameter_mm


# ---- diametro por fixture units (WSFU/DFU) ----

def test_diameter_grows_with_fixture_units_potable():
    small = calculate_pipe_diameter_mm("Domestic Cold Water", 1.0, 0.0)
    large = calculate_pipe_diameter_mm("Domestic Cold Water", 30.0, 0.0)
    assert large > small


def test_diameter_grows_with_fixture_units_sanitary():
    small = calculate_pipe_diameter_mm("Sanitary", 1.0, 0.0)
    large = calculate_pipe_diameter_mm("Sanitary", 30.0, 0.0)
    assert large > small


def test_create_mep_run_sizes_by_fixture_units():
    plan = create_mep_run(
        "Domestic Cold Water", "Nivel 1", (0, 0, 0), (1000, 0, 0),
        fixture_units=2.0, level_elevation_mm=0.0,
    )
    assert plan.main_diameter_mm == calculate_pipe_diameter_mm("Domestic Cold Water", 2.0, 0.0)


# ---- pendiente DWV 1/4"/pie ----

def test_sanitary_slope_matches_reference_20_8_mm_per_m():
    start_z, end_z = resolve_run_elevation_mm(
        "Sanitary", (0, 0, None), (1000, 0, None), level_elevation_mm=0.0,
    )
    horizontal_m = 1.0  # 1000mm run
    expected_drop = horizontal_m * SANITARY_SLOPE_MM_PER_M
    assert abs((start_z - end_z) - expected_drop) < 1e-6
    assert end_z < start_z  # drena hacia el colector (to_point)


def test_sanitary_explicit_z_is_honored_as_is():
    start_z, end_z = resolve_run_elevation_mm(
        "Sanitary", (0, 0, 100.0), (1000, 0, 50.0), level_elevation_mm=0.0,
    )
    assert start_z == 100.0
    assert end_z == 50.0


# ---- offsets por nivel ----

def test_potable_offset_below_level_elevation():
    start_z, end_z = resolve_run_elevation_mm(
        "DomesticColdWater", (0, 0, None), (1000, 0, None),
        level_elevation_mm=3000.0, offset_mm=-150.0,
    )
    assert start_z == 2850.0
    assert end_z == 2850.0


def test_potable_offset_is_configurable_per_level():
    start_z, _ = resolve_run_elevation_mm(
        "DomesticColdWater", (0, 0, None), (1000, 0, None),
        level_elevation_mm=6000.0, offset_mm=-300.0,
    )
    assert start_z == 5700.0


def test_missing_z_without_level_elevation_raises():
    try:
        resolve_run_elevation_mm("Sanitary", (0, 0, None), (1000, 0, None), level_elevation_mm=None)
        assert False, "esperaba ValueError"
    except ValueError:
        pass


# ---- deteccion de cruce ----

def test_find_clashes_detects_collision_when_segments_overlap():
    existing = [{
        "element_id": 111,
        "system_label": "Domestic Cold Water 1",
        "start": (0, 0, 0), "end": (1000, 0, 0), "diameter_mm": 32.0,
    }]
    clashes = find_clashes("DomesticColdWater", (0, 5, 0), (1000, 5, 0), 16.0, existing)
    assert len(clashes) == 1
    assert clashes[0].kind == "collision"


def test_find_clashes_detects_axis_crossing_far_apart_in_z():
    existing = [{
        "element_id": 222,
        "system_label": "Sanitary",
        "start": (500, -1000, -2000), "end": (500, 1000, -2000), "diameter_mm": 100.0,
    }]
    clashes = find_clashes("DomesticColdWater", (0, 0, 0), (1000, 0, 0), 16.0, existing)
    assert len(clashes) == 1
    assert clashes[0].kind == "axis_crossing"


def test_find_clashes_no_finding_when_far_and_not_crossing():
    existing = [{
        "element_id": 333,
        "system_label": "Domestic Cold Water 2",
        "start": (5000, 5000, 0), "end": (6000, 5000, 0), "diameter_mm": 32.0,
    }]
    clashes = find_clashes("DomesticColdWater", (0, 0, 0), (1000, 0, 0), 16.0, existing)
    assert len(clashes) == 0


def test_potable_lifted_above_crossing_sanitary_run():
    existing = [{
        "element_id": 444,
        "system_label": "Sanitary",
        "start": (500, -1000, -2000), "end": (500, 1000, -2000), "diameter_mm": 100.0,
    }]
    run_start, run_end = (0, 0, 0), (1000, 0, 0)
    clashes = find_clashes("DomesticColdWater", run_start, run_end, 16.0, existing)
    new_start, new_end, corrections = enforce_potable_over_drainage("DomesticColdWater", run_start, run_end, clashes)
    assert len(corrections) == 1
    assert corrections[0]["type"] == "potable_above_drainage_correction"
    assert new_start[2] > run_start[2]
    assert new_end[2] > run_end[2]


def test_sanitary_run_itself_is_never_lifted():
    existing = [{
        "element_id": 555,
        "system_label": "Domestic Cold Water 1",
        "start": (500, -1000, 2000), "end": (500, 1000, 2000), "diameter_mm": 32.0,
    }]
    run_start, run_end = (0, 0, -2000), (1000, 0, -2020)
    clashes = find_clashes("Sanitary", run_start, run_end, 40.0, existing)
    new_start, new_end, corrections = enforce_potable_over_drainage("Sanitary", run_start, run_end, clashes)
    assert corrections == []
    assert new_start == run_start
    assert new_end == run_end


# ---- seleccion de conectores (trap + vent) ----

def test_sanitary_extras_has_trap_and_vent():
    trap_branch, vent_branch, vent_diameter_mm = build_sanitary_extras((0, 0, 0), drain_diameter_mm=100.0)
    assert trap_branch.element_id == "trap-seal"
    assert vent_branch.element_id == "vent-stub"
    assert trap_branch.segments[0].kind == "trap-seal"
    assert vent_branch.segments[0].kind == "vent-stub"


def test_vent_diameter_is_half_drain_and_never_below_1_1_4in():
    _, _, vent_for_big_drain = build_sanitary_extras((0, 0, 0), drain_diameter_mm=200.0)
    assert vent_for_big_drain >= 100.0  # ~half of 200mm, rounded to standard size

    _, _, vent_for_small_drain = build_sanitary_extras((0, 0, 0), drain_diameter_mm=40.0)
    assert vent_for_small_drain >= MIN_VENT_DIAMETER_MM


def test_create_mep_run_sanitary_includes_trap_and_vent_branches():
    plan = create_mep_run(
        "Sanitary", "Nivel 1", (0, 0, None), (2000, 0, None),
        fixture_units=4.0, level_elevation_mm=0.0,
    )
    kinds = [b.element_id for b in plan.branches]
    assert "trap-seal" in kinds
    assert "vent-stub" in kinds
    assert plan.vent_diameter_mm is not None


def test_create_mep_run_potable_has_no_trap_or_vent():
    plan = create_mep_run(
        "Domestic Cold Water", "Nivel 1", (0, 0, None), (1000, 0, None),
        fixture_units=2.0, level_elevation_mm=0.0,
    )
    assert len(plan.branches) == 0
    assert plan.vent_diameter_mm is None


# ---- material / norma ----

def test_material_defaults_by_classification():
    plan_cold = create_mep_run("Domestic Cold Water", "N1", (0, 0, None), (1000, 0, None), level_elevation_mm=0.0)
    plan_hot = create_mep_run("Domestic Hot Water", "N1", (0, 0, None), (1000, 0, None), level_elevation_mm=0.0)
    plan_sani = create_mep_run("Sanitary", "N1", (0, 0, None), (1000, 0, None), level_elevation_mm=0.0)

    assert plan_cold.material["astm"] == "D2241"
    assert plan_hot.material["astm"] == "D2846"
    assert plan_sani.material["astm"] == "D2665"
    assert plan_sani.material["uso_final"] == "gravedad"
    assert plan_cold.material["uso_final"] == "presion"


def test_material_override_is_honored():
    plan = create_mep_run(
        "Domestic Cold Water", "N1", (0, 0, None), (1000, 0, None),
        level_elevation_mm=0.0, material={"material": "PEX", "astm": "F876"},
    )
    assert plan.material["material"] == "PEX"
