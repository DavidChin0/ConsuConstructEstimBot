# -*- coding: utf-8 -*-
"""
EstimBot - Borrar MEP Generado

Borra todo el contenido MEP generado por "Generate Layout" (Plumbing.panel)
y "Conduit by Ciruit" (Electrical.panel): pipes, pipe fittings, pipe
accessories, conduit, conduit fittings, y las cajas de fitting auto-colocadas
(identificadas por nombre de familia, NO por categoria completa, para no
borrar switches/tomas/paneles reales).

No crea geometria nueva. Solo audita (CSV) y borra.
"""

import io
import os
from datetime import datetime

from pyrevit import revit, DB, forms, script


doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
output.set_title("EstimBot - Borrar MEP Generado")

EXPORTS_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS"

CATEGORIES_TO_DELETE = [
    DB.BuiltInCategory.OST_PipeCurves,
    DB.BuiltInCategory.OST_PipeFitting,
    DB.BuiltInCategory.OST_PipeAccessory,
    DB.BuiltInCategory.OST_Conduit,
    DB.BuiltInCategory.OST_ConduitFitting,
]

# Palabras que identifican una caja de fitting (auto-colocada por los botones
# de generacion), copiado/adaptado de Conduit by Ciruit.pushbutton/script.py
BOX_WORDS = ["box", "caja", "junction", "registro", "conexiones", "conexion", "device box", "pull box"]

# Palabras que descartan un elemento aunque contenga una box-word (son
# dispositivos reales, no cajas de fitting auto-colocadas).
EXCLUDED_WORDS = [
    "switch",
    "interruptor",
    "tomacorriente",
    "receptacle",
    "outlet",
    "duplex",
    "gfci",
    "lighting fixture",
    "light fixture",
    "luminaire",
    "luminaria",
    "panel",
    "tablero",
]


def safe_name(elem):
    if elem is None:
        return ""
    try:
        value = DB.Element.Name.__get__(elem)
        if value:
            return value
    except Exception:
        pass
    try:
        value = elem.Name
        if value:
            return value
    except Exception:
        pass
    return ""


def get_param_string(elem, built_in_parameter):
    try:
        param = elem.get_Parameter(built_in_parameter)
        if param:
            value = param.AsString()
            if value:
                return value
            value = param.AsValueString()
            if value:
                return value
    except Exception:
        pass
    return ""


def symbol_display_name(symbol):
    family = ""
    try:
        family = symbol.FamilyName
    except Exception:
        try:
            family = safe_name(symbol.Family)
        except Exception:
            family = ""

    type_name = get_param_string(symbol, DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    if not type_name:
        type_name = safe_name(symbol)

    if family and type_name:
        return "{0} : {1}".format(family, type_name)
    return family or type_name or ""


def is_box_symbol_match(text):
    """Misma logica que Conduit by Ciruit.pushbutton/script.py: contiene una
    box-word y NO contiene ninguna palabra de dispositivo real."""
    for token in EXCLUDED_WORDS:
        if token in text:
            return False
    return any([word in text for word in BOX_WORDS])


def find_fitting_box_instances():
    """Recolecta instancias de FamilySymbol cuyo simbolo matchee la logica
    de 'caja de fitting' (no por categoria completa, por nombre)."""
    matches = []
    try:
        instances = DB.FilteredElementCollector(doc) \
            .OfClass(DB.FamilyInstance) \
            .WhereElementIsNotElementType() \
            .ToElements()
    except Exception:
        instances = []

    for inst in instances:
        try:
            symbol = inst.Symbol
        except Exception:
            symbol = None
        if symbol is None:
            continue
        try:
            text = symbol_display_name(symbol).lower()
        except Exception:
            text = ""
        if not text:
            continue
        if is_box_symbol_match(text):
            matches.append(inst)
    return matches


def category_name(elem):
    try:
        if elem.Category:
            return elem.Category.Name
    except Exception:
        pass
    return ""


def family_name(elem):
    try:
        return elem.Symbol.FamilyName
    except Exception:
        pass
    try:
        return elem.Symbol.Family.Name
    except Exception:
        pass
    return ""


def type_name(elem):
    try:
        return safe_name(doc.GetElement(elem.GetTypeId()))
    except Exception:
        pass
    try:
        return safe_name(elem.Symbol)
    except Exception:
        pass
    return ""


def element_id_value(element_id):
    if element_id is None:
        return None
    try:
        return element_id.IntegerValue
    except Exception:
        pass
    try:
        return element_id.Value
    except Exception:
        pass
    return None


def escape_csv_field(text):
    text = "" if text is None else str(text)
    text = text.replace('"', '""')
    if "," in text or '"' in text or "\n" in text:
        text = '"{0}"'.format(text)
    return text


def write_audit_csv(rows):
    if not os.path.isdir(EXPORTS_DIR):
        try:
            os.makedirs(EXPORTS_DIR)
        except Exception:
            pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = "borrado_mep_{0}.csv".format(timestamp)
    path = os.path.join(EXPORTS_DIR, filename)

    try:
        handle = io.open(path, "w", encoding="utf-8")
    except Exception as ex:
        output.print_md("- **No se pudo escribir el CSV de auditoria:** `{0}`".format(ex))
        return None

    try:
        handle.write(u"element_id,categoria,familia,tipo\n")
        for row in rows:
            line = u",".join([
                escape_csv_field(row.get("element_id", "")),
                escape_csv_field(row.get("categoria", "")),
                escape_csv_field(row.get("familia", "")),
                escape_csv_field(row.get("tipo", "")),
            ])
            handle.write(line + u"\n")
    finally:
        handle.close()

    return path


def collect_candidates():
    candidates = {}

    for bic in CATEGORIES_TO_DELETE:
        try:
            collector = DB.FilteredElementCollector(doc) \
                .OfCategory(bic) \
                .WhereElementIsNotElementType() \
                .ToElements()
        except Exception:
            collector = []
        for elem in collector:
            try:
                eid = element_id_value(elem.Id)
            except Exception:
                eid = None
            if eid is None:
                continue
            candidates[eid] = elem

    for elem in find_fitting_box_instances():
        try:
            eid = element_id_value(elem.Id)
        except Exception:
            eid = None
        if eid is None:
            continue
        candidates[eid] = elem

    return candidates


def build_stats_by_category(candidates):
    stats = {}
    for elem in candidates.values():
        cat = category_name(elem) or "Sin categoria"
        stats[cat] = stats.get(cat, 0) + 1
    return stats


def main():
    candidates = collect_candidates()

    if not candidates:
        forms.alert("No hay elementos MEP generado para borrar.")
        return

    rows = []
    for eid, elem in candidates.items():
        try:
            row = {
                "element_id": eid,
                "categoria": category_name(elem),
                "familia": family_name(elem),
                "tipo": type_name(elem),
            }
        except Exception:
            row = {"element_id": eid, "categoria": "", "familia": "", "tipo": ""}
        rows.append(row)

    csv_path = write_audit_csv(rows)

    stats_by_category = build_stats_by_category(candidates)
    total = len(candidates)

    summary_lines = ["Se van a borrar {0} elementos MEP generado:".format(total)]
    for cat in sorted(stats_by_category.keys()):
        summary_lines.append("- {0}: {1}".format(cat, stats_by_category[cat]))
    summary_lines.append("")
    summary_lines.append("Auditoria CSV: {0}".format(csv_path or "no se pudo escribir"))
    summary_lines.append("")
    summary_lines.append("Continuar?")

    answer = forms.alert("\n".join(summary_lines), yes=True, no=True)
    if not answer:
        output.print_md("## Borrar MEP Generado - cancelado por el usuario")
        return

    deleted_count = 0
    failed_count = 0
    deleted_by_category = {}

    t = DB.Transaction(doc, "Borrar MEP Generado")
    t.Start()
    try:
        for eid, elem in candidates.items():
            cat = category_name(elem) or "Sin categoria"
            try:
                doc.Delete(elem.Id)
                deleted_count += 1
                deleted_by_category[cat] = deleted_by_category.get(cat, 0) + 1
            except Exception:
                # El elemento puede haber sido borrado en cascada por
                # dependencia (p.ej. un fitting al borrar su pipe). Toleramos
                # el fallo individual y seguimos con el resto.
                failed_count += 1
        t.Commit()
    except Exception as ex:
        t.RollBack()
        forms.alert("Error borrando MEP generado:\n{0}".format(ex))
        return

    doc.Save()

    output.print_md("## Borrar MEP Generado")
    output.print_md("- Candidatos encontrados: `{0}`".format(total))
    output.print_md("- Elementos borrados: `{0}`".format(deleted_count))
    output.print_md("- Fallos/ya borrados por cascada: `{0}`".format(failed_count))
    output.print_md("- Auditoria CSV: `{0}`".format(csv_path or "no se pudo escribir"))
    output.print_md("### Borrados por categoria")
    for cat in sorted(deleted_by_category.keys()):
        output.print_md("- {0}: `{1}`".format(cat, deleted_by_category[cat]))

    result_lines = [
        "Borrado MEP Generado terminado.",
        "",
        "Elementos borrados: {0}".format(deleted_count),
        "Fallos/ya borrados por cascada: {0}".format(failed_count),
        "",
        "Auditoria CSV:",
        csv_path or "no se pudo escribir",
    ]
    forms.alert("\n".join(result_lines))


main()
