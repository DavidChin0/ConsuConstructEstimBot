# -*- coding: utf-8 -*-
"""
EstimBot - Sync Marks
CASE-MARKS-001 | 2026-07-19, dividido 2026-08-02 (goal-20149 rework)

Fase 1 - Sync TypeMarks desde csi_to_codigo.json:
  Materials        : ALL_MODEL_MARK = codigo
  WallType (incl. Curtain): ALL_MODEL_TYPE_MARK = codigo  [M_Wall Tag lee TypeMark]
  FloorType        : ALL_MODEL_TYPE_MARK = codigo + rename Name=codigo  [M_Floor Tag lee Type Name]
  Doors/Windows type  : ALL_MODEL_TYPE_MARK = codigo
  Doors/Windows inst  : ALL_MODEL_MARK = type TypeMark  (tag 30X40 lee inst mark)
  Structural/MEP types: ALL_MODEL_TYPE_MARK = codigo
  RoofType/Ceiling    : ALL_MODEL_TYPE_MARK = codigo (TM persists)

Fase 2 - Autotag keynotes en vista activa.

2026-08-02: Fase 3 (export schedules) y Fase 4 (import a EstimaStruct) se
sacaron de este botón — ya viven en "Exportar e Importar Schedules.pushbutton"
(Export.panel), que las cubre completas. Este botón queda solo Sync Marks +
Autotag, sin duplicar responsabilidad.

GOTCHAS:
  - No nested DB.Transaction — usar revit.Transaction de pyRevit
  - DB.ElementId(long(n)) en Revit 2024+
  - M_Floor Tag lee SYMBOL_NAME_PARAM (Type Name) -> rename Name=codigo
  - M_Wall Tag lee ALL_MODEL_TYPE_MARK -> setear TypeMark basta
  - Door tag 30X40 lee ALL_MODEL_MARK (inst) -> sync inst_mark = type_mark
  - CC-none (mat_id=2153364) y Air materials: skip
  - WallType TypeMark persiste con codigos limpios (SF-01, STR-05) — verificado
  - GAP CSIs (no en fichas) -> set_marks los deja sin cambio
"""

from pyrevit import DB, forms, revit, script
import codecs
import io
import json
import os
import re
from datetime import datetime

# ── Constants ────────────────────────────────────────────────────────────────
CSI_TO_CODIGO_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\csi_to_codigo.json"
KEYNOTE_EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S1_keynotes"


KEY_PARAM  = DB.BuiltInParameter.KEYNOTE_PARAM
TYPE_MARK  = DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
INST_MARK  = DB.BuiltInParameter.ALL_MODEL_MARK

SKIP_MAT_NAMES  = {"CC-none", "Air", "Default", ""}
SKIP_MAT_PREFIX = ("<",)

# Compound cats where Name rename needed for floor tag display
FLOOR_CAT   = DB.BuiltInCategory.OST_Floors
WALL_CAT    = DB.BuiltInCategory.OST_Walls
DOOR_CAT    = DB.BuiltInCategory.OST_Doors
WIN_CAT     = DB.BuiltInCategory.OST_Windows

CSI_PATTERN = re.compile(r"^\d{2}(?:\s\d{2}){2}(?:\.[0-9A-Za-z\.]+)?$")

ALLOWED_VIEW_TYPES = {
    "FloorPlan", "CeilingPlan", "Section", "Elevation",
    "Detail", "DraftingView", "EngineeringPlan", "StructuralPlan", "AreaPlan",
}

doc    = revit.doc
output = script.get_output()
output.set_title("EstimBot - Sync Marks")

# ── Helpers ──────────────────────────────────────────────────────────────────
def clean(value):
    if value is None:
        return ""
    try:
        return str(value).replace("_x000D_", "").strip()
    except Exception:
        return ""


def safe_name(elem):
    if elem is None:
        return ""
    try:
        v = DB.Element.Name.__get__(elem)
        if v:
            return clean(v)
    except Exception:
        pass
    try:
        return clean(elem.Name)
    except Exception:
        return ""


def gp(elem, bip):
    if elem is None:
        return ""
    p = elem.get_Parameter(bip)
    return (p.AsString() or "") if p else ""


def sp(elem, bip, val):
    """Set parameter if writable and value differs. Returns True if changed."""
    if elem is None:
        return False
    p = elem.get_Parameter(bip)
    if not p or p.IsReadOnly:
        return False
    if p.AsString() == val:
        return False
    try:
        p.Set(val)
        return True
    except Exception:
        return False


def get_csi(elem):
    return gp(elem, KEY_PARAM).strip()


def load_csi_map():
    if not os.path.isfile(CSI_TO_CODIGO_PATH):
        return {}
    try:
        with io.open(CSI_TO_CODIGO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def is_csi(text):
    return bool(CSI_PATTERN.match(clean(text)))


def view_type_name(view):
    try:
        return view.ViewType.ToString()
    except Exception:
        return str(view.ViewType)


# ── FASE 1: Sync TypeMarks ────────────────────────────────────────────────────
def fase1_sync_marks(csi_map):
    output.print_md("## Fase 1 - Sync TypeMarks")
    stats = {"mat": 0, "wall": 0, "floor_tm": 0, "floor_name": 0,
             "door_win_type": 0, "door_win_inst": 0, "other_type": 0,
             "skip": 0, "no_map": 0}

    with revit.Transaction("EstimBot - Sync Marks"):

        # 1A: Materials (ALL_MODEL_MARK = codigo)
        for m in DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements():
            name = safe_name(m)
            if name in SKIP_MAT_NAMES or any(name.startswith(p) for p in SKIP_MAT_PREFIX):
                stats["skip"] += 1
                continue
            csi = get_csi(m)
            if not csi:
                continue
            codigo = csi_map.get(csi, "")
            if not codigo:
                stats["no_map"] += 1
                continue
            if sp(m, INST_MARK, codigo):
                stats["mat"] += 1

        # 1B: Wall types (TypeMark = codigo — persists for walls)
        for wt in DB.FilteredElementCollector(doc).OfCategory(WALL_CAT)\
                .WhereElementIsElementType().ToElements():
            csi = get_csi(wt)
            if not csi:
                continue
            codigo = csi_map.get(csi, "")
            if not codigo:
                stats["no_map"] += 1
                continue
            if sp(wt, TYPE_MARK, codigo):
                stats["wall"] += 1

        # 1C: Floor types — TypeMark + rename Name (M_Floor Tag reads Type Name)
        for ft in DB.FilteredElementCollector(doc).OfCategory(FLOOR_CAT)\
                .WhereElementIsElementType().ToElements():
            csi = get_csi(ft)
            if not csi:
                continue
            codigo = csi_map.get(csi, "")
            if not codigo:
                stats["no_map"] += 1
                continue
            if sp(ft, TYPE_MARK, codigo):
                stats["floor_tm"] += 1
            # Rename Name = codigo so M_Floor Tag (reads SYMBOL_NAME_PARAM) shows codigo
            current_name = safe_name(ft)
            if current_name and not current_name.startswith(codigo):
                try:
                    ft.Name = codigo
                    stats["floor_name"] += 1
                except Exception:
                    # Name collision — append suffix
                    for suffix in range(2, 20):
                        try:
                            ft.Name = "{}-{}".format(codigo, suffix)
                            stats["floor_name"] += 1
                            break
                        except Exception:
                            continue

        # 1D: Door/Window types (TypeMark = codigo) + instances (inst_mark = TypeMark)
        for cat in [DOOR_CAT, WIN_CAT]:
            # Types
            for et in DB.FilteredElementCollector(doc).OfCategory(cat)\
                    .WhereElementIsElementType().ToElements():
                csi = get_csi(et)
                if not csi:
                    continue
                codigo = csi_map.get(csi, "")
                if not codigo:
                    stats["no_map"] += 1
                    continue
                if sp(et, TYPE_MARK, codigo):
                    stats["door_win_type"] += 1
            # Instances — sync inst_mark = type's TypeMark
            for inst in DB.FilteredElementCollector(doc).OfCategory(cat)\
                    .WhereElementIsNotElementType().ToElements():
                etype = doc.GetElement(inst.GetTypeId())
                if not etype:
                    continue
                tm_val = gp(etype, TYPE_MARK)
                if not tm_val:
                    continue
                if sp(inst, INST_MARK, tm_val):
                    stats["door_win_inst"] += 1

        # 1E: All other element types (Structural, MEP, Plumbing, etc.)
        SKIP_CATS = {WALL_CAT, FLOOR_CAT, DOOR_CAT, WIN_CAT}
        for et in DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
            cat = et.Category
            if not cat:
                continue
            try:
                bic = DB.Category.GetBuiltInCategory(cat)
                if bic in SKIP_CATS:
                    continue
            except Exception:
                pass
            csi = get_csi(et)
            if not csi:
                continue
            codigo = csi_map.get(csi, "")
            if not codigo:
                stats["no_map"] += 1
                continue
            if sp(et, TYPE_MARK, codigo):
                stats["other_type"] += 1

    output.print_md("- Materiales: **{}**".format(stats["mat"]))
    output.print_md("- Muros (TypeMark): **{}**".format(stats["wall"]))
    output.print_md("- Pisos (TypeMark): **{}**  |  Rename Name: **{}**".format(
        stats["floor_tm"], stats["floor_name"]))
    output.print_md("- Puertas/Ventanas tipo: **{}**  |  inst: **{}**".format(
        stats["door_win_type"], stats["door_win_inst"]))
    output.print_md("- Otros tipos (MEP/Estruct): **{}**".format(stats["other_type"]))
    output.print_md("- Sin mapa CSI: **{}**  |  Omitidos: **{}**".format(
        stats["no_map"], stats["skip"]))
    return stats


# ── FASE 2: Autotag keynotes en vista activa ──────────────────────────────────
def resolve_keynote_txt():
    # 1. path cargado en Revit
    try:
        kt = DB.KeynoteTable.GetKeynoteTable(doc)
        ext = kt.GetExternalFileReference()
        if DB.ExternalFileReference.IsValidExternalFileReference(ext):
            for getter in ("GetAbsolutePath", "GetPath"):
                try:
                    mp = getattr(ext, getter)()
                    p = clean(DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(mp))
                    if p and os.path.isfile(p):
                        return p, "loaded"
                except Exception:
                    pass
    except Exception:
        pass
    # 2. latest export
    if os.path.isdir(KEYNOTE_EXPORT_DIR):
        candidates = [
            os.path.join(KEYNOTE_EXPORT_DIR, f)
            for f in os.listdir(KEYNOTE_EXPORT_DIR)
            if f.lower().endswith(".txt") and f.lower().startswith("revitkeynotes_")
        ]
        if candidates:
            candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return candidates[0], "latest"
    return "", ""


def load_keynote_map(path):
    kmap = {}
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            with codecs.open(path, "r", enc) as f:
                for line in f:
                    parts = [clean(x) for x in clean(line).split("\t")]
                    if parts and is_csi(parts[0]):
                        kmap[parts[0]] = parts[1] if len(parts) > 1 else ""
            if kmap:
                return kmap
        except Exception:
            continue
    return kmap


def element_center(elem, view):
    try:
        loc = elem.Location
        if isinstance(loc, DB.LocationPoint):
            return loc.Point
        if isinstance(loc, DB.LocationCurve):
            return loc.Curve.Evaluate(0.5, True)
    except Exception:
        pass
    try:
        bb = elem.get_BoundingBox(view) or elem.get_BoundingBox(None)
        if bb:
            return bb.Min.Add(bb.Max).Multiply(0.5)
    except Exception:
        pass
    return None


def read_keynote_on_elem(elem):
    for candidate in (elem, doc.GetElement(elem.GetTypeId())):
        if candidate is None:
            continue
        p = candidate.get_Parameter(KEY_PARAM)
        v = (p.AsString() or "") if p else ""
        if v:
            return v
    return ""


def fase2_autotag(kmap):
    output.print_md("## Fase 2 - Autotag Keynotes")
    view = doc.ActiveView
    vt = view_type_name(view)
    if vt not in ALLOWED_VIEW_TYPES:
        output.print_md("Vista `{}` no soporta autotag. Saltando.".format(vt))
        return 0

    eligible = []
    skipped  = []

    for elem in DB.FilteredElementCollector(doc, view.Id)\
            .WhereElementIsNotElementType().ToElements():
        if elem is None or getattr(elem, "ViewSpecific", False):
            continue
        cat = elem.Category
        if not cat or clean(cat.Name) == "Keynote Tags":
            continue
        kn = read_keynote_on_elem(elem)
        if not kn or not is_csi(kn):
            skipped.append((clean(cat.Name), kn or "", "Sin keynote CSI"))
            continue
        if kn not in kmap:
            skipped.append((clean(cat.Name), kn, "CSI no en keynote TXT"))
            continue
        try:
            ref = DB.Reference(elem)
        except Exception:
            skipped.append((clean(cat.Name), kn, "Sin referencia"))
            continue
        pt = element_center(elem, view)
        if pt is None:
            skipped.append((clean(cat.Name), kn, "Sin punto"))
            continue
        eligible.append({"elem": elem, "ref": ref, "pt": pt, "kn": kn})

    output.print_md("Elegibles: **{}**  |  Omitidos: **{}**".format(
        len(eligible), len(skipped)))

    if not eligible:
        return 0

    created = 0
    with revit.Transaction("EstimBot - Autotag Keynotes"):
        for item in eligible:
            try:
                tag = DB.IndependentTag.Create(
                    doc, view.Id, item["ref"], False,
                    DB.TagMode.TM_ADDBY_CATEGORY,
                    DB.TagOrientation.Horizontal, item["pt"])
                if tag:
                    created += 1
            except Exception:
                pass

    output.print_md("- Etiquetas creadas: **{}**".format(created))
    return created


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if doc is None:
        forms.alert("No hay documento activo.", title="EstimBot")
        return

    output.print_md("# EstimBot — Sync Marks")
    output.print_md("CASE-MARKS-001 | {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M")))

    # --- Cargar csi_map ---
    csi_map = load_csi_map()
    if not csi_map:
        forms.alert(
            "No se encontró csi_to_codigo.json en:\n{}\n\n"
            "Ejecutar generate_csi_to_codigo.py primero.".format(CSI_TO_CODIGO_PATH),
            title="EstimBot"
        )
        return
    output.print_md("CSI map cargado: **{}** entradas".format(len(csi_map)))

    # --- Fase 1 ---
    stats1 = fase1_sync_marks(csi_map)

    # --- Fase 2 ---
    kn_path, kn_source = resolve_keynote_txt()
    if kn_path:
        kmap = load_keynote_map(kn_path)
        output.print_md("Keynote TXT: `{}` ({})".format(kn_path, kn_source))
        fase2_autotag(kmap)
    else:
        output.print_md("**SKIP Fase 2** — keynote TXT no encontrado.")

    # --- Summary alert ---
    forms.alert(
        "Marks sync: materiales={mat} muros={wall} pisos={floor_tm} "
        "puertas/vent={door_win_type}".format(**stats1),
        title="EstimBot - Sync Marks Completado"
    )


if __name__ == "__main__":
    main()
