"""
revit_marks_master.py — Master script for setting EstimaStruct marks in Revit.

Run via execute_revit_code MCP tool (paste CODE string).
DO NOT nest DB.Transaction — endpoint already wraps in one.

MARK RULES (canonical 2026-07-19):
  WallType/RoofType/CeilingType  : TypeMark = EMPTY (not persisted by Revit, silently drops after save)
  FloorType                       : TypeMark = codigo (DOES persist; set from csi_to_codigo.json)
  FloorType Name                  : RENAME to TypeMark codigo so M_Floor Tag shows codigo
                                    (M_Floor Tag reads SYMBOL_NAME_PARAM / Type Name, NOT TypeMark)
  Floor Instance ALL_MODEL_MARK   : = FloorType TypeMark (sync for schedule/filter use)
  DB.Material                     : ALL_MODEL_MARK = codigo
  Doors/Windows TYPE               : ALL_MODEL_TYPE_MARK = codigo
  Doors/Windows INSTANCE           : ALL_MODEL_MARK = copy of type's TypeMark
                                    (door/window tags read instance ALL_MODEL_MARK, not type TypeMark)
  Structural/MEP element types     : ALL_MODEL_TYPE_MARK = codigo
  Sanitario/Plumbing types         : ALL_MODEL_TYPE_MARK = codigo (watch for GAP CSIs)

GOTCHAS:
  - execute_revit_code wraps in transaction. NEVER nest DB.Transaction.
  - DB.ElementId(long(n)) required in Revit 2024+ IronPython — avoid bare int().
  - WallType TypeMark silently drops after save/reload. Leave empty, use keynote only.
  - GAP CSI (not in fichas catalog) → csi_to_codigo returns "" → TypeMark unchanged → manual fix.
  - Door/window tags read ALL_MODEL_MARK (instance mark) — must sync inst_mark = type TypeMark.
  - FloorType TypeMark DOES persist (unlike WallType/RoofType/CeilingType).
  - M_Floor Tag reads SYMBOL_NAME_PARAM (Type Name), NOT TypeMark nor instance Mark.
    Fix: rename FloorType.Name = TypeMark codigo so tag displays codigo automatically.
  - Multiple floor types can share the same TypeMark (e.g. 4x CONC-02 variants).
    Strategy: first type keeps bare name (CONC-02), duplicates get suffix (CONC-02-2, etc.).
  - Unplaced window types with numeric TypeMark (40-48) = pre-existing Revit defaults, skip.
  - CC-none material (mat_id=2153364) = void placeholder, skip.
  - Air/Membrane compound layers = skip (no keynote assignable).
  - Open Revit dialogs block ExternalEvent → close all before execute_revit_code.
  - element.Name AttributeError in IronPython: use get_Parameter(SYMBOL_NAME_PARAM).AsString()
    or element.get_Parameter(ALL_MODEL_TYPE_NAME).AsString() instead.

VERIFIED SESSION (2026-07-19):
  - Door 2515165 inst_mark = PM-1       ✓
  - Door 2522441 inst_mark = PT-2       ✓
  - Sanitario type 1532501 TypeMark = SN-14  ✓
  - FloorType 2443413 TypeMark = CONC-02     ✓
  - FloorType 2443413 renamed CONC-02        ✓ (tag now shows CONC-02)
  - 12 floor types with TypeMark renamed     ✓
  - 5 floor instances inst_mark synced       ✓
"""

CODE = r'''
import io, json
from collections import defaultdict
from pyrevit import revit, DB

doc = revit.doc
TYPE_MARK  = DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
INST_MARK  = DB.BuiltInParameter.ALL_MODEL_MARK
KEY_PARAM  = DB.BuiltInParameter.KEYNOTE_PARAM
SYM_NAME   = DB.BuiltInParameter.SYMBOL_NAME_PARAM

SKIP_NAMES    = {"CC-none", "Air", "Default"}
SKIP_PREFIXES = ("<",)
COMPOUND_CATS = {
    DB.BuiltInCategory.OST_Walls,
    DB.BuiltInCategory.OST_Roofs,
    DB.BuiltInCategory.OST_Ceilings,
}

# ---------------------------------------------------------------------------
# Load csi_to_codigo map
# ---------------------------------------------------------------------------
CSI_MAP_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\csi_to_codigo.json"
with io.open(CSI_MAP_PATH, encoding="utf-8") as f:
    csi_map = json.load(f)

stats = {"mat": 0, "type": 0, "floor_type": 0, "floor_rename": 0,
         "floor_inst": 0, "door_win": 0, "skip": 0, "error": 0}


def get_csi(elem):
    p = elem.get_Parameter(KEY_PARAM)
    return (p.AsString() or "").strip() if p else ""


def safe_set(elem, bip, val):
    """Set a BuiltInParameter string value. Returns True if changed."""
    p = elem.get_Parameter(bip)
    if p and not p.IsReadOnly and p.StorageType == DB.StorageType.String:
        if p.AsString() != val:
            p.Set(val)
            return True
    return False


# ---------------------------------------------------------------------------
# SECTION 1 — Materials  (ALL_MODEL_MARK = codigo)
# ---------------------------------------------------------------------------
mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
for m in mats:
    name = ""
    try:
        np = m.get_Parameter(DB.BuiltInParameter.MATERIAL_NAME)
        name = np.AsString() if np else ""
    except:
        pass
    if not name or name in SKIP_NAMES or any(name.startswith(p) for p in SKIP_PREFIXES):
        stats["skip"] += 1
        continue
    csi = get_csi(m)
    if not csi:
        continue
    codigo = csi_map.get(csi, "")
    if not codigo:
        continue
    if safe_set(m, INST_MARK, codigo):
        stats["mat"] += 1
        print("MAT {} -> {}".format(name[:30], codigo))


# ---------------------------------------------------------------------------
# SECTION 2 — Element types (ALL_MODEL_TYPE_MARK = codigo)
#             Skip Wall/Roof/Ceiling compound types (TypeMark doesn't persist)
# ---------------------------------------------------------------------------
all_types = DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements()
for t in all_types:
    cat = t.Category
    if not cat:
        continue
    try:
        bic = DB.Category.GetBuiltInCategory(cat)
        if bic in COMPOUND_CATS:
            continue
    except:
        pass
    csi = get_csi(t)
    if not csi:
        continue
    codigo = csi_map.get(csi, "")
    if not codigo:
        continue
    if safe_set(t, TYPE_MARK, codigo):
        stats["type"] += 1


# ---------------------------------------------------------------------------
# SECTION 3 — Floor types
#   3a. Set TypeMark = codigo  (DOES persist, unlike Wall/Roof/Ceiling)
#   3b. Rename Type Name = TypeMark  (so M_Floor Tag displays codigo)
#       M_Floor Tag reads SYMBOL_NAME_PARAM (Type Name), NOT TypeMark.
#       Multiple types sharing same TypeMark get suffix: CONC-02, CONC-02-2, etc.
# ---------------------------------------------------------------------------
floor_types = DB.FilteredElementCollector(doc)\
    .OfCategory(DB.BuiltInCategory.OST_Floors)\
    .WhereElementIsElementType()\
    .ToElements()

tm_seen = defaultdict(int)
for ft in floor_types:
    csi = get_csi(ft)
    codigo = csi_map.get(csi, "") if csi else ""

    # 3a — set TypeMark
    if codigo and safe_set(ft, TYPE_MARK, codigo):
        stats["floor_type"] += 1

    # 3b — rename Type Name to TypeMark so floor tag shows codigo
    tm_p = ft.get_Parameter(TYPE_MARK)
    tm_val = tm_p.AsString() if tm_p else ""
    if not tm_val:
        continue

    tm_seen[tm_val] += 1
    count = tm_seen[tm_val]
    new_name = tm_val if count == 1 else "{}-{}".format(tm_val, count)

    current_name_p = ft.get_Parameter(SYM_NAME)
    current_name = current_name_p.AsString() if current_name_p else ""
    if current_name == new_name:
        continue

    try:
        ft.Name = new_name
        stats["floor_rename"] += 1
        print("FLOOR RENAME id={} '{}' -> '{}'".format(ft.Id.Value, current_name[:30], new_name))
    except Exception as e:
        stats["error"] += 1
        print("FLOOR RENAME ERROR id={}: {}".format(ft.Id.Value, str(e)[:60]))


# ---------------------------------------------------------------------------
# SECTION 4 — Door / Window instances
#   Tag reads ALL_MODEL_MARK (instance), not type TypeMark.
#   Sync inst_mark = type's TypeMark on all placed instances.
# ---------------------------------------------------------------------------
for cat in [DB.BuiltInCategory.OST_Doors, DB.BuiltInCategory.OST_Windows]:
    for inst in DB.FilteredElementCollector(doc).OfCategory(cat)\
            .WhereElementIsNotElementType().ToElements():
        typ = doc.GetElement(inst.GetTypeId())
        if not typ:
            continue
        p_tm = typ.get_Parameter(TYPE_MARK)
        tm_val = p_tm.AsString() if p_tm else ""
        if not tm_val:
            continue
        if safe_set(inst, INST_MARK, tm_val):
            stats["door_win"] += 1


# ---------------------------------------------------------------------------
# SECTION 5 — Floor instances  (ALL_MODEL_MARK = FloorType TypeMark)
#   Sync for schedule/filter use.  Tag display is handled via Type Name rename above.
# ---------------------------------------------------------------------------
for fl in DB.FilteredElementCollector(doc)\
        .OfCategory(DB.BuiltInCategory.OST_Floors)\
        .WhereElementIsNotElementType().ToElements():
    ft = doc.GetElement(fl.GetTypeId())
    if not ft:
        continue
    p_tm = ft.get_Parameter(TYPE_MARK)
    tm_val = p_tm.AsString() if p_tm else ""
    if not tm_val:
        continue
    if safe_set(fl, INST_MARK, tm_val):
        stats["floor_inst"] += 1
        print("FLOOR INST id={} mark -> '{}'".format(fl.Id.Value, tm_val))


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
print("\n=== DONE ===")
for k, v in sorted(stats.items()):
    print("  {}: {}".format(k, v))
'''

if __name__ == "__main__":
    print("Paste CODE string into execute_revit_code MCP tool.")
    print("Do NOT run this file directly — it requires IronPython inside Revit.")
    print("CODE is defined above as a raw string literal.")
