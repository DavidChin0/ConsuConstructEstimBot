# -*- coding: utf-8 -*-
"""
pipe_match_core.py — pure matching engine for EstimaStruct pipe/fitting audit.

Compatible with BOTH IronPython 2.7 (runs inside Revit via the :48884 bridge)
and CPython (unit tests with D:/LLM/python, no Revit API imports).

Answers: given a LIVE inventory and a PLAN inventory (golden metadata, e.g.
`development/mep_metadata/<obra>/pipes.json` + `fittings.json`), match every
pipe and fitting by the key set:

    category, family, type, system, material, diameter, level, connectors,
    length, placement

and report: matched / unmatched-live / unmatched-plan / field-mismatches.

Field conventions (mirror mep_metadata dumps):
  - lengths in FEET (`length_ft`), diameters in BOTH `diameter_ft` and
    `diameter_mm`, exact (`diameter_mm` is authoritative for matching).
  - placement: pipes -> `start`/`end` {x,y,z}; fittings -> `location` {x,y,z}.
  - connectors -> list of {x,y,z,is_connected,connector_type}.
  - level -> level NAME string.
  - system -> `system_label` (e.g. "Domestic Cold Water 1").
"""

# ---------------------------------------------------------------------------
# Matching keys
# ---------------------------------------------------------------------------

PIPE_MATCH_FIELDS = [
    "family_name",
    "type_name",
    "system_label",
    "material",
    "diameter_mm",
    "level",
]
FITTING_MATCH_FIELDS = [
    "family_name",
    "type_name",
    "level",
]
# Fields whose mismatch is a *hard* mismatch (anything else is soft/soft note).
# placement/length/connectors hard-mismatch only when the key already matched.


def category_of(kind):
    return "Pipes" if kind == "pipe" else "Pipe Fittings"


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float):
        return value
    return str(value).strip() or None


def _norm_num(value, eps=0.5):
    """Round a pysical dimension so width-of-part 0.5mm doesn't open a gap."""
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return _clean(value)
    if v == 0.0 or abs(v) < 1e-9:
        return 0.0
    return round(v / eps) * eps


def _radius_to_diameter_mm(radius_ft):
    """Connector radius (feet, if present) -> nominal diameter mm."""
    if radius_ft is None:
        return None
    try:
        r = float(radius_ft)
    except Exception:
        return None
    return round(r * 2.0 * 304.8, 1)


# ---------------------------------------------------------------------------
# Key building (plan rows and live rows share these accessors)
# ---------------------------------------------------------------------------


def match_key(row, kind):
    """Canonical (hashable) key used to pair live vs plan rows.

    Hard-match on the fields the goal lists as identity: category, family,
    type, system, material, diameter, level. Connectors/length/placement are
    compared AFTER a key hit (see compare_detail).
    """
    cats = category_of(kind)
    if kind == "pipe":
        return (
            cats,
            _clean(row.get("family_name")),
            _clean(row.get("type_name")),
            _clean(row.get("system_label")),
            _clean(row.get("material")),
            _norm_num(row.get("diameter_mm")),
            _clean(row.get("level")),
        )
    return (
        cats,
        _clean(row.get("family_name")),
        _clean(row.get("type_name")),
        _clean(row.get("level")),
    )


def plan_key(row, kind):
    return match_key(row, kind)


def live_key(row, kind):
    return match_key(row, kind)


# ---------------------------------------------------------------------------
# Detail comparison (soft fields: connectors / length / placement)
# ---------------------------------------------------------------------------


def _xyz_dist(a, b):
    if not a or not b:
        return None
    try:
        dx = float(a.get("x", 0.0)) - float(b.get("x", 0.0))
        dy = float(a.get("y", 0.0)) - float(b.get("y", 0.0))
        dz = float(a.get("z", 0.0)) - float(b.get("z", 0.0))
        return (dx * dx + dy * dy + dz * dz) ** 0.5
    except Exception:
        return None


def compare_detail(live_row, plan_row, kind, placement_tol_ft=1.0, length_tol_ft=0.5):
    """Compare connectors/length/placement of a key-matched pair.

    Returns dict of field -> {expected, actual, note}. Differences within
    tolerance are reported as `note` only and do not fail the match.
    """
    out = {}

    lc = live_row.get("connectors") or []
    pc = plan_row.get("connectors") or []
    out["connector_count"] = {
        "expected": len(pc),
        "actual": len(lc),
        "note": None if len(pc) == len(lc) else "connector count differs",
    }
    l_open = sum(1 for c in lc if not c.get("is_connected"))
    p_open = sum(1 for c in pc if not c.get("is_connected"))
    if p_open != l_open:
        out["open_connectors"] = {
            "expected": p_open,
            "actual": l_open,
            "note": "open connector count differs",
        }

    if kind == "pipe":
        l_len = live_row.get("length_ft")
        p_len = plan_row.get("length_ft")
        if l_len is not None and p_len is not None:
            diff = abs(float(l_len) - float(p_len))
            out["length_ft"] = {
                "expected": p_len,
                "actual": l_len,
                "note": None if diff <= length_tol_ft else "length differs > %.2f ft" % length_tol_ft,
            }
        d = _xyz_dist(live_row.get("start"), plan_row.get("start"))
        if d is not None:
            out["start_placement"] = {
                "expected": plan_row.get("start"),
                "actual": live_row.get("start"),
                "note": None if d <= placement_tol_ft else "start displaced %.1f ft" % d,
            }
        d = _xyz_dist(live_row.get("end"), plan_row.get("end"))
        if d is not None:
            out["end_placement"] = {
                "expected": plan_row.get("end"),
                "actual": live_row.get("end"),
                "note": None if d <= placement_tol_ft else "end displaced %.1f ft" % d,
            }
    else:
        d = _xyz_dist(live_row.get("location"), plan_row.get("location"))
        if d is not None:
            out["placement"] = {
                "expected": plan_row.get("location"),
                "actual": live_row.get("location"),
                "note": None if d <= placement_tol_ft else "displaced %.1f ft" % d,
            }
    return out


# ---------------------------------------------------------------------------
# The matcher
# ---------------------------------------------------------------------------


def match_inventory(live_pipes, live_fittings, plan_pipes, plan_fittings,
                    placement_tol_ft=1.0, length_tol_ft=0.5):
    """Cross-match live inventory against a plan inventory.

    Returns dict:
      {
        "summary": {...counters},
        "matched": [...{live_id, plan_id, kind, key, details}],
        "unmatched_live": [...rows],
        "unmatched_plan": [...rows],
        "field_mismatches": [...{live_id, plan_id, kind, key, fields}],
      }
    """
    def bucket(rows, kind):
        d = {}
        for row in rows:
            k = live_key(row, kind)
            d.setdefault(k, []).append(row)
        return d

    live = {"pipe": live_pipes or [], "fitting": live_fittings or []}
    plan = {"pipe": plan_pipes or [], "fitting": plan_fittings or []}
    lb = {kind: bucket(rows, kind) for kind, rows in live.items()}
    pb = {kind: bucket(rows, kind) for kind, rows in plan.items()}

    matched = []
    unmatched_live = []
    unmatched_plan = []
    field_mismatches = []

    for kind in ("pipe", "fitting"):
        used_plan = set()
        used_live = set()
        pkeys = sorted(pb[kind].keys())
        for pk in pkeys:
            p_rows = pb[kind][pk]
            l_rows = lb[kind].get(pk, [])
            if not l_rows:
                unmatched_plan.extend(p_rows)
                continue
            # pair plan rows with live rows one-to-one in order
            for i, p_row in enumerate(p_rows):
                if i < len(l_rows):
                    l_row = l_rows[i]
                    details = compare_detail(
                        l_row, p_row, kind,
                        placement_tol_ft=placement_tol_ft,
                        length_tol_ft=length_tol_ft,
                    )
                    matched.append({
                        "kind": kind,
                        "key": list(pk),
                        "plan_id": p_row.get("element_id"),
                        "live_id": l_row.get("element_id"),
                        "details": details,
                    })
                    bad = {f: v for f, v in details.items() if v.get("note")}
                    if bad:
                        field_mismatches.append({
                            "kind": kind,
                            "key": list(pk),
                            "plan_id": p_row.get("element_id"),
                            "live_id": l_row.get("element_id"),
                            "fields": bad,
                        })
                else:
                    unmatched_plan.append(p_row)
            # stragglers in live bucket
            for l_row in l_rows[len(p_rows):]:
                unmatched_live.append(l_row)
        # plan keys that simply don't exist live
        for lk, l_rows in lb[kind].items():
            if lk not in pb[kind]:
                unmatched_live.extend(l_rows)

    summary = {
        "plan_pipes": len(plan["pipe"]),
        "plan_fittings": len(plan["fitting"]),
        "live_pipes": len(live["pipe"]),
        "live_fittings": len(live["fitting"]),
        "matched": len(matched),
        "unmatched_live": len(unmatched_live),
        "unmatched_plan": len(unmatched_plan),
        "field_mismatches": len(field_mismatches),
    }
    return {
        "summary": summary,
        "matched": matched,
        "unmatched_live": unmatched_live,
        "unmatched_plan": unmatched_plan,
        "field_mismatches": field_mismatches,
    }


# ---------------------------------------------------------------------------
# Plan directory resolution (pure, dual-compatible)
# ---------------------------------------------------------------------------

# Live doc.Title -> golden plan slug. Kept in ONE place so inventory and
# preview agree; extend when a new live title diverges from its plan folder.
PLAN_SLUG_ALIASES = {
    "Proyecto Apartamento Valle de Angeles2": "valle_de_angeles2",
    "Valle de Angeles2": "valle_de_angeles2",
    "Valle de Angeles 2": "valle_de_angeles2",
}


def _slug_of(title):
    if not title:
        return None
    return "".join(c for c in title if c.isalnum() or c in " -_").strip() or None


def resolve_plan_dir(workspace_dir, title, prefer_existing=True):
    """Map a Live document title to the golden plan directory under
    `workspace_dir` (e.g. `<workspace>/<octubre-slug>/`).

    Priority:
      1. exact slug dir that already contains pipes.json (prefer_existing)
      2. PLAN_SLUG_ALIASES[title] -> dir that contains pipes.json
      3. scan <workspace>/* for the ONLY subdir holding pipes.json
         (returns None if zero or multiple candidates -> ambiguous)
      4. derived slug (fallback, even if dir does not exist yet)

    Returns an absolute path (may not exist in case 4). Pure/filesystem-free
    except path checks; injection-free.
    """
    import os  # noqa: F401  (lazy: keeps module importable in bare sandboxes)

    title_slug = _slug_of(title)
    candidates = []

    def _has_plan(p):
        return p and os.path.isdir(p) and os.path.exists(os.path.join(p, "pipes.json"))

    if prefer_existing and title_slug:
        d = os.path.join(workspace_dir, title_slug)
        if _has_plan(d):
            candidates.append(d)
    alias = PLAN_SLUG_ALIASES.get(title) if title else None
    if alias:
        d = os.path.join(workspace_dir, alias)
        if _has_plan(d):
            candidates.append(d)
    # unique-plan scan fallback
    found = []
    try:
        for name in sorted(os.listdir(workspace_dir)):
            p = os.path.join(workspace_dir, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "pipes.json")):
                found.append(p)
    except Exception:
        found = []
    if len(found) == 1:
        candidates.append(found[0])
    # dedupe, prefer existing hit
    seen = []
    for c in candidates:
        if c not in seen:
            seen.append(c)
    if seen:
        return seen[0]
    if title_slug:
        return os.path.join(workspace_dir, title_slug)
    return None


def live_out_paths_from(plan_dir, kind):
    """Return (pipes_path, fittings_path) writing NEXT TO the golden plan but
    with a `live_` prefix so the golden baseline is never overwritten.
    Called by the inventory script; plan_dir comes from resolve_plan_dir.
    """
    import os  # noqa: F401

    if kind == "pipes":
        return (
            os.path.join(plan_dir, "live_pipes.json"),
            os.path.join(plan_dir, "live_fittings.json"),
        )
    return (
        os.path.join(plan_dir, "live_pipes.json"),
        os.path.join(plan_dir, "live_fittings.json"),
    )


def preview_text(report, max_rows=200):
    """Human-readable preview of a match report."""
    lines = []
    s = report["summary"]
    lines.append("PIPE MATCH PREVIEW")
    lines.append("  plan: %d pipes / %d fittings | live: %d pipes / %d fittings"
                 % (s["plan_pipes"], s["plan_fittings"], s["live_pipes"], s["live_fittings"]))
    lines.append("  matched=%d unmatched_live=%d unmatched_plan=%d field_mismatches=%d"
                 % (s["matched"], s["unmatched_live"], s["unmatched_plan"], s["field_mismatches"]))
    if report["unmatched_plan"]:
        lines.append("UNMATCHED PLAN (missing from live):")
        for row in report["unmatched_plan"][:max_rows]:
            lines.append("  - [%s] %s | %s | %s | d%s | %s"
                         % (row.get("kind") or row.get("element_kind") or "?",
                            row.get("family_name"), row.get("type_name"),
                            row.get("system_label") or "-", row.get("diameter_mm"),
                            row.get("level")))
    if report["unmatched_live"]:
        lines.append("UNMATCHED LIVE (no plan counterpart):")
        for row in report["unmatched_live"][:max_rows]:
            lines.append("  + [%s] %s | %s | %s | d%s | %s"
                         % (row.get("kind") or row.get("element_kind") or "?",
                            row.get("family_name"), row.get("type_name"),
                            row.get("system_label") or "-", row.get("diameter_mm"),
                            row.get("level")))
    if report["field_mismatches"]:
        lines.append("KEY-MATCHED BUT FIELD DIFFS:")
        for fm in report["field_mismatches"][:max_rows]:
            lines.append("  * [%s] %s (plan=%s live=%s)"
                         % (fm["kind"], " | ".join(fm["key"]),
                            fm["plan_id"], fm["live_id"]))
            for f, v in fm["fields"].items():
                lines.append("      ~ %s: plan=%s live=%s" % (f, v["expected"], v["actual"]))
    return "\n".join(lines)