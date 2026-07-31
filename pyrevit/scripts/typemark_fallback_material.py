# MCP_NO_TXN
# -*- coding: utf-8 -*-
"""Fallback de Type Mark por MATERIAL PRINCIPAL para tipos SIN_KEYNOTE.
Decision Director 2026-06-12:
  - El tag SIEMPRE es un type_mark REAL de EstimaStruct (nunca inventado).
  - Se usa el material PRINCIPAL del nombre (identidad del muro, no el primer
    literal: pintura/acabado NO identifica).
  - Se permite REPETIR (6 muros iguales de bloque-4" => STR-05 todos). Honesto.
  - Solo toca tipos SIN_KEYNOTE con Type Mark VACIO (no pisa W10/F01/AF04/27...).
Correr via MCP execute_revit_code (marcador MCP_NO_TXN => transaccion propia).
PRIORITY mapea material->type_mark real validado contra el inventario del
presupuesto 'Apartamento Valle de Angeles' (55d932d2-...). Ajustar PRIORITY si
cambia el presupuesto activo."""
import re
from pyrevit import revit, DB
doc = revit.doc

# material principal (orden = importancia identitaria) -> (label, type_mark REAL EstimaStruct, regex)
PRIORITY = [
    ('Bloque 8"',      'STR-07', r'bloque de 8|8"|20cm'),
    ('Bloque 6"',      'STR-06', r'bloque de 6|6"|15cm'),
    ('Bloque 4"',      'STR-05', r'bloque de 4|4"|10cm'),
    ('Ladrillo Rafon', 'STR-09', r'ladrillo'),
    ('Plycem',         'WS-04',  r'plycem'),
    ('Tablayeso',      'WS-01',  r'tablayeso'),
    ('DensGlass',      'WS-03',  r'densglass'),
    ('Concreto',       'CON-01', r'\bconc'),
    ('Fachaleta',      'STR-11', r'fachaleta|fach|enchape'),
    ('Ceramica',       'CER-05', r'ceramica'),
    ('WPC Ext',        'COA9',   r'wpc ext|wpcext|wpext|extwpc'),
    ('WPC Int',        'COA8',   r'wpc int|wpcint|wpc inte'),
    ('WPC',            'COA8',   r'wpc'),
    ('Steel Framing',  'SF-01',  r'steelf|steel'),
    ('Repello',        'COA01',  r'repello'),
    ('Pulido',         'COA02',  r'pulido'),
    ('Vinyl',          'FL-01',  r'vinyl|vynil|pvc'),
    ('Pintura',        'COA06',  r'pint'),
    ('Aislante',       'AT-06',  r'aislante'),
]

INVENTED = set(["BLK","CONC","PAINT","GYP","CER","WPC","PLYCEM","BRICK","WOOD","GLASS","STEEL","PVC"])

CATS = [
    DB.BuiltInCategory.OST_StructuralFraming, DB.BuiltInCategory.OST_StructuralColumns,
    DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_Floors,
    DB.BuiltInCategory.OST_Ceilings, DB.BuiltInCategory.OST_Doors,
    DB.BuiltInCategory.OST_Windows, DB.BuiltInCategory.OST_Walls,
]


def principal(nm):
    low = (nm or "").lower()
    for label, tag, rx in PRIORITY:
        if re.search(rx, low):
            return label, tag
    return None, None


class _Swallow(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, acc):
        for f in acc.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                acc.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


escritos, revertidos, sin_material = [], 0, []
t = DB.Transaction(doc, "TM fallback material principal (SIN_KEYNOTE)")
fho = t.GetFailureHandlingOptions()
fho.SetFailuresPreprocessor(_Swallow())
t.SetFailureHandlingOptions(fho)
t.Start()
try:
    for bic in CATS:
        for typ in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType():
            p_kn = typ.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
            kn = (p_kn.AsString() or "").strip() if p_kn else ""
            if kn:
                continue  # solo SIN_KEYNOTE
            p_tm = typ.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
            if p_tm is None or p_tm.IsReadOnly:
                continue
            cur = p_tm.AsString() or ""
            if cur in INVENTED:        # limpiar inventado previo
                p_tm.Set(""); cur = ""; revertidos += 1
            if cur:                    # solo TM vacio (no pisa placeholders W10/F01/27)
                continue
            p_name = typ.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
            nm = p_name.AsString() if p_name else "?"
            label, tag = principal(nm)
            if not tag:
                sin_material.append(nm)
                continue
            p_tm.Set(tag)
            escritos.append((nm, tag, label))
    t.Commit()
except Exception:
    t.RollBack(); raise

print("inventados limpiados:", revertidos)
print("ESCRITOS (material principal -> tag real):", len(escritos))
for nm, tag, label in escritos:
    print(u"  {} -> {} ({})".format(nm, tag, label))
print("SIN material reconocible (manual):", len(sin_material))
for nm in sin_material:
    print(u"  {}".format(nm))
