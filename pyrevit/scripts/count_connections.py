# -*- coding: utf-8 -*-
"""
count_connections.py - Conexiones de acero VV / VC filtradas por KEYNOTE (CSI).

Fuente UNICA (la usan ExportTools.extension y EstimBot.extension via delegacion).

Reglas (acordadas 2026-06-03):
  - Incluir SOLO miembros cuyo keynote (CSI) este en rango:
        Vigas    : 05 20 00.4 .. 05 20 00.9   (VA7..VA11)
        Columnas : 05 20 00.10 .. 05 20 00.14  (C6..C10)
  - Excluir canaletas galvanizadas (05 31 xx), HSS C1..C5 (05 20 00.0..3), pedestales y todo lo demas.
  - Pedestales (03 31 00.20..27) NO generan conexion: la placa base ya esta en los insumos del pedestal.
  - Clasifica el TIPO geometrico:
        VC = endpoint de viga dentro del bbox de una columna en rango
        VV = endpoint de viga sobre la curva de otra viga en rango (no en columna)
  - pyRevit NO decide soldada/apernada NI costo. Exporta CSV crudo:
        tipo_conexion, csi_viga, perfil_viga, csi_columna, perfil_columna, cantidad
    (en VV, las columnas csi_columna/perfil_columna llevan la viga de soporte).
    EstimaStruct (modulo Conexiones) decide soldada/apernada -> ficha + insumos x cantidad.

Lectura de keynote: BuiltInParameter.KEYNOTE_PARAM (patron probado en PYREVIT_S10),
override de instancia primero, si no, el del tipo.

Export: D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\S5_schedules\\
  - C10_connections_YYYYMMDD_HHMMSS.csv
  - C10_connections_latest.csv  (siempre sobreescrito)
"""

from pyrevit import revit, DB, script, forms

import os
import io
import re
from datetime import datetime
from collections import defaultdict

doc = revit.doc
output = script.get_output()

EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"

# Tolerancia geometrica en pies (~150 mm) para bbox y punto-a-curva.
TOL = 0.5

CSV_HEADERS = [
    "tipo_conexion", "csi_viga", "perfil_viga",
    "csi_columna", "perfil_columna", "cantidad",
]


# ---------------------------------------------------------------------------
# Keynote / clasificacion por CSI
# ---------------------------------------------------------------------------
def _kn_from_param(elem):
    """Lee KEYNOTE_PARAM de un elemento (instancia o tipo). '' si no hay."""
    try:
        p = elem.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
        if p is not None:
            v = p.AsString()
            if v:
                return v.strip()
            v = p.AsValueString()
            if v:
                return v.strip()
    except Exception:
        pass
    return u""


def member_keynote(elem):
    """Keynote del miembro: override de instancia, si no, el del tipo."""
    kn = _kn_from_param(elem)
    if kn:
        return kn
    try:
        et = doc.GetElement(elem.GetTypeId())
        if et is not None:
            return _kn_from_param(et)
    except Exception:
        pass
    return u""


def classify_keynote(kn):
    """'VIGA' (05 20 00.4-.9) | 'COLUMNA' (05 20 00.10-.14) | None."""
    kn = (kn or "").strip()
    if not kn.startswith("05 20 00."):
        return None
    try:
        n = int(kn.split(".")[-1])
    except (ValueError, IndexError):
        return None
    if 4 <= n <= 9:
        return "VIGA"
    if 10 <= n <= 14:
        return "COLUMNA"
    return None


def type_name(elem):
    try:
        et = doc.GetElement(elem.GetTypeId())
        return DB.Element.Name.__get__(et) or u""
    except Exception:
        return u""


def extract_profile(name):
    """'W150x24' de cualquier string con W###x###; '' si no hay."""
    m = re.search(r"W\s*(\d+)\s*[Xx]\s*(\d+)", name or "", re.IGNORECASE)
    if m:
        return "W{0}x{1}".format(m.group(1), m.group(2))
    return u""


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------
def pt_in_bbox_xy(pt, bbox):
    return (
        bbox.Min.X - TOL <= pt.X <= bbox.Max.X + TOL
        and bbox.Min.Y - TOL <= pt.Y <= bbox.Max.Y + TOL
    )


def collect():
    """Devuelve (beams, cols) ya filtrados por keynote en rango."""
    beams = []
    framing = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for e in framing:
        if not isinstance(e.Location, DB.LocationCurve):
            continue
        kn = member_keynote(e)
        if classify_keynote(kn) != "VIGA":
            continue
        beams.append({
            "elem": e, "curve": e.Location.Curve,
            "kn": kn, "perfil": extract_profile(type_name(e)),
        })

    cols = []
    columns = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for c in columns:
        kn = member_keynote(c)
        if classify_keynote(kn) != "COLUMNA":
            continue
        bbox = c.get_BoundingBox(None)
        if bbox is None:
            continue
        cols.append({
            "bbox": bbox, "kn": kn, "perfil": extract_profile(type_name(c)),
        })
    return beams, cols


def column_at(pt, cols):
    for c in cols:
        if pt_in_bbox_xy(pt, c["bbox"]):
            return c
    return None


def beam_at(pt, beams, exclude):
    for b in beams:
        if b is exclude:
            continue
        try:
            if b["curve"].Distance(pt) <= TOL:
                return b
        except Exception:
            pass
    return None


def detect(beams, cols):
    """
    conn: (tipo, csi_viga, perfil_viga, csi_sop, perfil_sop) -> count
    skipped: (csi_viga, perfil_viga) -> count   (endpoints sin soporte en rango)
    """
    conn = defaultdict(int)
    skipped = defaultdict(int)
    for b in beams:
        for i in (0, 1):
            pt = b["curve"].GetEndPoint(i)
            c = column_at(pt, cols)
            if c is not None:
                conn[("VC", b["kn"], b["perfil"], c["kn"], c["perfil"])] += 1
                continue
            other = beam_at(pt, beams, b)
            if other is not None:
                conn[("VV", b["kn"], b["perfil"], other["kn"], other["perfil"])] += 1
            else:
                skipped[(b["kn"], b["perfil"])] += 1
    return conn, skipped


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def _cell(v):
    t = u"" if v is None else u"{0}".format(v)
    if any(ch in t for ch in (u",", u'"', u"\n", u"\r")):
        t = u'"' + t.replace(u'"', u'""') + u'"'
    return t


def write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8-sig") as f:
        f.write(u",".join(_cell(h) for h in CSV_HEADERS) + u"\n")
        for r in rows:
            f.write(u",".join(_cell(x) for x in r) + u"\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    output.set_title("EstimBot - Conexiones de Acero (VV/VC por keynote)")

    if doc is None:
        forms.alert("No hay documento activo en Revit.", title="Conexiones Acero")
        return

    output.print_md("## Detectando conexiones (filtro por keynote CSI)")
    output.print_md("Rango: vigas `05 20 00.4-.9` | columnas `05 20 00.10-.14`. "
                    "Canaletas, HSS y pedestales excluidos.")

    beams, cols = collect()
    output.print_md("- Vigas en rango: **{0}**".format(len(beams)))
    output.print_md("- Columnas en rango: **{0}**".format(len(cols)))

    if not beams:
        forms.alert(
            "No hay vigas de acero en rango (keynote 05 20 00.4-.9).\n"
            "Verificar que los keynotes esten asignados en Revit.",
            title="Conexiones Acero",
        )
        return

    conn, skipped = detect(beams, cols)

    rows = []
    for key in sorted(conn.keys()):
        tipo, cv, pv, cc, pc = key
        rows.append([tipo, cv, pv, cc, pc, conn[key]])

    output.print_md("## Conexiones detectadas (VV / VC)")
    if rows:
        output.print_table(
            [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows],
            title="Conexiones por keynote",
            columns=CSV_HEADERS,
        )
        output.print_md("### Total conexiones: **{0}**".format(sum(r[5] for r in rows)))
    else:
        output.print_md("**Sin conexiones clasificadas.** Revisar keynotes de vigas/columnas.")

    if skipped:
        output.print_md("### Endpoints de viga sin soporte en rango (informativo)")
        output.print_table(
            [[k[0], k[1], n] for k, n in sorted(skipped.items())],
            columns=["csi_viga", "perfil_viga", "count"],
        )

    if not os.path.isdir(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p_ts = os.path.join(EXPORT_DIR, "C10_connections_{0}.csv".format(ts))
    p_last = os.path.join(EXPORT_DIR, "C10_connections_latest.csv")
    write_csv(p_ts, rows)
    write_csv(p_last, rows)

    total = sum(r[5] for r in rows)
    output.print_md("**CSV exportado:**")
    output.print_md("- `{0}`".format(p_ts))
    output.print_md("- `{0}` (siempre sobreescrito)".format(p_last))
    output.print_md("**Siguiente:** EstimaStruct -> modulo Conexiones -> Importar CSV pyRevit "
                    "(ahi se decide soldada/apernada -> ficha + insumos).")

    forms.alert(
        "Conexiones detectadas: {0}\nCombinaciones (filas CSV): {1}\n\nCSV: {2}".format(
            total, len(rows), p_ts
        ),
        title="Conexiones Exportadas",
    )
