# SCRIPT: EXPORT REVIT SCHEDULES TO SINGLE CSV
# Revit 2025 | Dynamo CPython3 | EstimBot v4.0
#
# Exports all schedules whose name starts with a digit or "T0"
# (matches: 01Door Schedule, 02Electrico ... T01, T02, T03)
# Output: one CSV with each schedule as a labeled block.
# No IN[x] needed. No transaction needed (read only). Run.

import clr
import os
import csv
from datetime import datetime

clr.AddReference('RevitAPI')
clr.AddReference('RevitServices')

from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule, SectionType
from RevitServices.Persistence import DocumentManager

doc = DocumentManager.Instance.CurrentDBDocument

ROOT_DIR = os.environ.get(
    "ESTIMBOT_PYREVIT_ROOT",
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
OUTPUT_DIR = os.environ.get(
    "ESTIMBOT_PYREVIT_SCHEDULES_DIR",
    os.path.join(ROOT_DIR, "step6_quantities")
)
OUTPUT_PATH = os.path.join(
    OUTPUT_DIR,
    "schedules_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── FILTER SCHEDULES BY NAME ───────────────────────────────────────────────
# Include schedules whose name starts with a digit (01-10) or "T0" (T01-T03)

def should_export(name):
    if not name:
        return False
    return name[0].isdigit() or name.upper().startswith("T0")

all_schedules = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()

schedules = sorted(
    [s for s in all_schedules if should_export(s.Name)],
    key=lambda s: s.Name
)

# ── READ SCHEDULE DATA ─────────────────────────────────────────────────────

def read_schedule(vs):
    try:
        tsd   = vs.GetTableData().GetSectionData(SectionType.Body)
        n_rows = tsd.NumberOfRows
        n_cols = tsd.NumberOfColumns
        rows   = []
        for r in range(n_rows):
            row = []
            for c in range(n_cols):
                try:
                    cell = vs.GetCellText(SectionType.Body, r, c)
                    row.append(cell or "")
                except Exception:
                    row.append("")
            rows.append(row)
        return rows
    except Exception as e:
        return [["ERROR: " + str(e)]]

# ── WRITE CSV ──────────────────────────────────────────────────────────────

exported = []
skipped  = []

with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)

    for vs in schedules:
        rows = read_schedule(vs)

        if len(rows) < 2:          # empty schedule (no data rows)
            skipped.append(vs.Name)
            continue

        headers   = rows[0]        # row 0 = column names
        data_rows = rows[1:]       # rows 1+ = actual data

        # Schedule name separator row
        writer.writerow(["### " + vs.Name + " ###"])
        writer.writerow(headers)
        writer.writerows(data_rows)
        writer.writerow([])        # blank line between schedules

        exported.append(vs.Name)

# ── OUT ────────────────────────────────────────────────────────────────────

OUT = {
    "status":       "success",
    "output_path":  OUTPUT_PATH,
    "exported":     exported,
    "skipped_empty":skipped,
    "total":        len(exported),
}
