"""Crea/duplica los tipos de columna de concreto rectangular que el catálogo
paramétrico (`M_Concrete-Rectangular-Column`) no trae de fábrica -- Revit
carga esta familia con 2-3 tipos genéricos (300x450mm, etc), pero
EstimaStruct necesita un tipo por marca real de obra (R1..R9, P1..P7), cada
uno con su Width("b")/Depth("h") real, CSI keynote y Type Mark.

Descubierto en vivo 2026-08-02 (goal-20147/20173/20149): a diferencia de los
perfiles de acero AISC/HSS (catálogo de tipos con nombre estándar, ver
`revit_sync_marks_from_reference_snippet.py` pass4), la columna de concreto
rectangular es una familia PARAMÉTRICA -- no hay "tipo correcto" que cargar
de una librería, hay que crear los tipos a mano con las dimensiones reales
del proyecto de referencia.

Params confirmados por inspección directa (`LookupParameter`, no
BuiltInParameter -- son parámetros de familia, no de sistema):
- "b" = Width (ancho), Double, editable
- "h" = Depth (peralte), Double, editable
Unidad interna Revit = pies. cm -> pies: cm / 30.48.

Uso: pegar CODE en execute_revit_code con el documento destino abierto y
titulado "estimastruct_blank_template" (o ajustar TARGET_TITLE), o llamar
build_code(target_title, rows) con `rows` = lista de
(type_name, width_cm, depth_cm, csi_keynote, marca).

Corrida real 2026-08-02: 17/17 tipos creados (R1-R9, P1-P7, GAP-01
"Existente 20x40cm") contra Valle de Angeles como fuente de las dimensiones
reales.
"""
CODE_TEMPLATE = r'''
import json
import Autodesk.Revit.DB as DB

app = __revit__.Application
target = None
for d in app.Documents:
    if d.Title == "TARGET_TITLE_PLACEHOLDER":
        target = d

base = None
for t in DB.FilteredElementCollector(target).OfCategory(DB.BuiltInCategory.OST_StructuralColumns).WhereElementIsElementType().ToElements():
    if getattr(t, "FamilyName", None) == "M_Concrete-Rectangular-Column":
        base = t
        break

KEY_PARAM = DB.BuiltInParameter.KEYNOTE_PARAM
TYPE_MARK = DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
CM = 1.0 / 30.48

rows = ROWS_PLACEHOLDER

results = []
for name, w_cm, h_cm, kn, mk in rows:
    try:
        nt = base.Duplicate(name)
        pb = nt.LookupParameter("b")
        ph = nt.LookupParameter("h")
        if pb:
            pb.Set(w_cm * CM)
        if ph:
            ph.Set(h_cm * CM)
        pk = nt.get_Parameter(KEY_PARAM)
        if pk:
            pk.Set(kn)
        pm = nt.get_Parameter(TYPE_MARK)
        if pm:
            pm.Set(mk)
        results.append({"name": name, "ok": True})
    except Exception as ex:
        results.append({"name": name, "ok": False, "error": str(ex)})

print(json.dumps(results))
'''

DEFAULT_ROWS = [
    ("R1 15x15cm", 15, 15, "03 31 00.1", "R-1"),
    ("R2 20x20cm", 20, 20, "03 31 00.2", "R-2"),
    ("R3 20x30cm", 20, 30, "03 31 00.3", "R-3"),
    ("R4 20x20cm b", 20, 20, "03 31 00.4", "R-4"),
    ("R5 35x35cm", 35, 35, "03 31 00.5", "R-5"),
    ("R6 60x60cm", 60, 60, "03 31 00.6", "R-6"),
    ("R7 25x25cm", 25, 25, "03 31 00.13", "R-7"),
    ("R8 30x30cm", 30, 30, "03 31 00.14", "R-8"),
    ("R9 40x40cm", 40, 40, "03 31 00.15", "R-9"),
    ("P1 40x40cm", 40, 40, "03 31 00.20", "P-1"),
    ("P2 50x50cm", 50, 50, "03 31 00.21", "P-2"),
    ("P3 60x60cm", 60, 60, "03 31 00.22", "P-3"),
    ("P4 70x70cm", 70, 70, "03 31 00.23", "P-4"),
    ("P5 30x30cm", 30, 30, "03 31 00.24", "P-5"),
    ("P6 35x35cm", 35, 35, "03 31 00.25", "P-6"),
    ("P7 40x40cm", 40, 40, "03 31 00.27", "P-7"),
    ("Existente 20x40cm", 20, 40, "02 01 00", "GAP-01"),
]


def build_code(target_title, rows=None):
    rows = rows or DEFAULT_ROWS
    return (CODE_TEMPLATE
            .replace("TARGET_TITLE_PLACEHOLDER", target_title)
            .replace("ROWS_PLACEHOLDER", repr(rows)))
