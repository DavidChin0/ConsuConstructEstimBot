# -*- coding: utf-8 -*-
"""
EstimBot - Sync Marks + Autotag + Export
CASE-MARKS-001 | 2026-07-19

Fase 1 - Sync TypeMarks desde csi_to_codigo.json:
  Materials        : ALL_MODEL_MARK = codigo
  WallType (incl. Curtain): ALL_MODEL_TYPE_MARK = codigo  [M_Wall Tag lee TypeMark]
  FloorType        : ALL_MODEL_TYPE_MARK = codigo + rename Name=codigo  [M_Floor Tag lee Type Name]
  Doors/Windows type  : ALL_MODEL_TYPE_MARK = codigo
  Doors/Windows inst  : ALL_MODEL_MARK = type TypeMark  (tag 30X40 lee inst mark)
  Structural/MEP types: ALL_MODEL_TYPE_MARK = codigo
  RoofType/Ceiling    : ALL_MODEL_TYPE_MARK = codigo (TM persists)

Fase 2 - Autotag keynotes en vista activa.
Fase 3 - Export schedules 01-99 / T01-T99 a CSV de cantidades.

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
from System.IO import StreamWriter
from System.Text import UTF8Encoding
from System.Net import WebClient

# ── Constants ────────────────────────────────────────────────────────────────
CSI_TO_CODIGO_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\csi_to_codigo.json"
KEYNOTE_EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S1_keynotes"
SCHEDULES_EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"

# EstimaStruct backend (FastAPI) — misma maquina que Revit
ESTIMASTRUCT_API = "http://127.0.0.1:8002"


# ── HTTP helpers (IronPython 2.7 — sin requests, WebClient .NET nativo) ────────
def _http_get_json(url):
    wc = WebClient()
    try:
        raw = wc.DownloadString(url)
    finally:
        wc.Dispose()
    return json.loads(raw)


def _http_post_json(url, payload_dict):
    wc = WebClient()
    wc.Headers.Add("Content-Type", "application/json")
    body = json.dumps(payload_dict)
    try:
        raw = wc.UploadString(url, "POST", body)
    finally:
        wc.Dispose()
    return json.loads(raw)

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
output.set_title("EstimBot - Sync Marks + Autotag + Export")

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


# ── FASE 3: Export schedules to CSV ──────────────────────────────────────────
def should_export(name):
    n = (name or "").strip()
    return bool(re.match(r"^\d{2}", n) or re.match(r"^T\d{2}", n, re.IGNORECASE))


def csv_escape(v):
    text = str(v) if v is not None else ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "," in text or '"' in text or "\n" in text:
        return '"' + text.replace('"', '""') + '"'
    return text


def csv_row(vals):
    return ",".join(csv_escape(v) for v in vals)


def read_schedule(vs):
    rows = []
    try:
        sec = vs.GetTableData().GetSectionData(DB.SectionType.Body)
        for r in range(sec.NumberOfRows):
            rows.append([
                vs.GetCellText(DB.SectionType.Body, r, c) or ""
                for c in range(sec.NumberOfColumns)
            ])
    except Exception as ex:
        rows.append(["ERROR: {}".format(ex)])
    return rows


def _to_m(feet):
    try:
        return DB.UnitUtils.ConvertFromInternalUnits(feet, DB.UnitTypeId.Meters)
    except Exception:
        return feet * 0.3048


def api_length_blocks():
    from collections import defaultdict
    out = []
    for title, bic in [("18Cable Schedule", DB.BuiltInCategory.OST_Wire),
                        ("19Conduit Schedule", DB.BuiltInCategory.OST_Conduit)]:
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(bic)\
                .WhereElementIsNotElementType().ToElements()
        except Exception:
            continue
        agg = defaultdict(lambda: [0.0, ""])
        for e in elems:
            et = doc.GetElement(e.GetTypeId())
            key = gp(et, KEY_PARAM) or gp(e, KEY_PARAM)
            if not key:
                continue
            lp = e.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
            agg[key][0] += _to_m(lp.AsDouble() if lp else 0.0)
            agg[key][1] = safe_name(et)
        if not agg:
            continue
        rows = [["Keynote", "Type", "Length"]]
        for k in sorted(agg.keys()):
            rows.append([k, agg[k][1], round(agg[k][0], 2)])
        out.append((title, rows))
    return out


def fase3_export_schedules():
    output.print_md("## Fase 3 - Export Schedules")
    if not os.path.isdir(SCHEDULES_EXPORT_DIR):
        os.makedirs(SCHEDULES_EXPORT_DIR)

    out_path = os.path.join(
        SCHEDULES_EXPORT_DIR,
        "schedules_{}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    )

    all_vs = DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).ToElements()
    schedules = sorted(
        [vs for vs in all_vs if should_export(safe_name(vs))],
        key=lambda vs: safe_name(vs)
    )

    exported = []
    writer = StreamWriter(out_path, False, UTF8Encoding(True))
    try:
        for vs in schedules:
            name = safe_name(vs)
            rows = read_schedule(vs)
            if len(rows) < 2:
                continue
            writer.WriteLine(csv_row(["### {} ###".format(name)]))
            for row in rows:
                writer.WriteLine(csv_row(row))
            writer.WriteLine("")
            exported.append(name)
        for title, rows in api_length_blocks():
            writer.WriteLine(csv_row(["### {} ###".format(title)]))
            for row in rows:
                writer.WriteLine(csv_row(row))
            writer.WriteLine("")
            exported.append(title + " (API)")
    finally:
        writer.Close()

    output.print_md("- Schedules exportados: **{}**".format(len(exported)))
    output.print_md("- Archivo: `{}`".format(out_path))
    return out_path, exported


# ── FASE 4: Importar cantidades a una obra de EstimaStruct ────────────────────
def fase4_import_estimastruct(csv_path):
    """Ofrece importar el CSV recien generado a una obra de EstimaStruct via el
    backend FastAPI (:8002). No crashea si el backend no responde."""
    output.print_md("## Fase 4 - Importar a EstimaStruct")

    if not csv_path or not os.path.isfile(csv_path):
        output.print_md("- SKIP: no hay CSV valido para importar.")
        return

    # 1. Preguntar si quiere importar ahora
    quiere = forms.alert(
        "¿Importar estas cantidades a una obra de EstimaStruct ahora?\n\n"
        "El CSV ya quedo guardado en disco:\n{}".format(csv_path),
        title="EstimBot - Importar a EstimaStruct",
        yes=True, no=True
    )
    if not quiere:
        output.print_md("- Usuario eligio NO importar. CSV guardado en disco.")
        return

    # 2. Listar obras del backend
    try:
        obras = _http_get_json(ESTIMASTRUCT_API + "/presupuestos")
    except Exception as e:
        forms.alert(
            "No se pudo conectar a EstimaStruct (:8002). "
            "¿Esta corriendo el backend? Podes importar manualmente desde la web.\n\n"
            "Detalle: {}".format(str(e)),
            title="EstimBot - Error de conexion"
        )
        output.print_md("- ERROR conexion: {}".format(str(e)))
        return

    # Mapear nombre -> id (filtrar templates)
    nombre_a_id = {}
    for o in (obras or []):
        try:
            if o.get("es_template"):
                continue
            nombre = clean(o.get("nombre")) or "(sin nombre)"
            oid = o.get("id")
            if oid is None:
                continue
            # Evitar colisiones de nombre duplicado
            label = nombre
            n = 2
            while label in nombre_a_id:
                label = "{} ({})".format(nombre, n)
                n += 1
            nombre_a_id[label] = oid
        except Exception:
            continue

    if not nombre_a_id:
        forms.alert(
            "El backend respondio pero no hay obras disponibles para importar.",
            title="EstimBot - Sin obras"
        )
        output.print_md("- Backend sin obras (o todas son templates).")
        return

    # 3. Picker de obra
    seleccion = forms.SelectFromList.show(
        sorted(nombre_a_id.keys()),
        title="Selecciona la obra EstimaStruct",
        button_name="Importar cantidades",
        multiselect=False
    )
    if not seleccion:
        output.print_md("- Usuario cancelo el picker. Nada importado.")
        return

    pid = nombre_a_id.get(seleccion)
    if pid is None:
        output.print_md("- Seleccion invalida. Nada importado.")
        return

    # 4. POST import-quantities
    url = "{}/revit-mcp/obras/{}/import-quantities".format(ESTIMASTRUCT_API, pid)
    try:
        resp = _http_post_json(url, {"csv_path": csv_path})
    except Exception as e:
        forms.alert(
            "No se pudo importar a EstimaStruct (:8002). "
            "¿Esta corriendo el backend? Podes importar manualmente desde la web.\n\n"
            "Obra: {}\nDetalle: {}".format(seleccion, str(e)),
            title="EstimBot - Error de importacion"
        )
        output.print_md("- ERROR import: {}".format(str(e)))
        return

    # 5. Mostrar resultado
    salida = ""
    try:
        salida = resp.get("output") or ""
    except Exception:
        salida = str(resp)
    forms.alert(
        "Importacion a '{}' completada.\n\n{}".format(seleccion, salida),
        title="EstimBot - Importacion EstimaStruct"
    )
    output.print_md("- Importado a obra: **{}**".format(seleccion))
    output.print_md("```\n{}\n```".format(salida))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if doc is None:
        forms.alert("No hay documento activo.", title="EstimBot")
        return

    output.print_md("# EstimBot — Sync Marks + Autotag + Export")
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

    # --- Fase 3 ---
    out_path, exported = fase3_export_schedules()

    # --- Summary alert ---
    forms.alert(
        "Marks sync: materiales={mat} muros={wall} pisos={floor_tm} "
        "puertas/vent={door_win_type}\n"
        "Schedules exportados: {n}\n{path}".format(
            n=len(exported), path=out_path, **stats1),
        title="EstimBot - Completado"
    )

    # --- Fase 4: importar a EstimaStruct (solo si fase3 genero out_path) ---
    if out_path:
        try:
            fase4_import_estimastruct(out_path)
        except Exception as e:
            # Nunca perder el resultado de fase1-3 por un fallo en fase4
            forms.alert(
                "Fase 4 (importar a EstimaStruct) fallo, pero el CSV ya quedo "
                "guardado en disco. Podes importar manualmente desde la web.\n\n"
                "Detalle: {}".format(str(e)),
                title="EstimBot - Fase 4 error"
            )


if __name__ == "__main__":
    main()
