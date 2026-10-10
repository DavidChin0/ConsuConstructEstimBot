# -*- coding: utf-8 -*-
"""
EstimBot - Clear Piping

Companion tool to "Generate Layout" for fast iteration: deletes the piping
elements (pipes, fittings, accessories) currently SELECTED in the Revit UI.

Why selection-based, not "wipe all piping in the model": VDA2 is a real
project file, not a disposable test model. "Generate Layout" already leaves
its newly-created elements selected right after a run
(uidoc.Selection.SetElementIds(created_ids)), so the natural iteration loop
is: run Generate Layout -> inspect result -> if wrong, click Clear Piping
(deletes exactly what was just drawn) -> adjust params -> rerun.

If nothing is selected, this script launches an interactive pick (filtered
to piping categories only) instead of silently falling back to "delete
everything" -- there is no unprompted whole-model deletion path here.
"""

import traceback

from pyrevit import DB, forms, revit, script

output = script.get_output()
output.set_title("EstimBot - Clear Piping")

doc = revit.doc
uidoc = revit.uidoc

PIPING_CATEGORIES = (
    DB.BuiltInCategory.OST_PipeCurves,
    DB.BuiltInCategory.OST_PipeFitting,
    DB.BuiltInCategory.OST_PipeAccessory,
    DB.BuiltInCategory.OST_FlexPipeCurves,
)


def clean(value):
    if value is None:
        return ""
    try:
        return str(value).replace("_x000D_", "").strip()
    except Exception:
        return ""


def element_id_value(elem_id):
    if elem_id is None:
        return None
    for attr in ("IntegerValue", "Value"):
        try:
            value = getattr(elem_id, attr)
            if value is not None:
                return int(value)
        except Exception:
            pass
    try:
        text = clean(elem_id.ToString())
        if text and text.lstrip("-").isdigit():
            return int(text)
    except Exception:
        pass
    return None


def safe_name(elem):
    if elem is None:
        return ""
    try:
        value = DB.Element.Name.__get__(elem)
        if value:
            return clean(value)
    except Exception:
        pass
    try:
        value = elem.Name
        if value:
            return clean(value)
    except Exception:
        pass
    return ""


def eid(elem_id):
    """Revit 2027 solo expone ElementId.Value (no .IntegerValue) -- helper
    con fallback chain para portabilidad entre builds."""
    for attr in ("Value", "IntegerValue", "Int32Value"):
        try:
            return int(getattr(elem_id, attr))
        except Exception:
            pass
    return int(str(elem_id))


def category_bic(elem):
    try:
        cat = elem.Category
        if cat is None:
            return None
        return DB.BuiltInCategory(eid(cat.Id))
    except Exception:
        return None


def is_piping_category(elem):
    bic = category_bic(elem)
    if bic is None:
        return False
    return bic in PIPING_CATEGORIES


class PipingSelectionFilter(DB.Selection.ISelectionFilter):
    """Restricts interactive picking to the piping categories only."""

    def AllowElement(self, elem):
        return is_piping_category(elem)

    def AllowReference(self, reference, position):
        return True


def get_selected_elements():
    selected_ids = list(uidoc.Selection.GetElementIds())
    elements = []
    for elem_id in selected_ids:
        elem = doc.GetElement(elem_id)
        if elem is not None:
            elements.append(elem)
    return elements


def pick_piping_elements():
    try:
        refs = uidoc.Selection.PickObjects(
            DB.Selection.ObjectType.Element,
            PipingSelectionFilter(),
            "Selecciona tuberias/fittings/accesorios a borrar (Finish/Enter para terminar)",
        )
    except Exception:
        # Usuario canceló el pick (Esc) -- no es un error, es una salida limpia.
        return []
    elements = []
    for ref in refs or []:
        elem = doc.GetElement(ref.ElementId)
        if elem is not None:
            elements.append(elem)
    return elements


def build_report(kept, skipped_non_piping):
    lines = []
    lines.append("## Clear Piping")
    lines.append("- Elementos de plomeria a borrar: `{0}`".format(len(kept)))
    if skipped_non_piping:
        lines.append("- Ignorados (no son categoria de plomeria): `{0}`".format(len(skipped_non_piping)))
        for elem in skipped_non_piping[:20]:
            lines.append(
                "  - `{0}` (id={1}, categoria={2})".format(
                    safe_name(elem) or "Elemento",
                    element_id_value(getattr(elem, "Id", None)),
                    getattr(getattr(elem, "Category", None), "Name", "?"),
                )
            )
    lines.append("### A borrar")
    by_category = {}
    for elem in kept:
        bic = category_bic(elem)
        key = str(bic) if bic is not None else "?"
        by_category.setdefault(key, 0)
        by_category[key] += 1
    for key, count in sorted(by_category.items()):
        lines.append("- `{0}`: {1}".format(key, count))
    return "\n".join(lines)


def main():
    if doc is None or uidoc is None:
        forms.alert("No hay documento activo en Revit.", title="Clear Piping")
        return

    elements = get_selected_elements()
    picked_now = False
    if not elements:
        picked_now = True
        elements = pick_piping_elements()

    if not elements:
        forms.alert(
            "No hay elementos seleccionados ni pickeados. Nada que borrar.",
            title="Clear Piping",
        )
        return

    kept = [elem for elem in elements if is_piping_category(elem)]
    skipped_non_piping = [elem for elem in elements if not is_piping_category(elem)]

    if not kept:
        output.print_md("## Clear Piping")
        output.print_md("- Ningun elemento de la seleccion es de categoria de plomeria (pipe/fitting/accessory).")
        output.print_md("- No se borro nada.")
        forms.alert(
            "Nada que borrar: la seleccion no tiene tuberias/fittings/accesorios.",
            title="Clear Piping",
        )
        return

    output.print_md(build_report(kept, skipped_non_piping))

    source_label = "elementos pickeados" if picked_now else "seleccion actual"
    if not forms.alert(
        "Esto va a BORRAR {0} elemento(s) de plomeria ({1}).\nContinuar?".format(len(kept), source_label),
        title="Clear Piping",
        ok=True,
        cancel=True,
    ):
        return

    # Nunca borrar iterando una coleccion viva -- ya tenemos lista estatica (kept).
    ids_to_delete = []
    for elem in kept:
        try:
            ids_to_delete.append(elem.Id)
        except Exception:
            continue

    deleted_count = 0
    failed = []
    t = DB.Transaction(doc, "EstimBot - Clear Piping")
    t.Start()
    try:
        for elem_id in ids_to_delete:
            try:
                result = doc.Delete(elem_id)
                # doc.Delete puede borrar elementos dependientes tambien (fittings
                # huerfanos, etc.) -- result es un ICollection<ElementId>, no un bool.
                if result is not None:
                    deleted_count += 1
                else:
                    failed.append(element_id_value(elem_id))
            except Exception as ex:
                failed.append("{0}: {1}".format(element_id_value(elem_id), ex))
        t.Commit()
    except Exception:
        try:
            t.RollBack()
        except Exception:
            pass
        raise

    output.print_md("## Resultado")
    output.print_md("- Elementos procesados: `{0}`".format(len(ids_to_delete)))
    output.print_md("- Borrados OK: `{0}`".format(deleted_count))
    output.print_md("- Fallos: `{0}`".format(len(failed)))
    if failed:
        output.print_md("### Fallos")
        for item in failed:
            output.print_md("- {0}".format(item))

    forms.alert(
        "Borrado listo.\nProcesados: {0}\nOK: {1}\nFallos: {2}".format(
            len(ids_to_delete),
            deleted_count,
            len(failed),
        ),
        title="Clear Piping",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        tb = traceback.format_exc()
        output.print_md("## Error")
        output.print_md("```text")
        output.print_md(tb)
        output.print_md("```")
        forms.alert("Clear Piping fallo.\n{0}".format(ex), title="Clear Piping")
