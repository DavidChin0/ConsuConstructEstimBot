# -*- coding: utf-8 -*-
"""
Unit tests for pipe_match_core against the REAL golden dataset
(development/mep_metadata/valle_de_angeles2/pipes.json+fittings.json).

Run: D:/LLM/python/python.exe -m pytest pipe_match_core_test.py -v
Pure CPython; no Revit required.
"""

import json
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipe_match_core as core

DATASET = r"D:/GitHub/EstimBot/ConsuConstructEstimBot/ESTIMASTRUCT/development/mep_metadata/valle_de_angeles2"


def _golden():
    with open(os.path.join(DATASET, "pipes.json")) as fh:
        pipes = json.load(fh)
    with open(os.path.join(DATASET, "fittings.json")) as fh:
        fittings = json.load(fh)
    return pipes, fittings


def test_golden_fixture_load():
    pipes, fittings = _golden()
    assert len(pipes) == 45, len(pipes)
    assert len(fittings) == 22, len(fittings)


def test_self_match_perfect():
    """Plan == live -> every row matched, zero unmatched/mismatches."""
    pipes, fittings = _golden()
    report = core.match_inventory(pipes, fittings, pipes, fittings)
    s = report["summary"]
    assert s["matched"] == 45 + 22, s
    assert s["unmatched_live"] == 0, s
    assert s["unmatched_plan"] == 0, s
    assert s["field_mismatches"] == 0, s


def test_missing_pipe_detected():
    pipes, fittings = _golden()
    missing = pipes[:-1]
    report = core.match_inventory(missing, fittings, pipes, fittings)
    assert report["summary"]["unmatched_plan"] == 1
    assert report["summary"]["matched"] == 44 + 22


def test_extra_live_pipe_detected():
    pipes, fittings = _golden()
    extra = copy.deepcopy(pipes)
    extra.append(copy.deepcopy(pipes[0]))
    extra[-1]["element_id"] = 99999901
    report = core.match_inventory(extra, fittings, pipes, fittings)
    assert report["summary"]["unmatched_live"] == 1


def test_diameter_change_is_unmatched():
    pipes, fittings = _golden()
    changed = copy.deepcopy(pipes)
    changed[0]["diameter_mm"] = 50.0
    report = core.match_inventory(changed, fittings, pipes, fittings)
    # diameter is part of the hard key -> the row stops matching
    assert report["summary"]["unmatched_live"] >= 1
    assert report["summary"]["unmatched_plan"] >= 1


def test_level_change_is_unmatched():
    pipes, fittings = _golden()
    changed = copy.deepcopy(fittings)
    changed[0]["level"] = "Terraza 2"
    report = core.match_inventory(pipes, changed, pipes, fittings)
    assert report["summary"]["unmatched_plan"] >= 1
    assert report["summary"]["unmatched_live"] >= 1


def test_system_label_change_is_unmatched_for_pipe():
    pipes, fittings = _golden()
    changed = copy.deepcopy(pipes)
    changed[0]["system_label"] = "Domestic Cold Water 99"
    report = core.match_inventory(changed, fittings, pipes, fittings)
    assert report["summary"]["unmatched_plan"] >= 1
    assert report["summary"]["unmatched_live"] >= 1


def test_length_drift_within_tolerance_is_not_mismatch():
    pipes, fittings = _golden()
    changed = copy.deepcopy(pipes)
    changed[0]["length_ft"] = round(changed[0]["length_ft"] + 0.2, 4)  # < 0.5 ft tol
    report = core.match_inventory(changed, fittings, pipes, fittings)
    assert report["summary"]["matched"] == 45 + 22
    assert report["summary"]["field_mismatches"] == 0


def test_length_drift_beyond_tolerance_flagged_in_field_mismatch():
    pipes, fittings = _golden()
    changed = copy.deepcopy(pipes)
    changed[0]["length_ft"] = round(changed[0]["length_ft"] + 3.0, 4)  # > 0.5 ft tol
    report = core.match_inventory(changed, fittings, pipes, fittings)
    # key still matches (length not in hard key) -> appears in field_mismatches
    assert report["summary"]["matched"] == 45 + 22
    assert report["summary"]["field_mismatches"] >= 1


def test_preview_text_smoke():
    pipes, fittings = _golden()
    report = core.match_inventory(pipes, fittings, pipes, fittings)
    text = core.preview_text(report)
    assert "PIPE MATCH PREVIEW" in text
    assert "matched=67" in text

# --- plan dir resolution ---

def _tmp_workspace(tmpdir):
    return tmpdir


def test_plan_slug_alias(tmp_path):
    d = tmp_path / "valle_de_angeles2"
    d.mkdir()
    (d / "pipes.json").write_text("[]")
    out = core.resolve_plan_dir(str(tmp_path), "Proyecto Apartamento Valle de Angeles2")
    assert out.replace("\\", "/").endswith("valle_de_angeles2")


def test_plan_exact_slug_preferred(tmp_path):
    (tmp_path / "Valle de Angeles 2").mkdir()
    (tmp_path / "Valle de Angeles 2" / "pipes.json").write_text("[]")
    out = core.resolve_plan_dir(str(tmp_path), "Valle de Angeles 2")
    assert "Valle de Angeles 2" in out


def test_plan_single_scan_fallback(tmp_path):
    (tmp_path / "solo_plan").mkdir()
    (tmp_path / "solo_plan" / "pipes.json").write_text("[]")
    out = core.resolve_plan_dir(str(tmp_path), "Some Other Title 123")
    assert out.replace("\\", "/").endswith("solo_plan")


def test_plan_fallback_to_derived_slug(tmp_path):
    out = core.resolve_plan_dir(str(tmp_path), "Marca Desconocida", prefer_existing=False)
    assert out.replace("\\", "/").endswith("Marca Desconocida")


def test_live_out_paths_have_live_prefix(tmp_path):
    p, f = core.live_out_paths_from(str(tmp_path), "pipes")
    assert p.replace("\\", "/").endswith("live_pipes.json")
    assert f.replace("\\", "/").endswith("live_fittings.json")
