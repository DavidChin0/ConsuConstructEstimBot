# -*- coding: utf-8 -*-
"""
EstimBot - Autodim by Axis

Clean IronPython implementation for pyRevit.
Creates one aligned dimension per grid direction group in each selected view.
"""

from pyrevit import DB, forms, revit, script

import math


doc = revit.doc
output = script.get_output()
output.set_title("EstimBot - Autodim by Axis")

DIMENSION_OFFSET_FT = 5.0
PARALLEL_TOLERANCE = 0.98

ALLOWED_VIEW_TYPES = set([
    "FloorPlan",
    "CeilingPlan",
    "Section",
    "Elevation",
    "Detail",
    "DraftingView",
    "EngineeringPlan",
    "StructuralPlan",
    "AreaPlan",
])


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


def element_id_value(elem_id):
    if elem_id is None:
        return None
    for attr in ("Value", "IntegerValue"):
        try:
            value = getattr(elem_id, attr)
            if value is not None:
                return int(value)
        except Exception:
            pass
    try:
        return int(elem_id)
    except Exception:
        return None


def view_type_name(view):
    try:
        return view.ViewType.ToString()
    except Exception:
        try:
            return str(view.ViewType)
        except Exception:
            return ""


def is_valid_view(view):
    if view is None:
        return False, "No hay vista activa."
    if getattr(view, "IsTemplate", False):
        return False, "La vista activa es una plantilla."
    vt_name = view_type_name(view)
    if vt_name not in ALLOWED_VIEW_TYPES:
        return False, "No se soporta en esta vista: {0}".format(vt_name or "desconocida")
    return True, ""


class ViewOption(object):
    def __init__(self, view):
        self.view = view
        self.label = "{0} | {1} | Id {2}".format(
            clean(safe_name(view)),
            view_type_name(view),
            element_id_value(view.Id),
        )

    def __str__(self):
        return self.label


def choose_views(doc):
    options = []
    collector = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
    for view in collector:
        if view is None:
            continue
        valid, _ = is_valid_view(view)
        if valid:
            options.append(ViewOption(view))

    options.sort(key=lambda item: item.label.lower())
    if not options:
        return []

    selected = forms.SelectFromList.show(
        options,
        multiselect=True,
        name_attr="label",
        title="Seleccionar vistas para Autodim by Axis",
        button_name="Procesar vistas",
    )
    if not selected:
        return []
    if not isinstance(selected, list):
        selected = [selected]
    return [item.view for item in selected if item and item.view]


def get_view_basis(view):
    return view.RightDirection.Normalize(), view.UpDirection.Normalize()


def point_to_uv(point, right, up):
    return (point.DotProduct(right), point.DotProduct(up))


def uv_to_xyz(u, v, right, up):
    return right.Multiply(u).Add(up.Multiply(v))


def uv_add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def uv_scale(a, factor):
    return (a[0] * factor, a[1] * factor)


def uv_dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def uv_len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


def uv_normalize(a):
    length = uv_len(a)
    if length <= 1e-9:
        return None
    return (a[0] / length, a[1] / length)


def uv_perp(a):
    return (-a[1], a[0])


def curve_direction_uv(curve, right, up):
    try:
        start = curve.GetEndPoint(0)
        end = curve.GetEndPoint(1)
        delta = end.Subtract(start)
        uv = point_to_uv(delta, right, up)
        return uv_normalize(uv)
    except Exception:
        return None


def get_grid_curve(grid, view):
    try:
        curves = grid.GetCurvesInView(DB.DatumExtentType.ViewSpecific, view)
        if curves:
            for curve in curves:
                if isinstance(curve, DB.Line):
                    return curve
    except Exception:
        pass

    try:
        curve = grid.Curve
        if isinstance(curve, DB.Line):
            return curve
    except Exception:
        pass

    return None


def get_grid_reference(grid, view):
    opt = DB.Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = True
    opt.View = view

    try:
        geometry = grid.get_Geometry(opt)
    except Exception:
        geometry = None

    if geometry is not None:
        for obj in geometry:
            if isinstance(obj, DB.Line):
                try:
                    ref = obj.Reference
                    if ref is not None:
                        return ref
                except Exception:
                    pass

    try:
        curve = grid.Curve
        if curve is not None:
            return curve.Reference
    except Exception:
        pass

    return None


def collect_grid_items(view, doc):
    right, up = get_view_basis(view)
    grids = []
    skipped = []

    collector = (
        DB.FilteredElementCollector(doc, view.Id)
        .OfClass(DB.Grid)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    for grid in collector:
        if grid is None:
            continue

        grid_name = clean(getattr(grid, "Name", ""))
        curve = get_grid_curve(grid, view)
        if curve is None:
            skipped.append({"name": grid_name, "reason": "Sin curva visible"})
            continue

        if not isinstance(curve, DB.Line):
            skipped.append({"name": grid_name, "reason": "Grid curvo no soportado"})
            continue

        direction = curve_direction_uv(curve, right, up)
        if direction is None:
            skipped.append({"name": grid_name, "reason": "Sin direccion util"})
            continue

        center_point = None
        try:
            center_point = curve.Evaluate(0.5, True)
        except Exception:
            center_point = None
        if center_point is None:
            skipped.append({"name": grid_name, "reason": "Sin punto medio util"})
            continue

        ref = get_grid_reference(grid, view)
        if ref is None:
            skipped.append({"name": grid_name, "reason": "Sin referencia de geometria"})
            continue

        grids.append({
            "name": grid_name,
            "curve": curve,
            "center": center_point,
            "direction": direction,
            "ref": ref,
        })

    return grids, skipped


def group_parallel_grids(items):
    groups = []
    for item in items:
        placed = False
        for group in groups:
            if abs(uv_dot(group["base_dir"], item["direction"])) >= PARALLEL_TOLERANCE:
                group["items"].append(item)
                placed = True
                break
        if not placed:
            groups.append({
                "base_dir": item["direction"],
                "items": [item],
            })
    return groups


def sort_group_items(view, group):
    right, up = get_view_basis(view)
    base_dir = group["base_dir"]
    dim_dir = uv_perp(base_dir)
    dim_dir = uv_normalize(dim_dir)
    if dim_dir is None:
        return None, None, None

    centers_uv = []
    for item in group["items"]:
        centers_uv.append(point_to_uv(item["center"], right, up))

    ordered = []
    for idx, item in enumerate(group["items"]):
        scalar = uv_dot(centers_uv[idx], dim_dir)
        ordered.append((scalar, item))
    ordered.sort(key=lambda row: row[0])

    centroid = (
        sum(pt[0] for pt in centers_uv) / float(len(centers_uv)),
        sum(pt[1] for pt in centers_uv) / float(len(centers_uv)),
    )

    return ordered, dim_dir, centroid


def build_dimension_line(view, ordered, dim_dir, centroid, base_dir, side_sign):
    right, up = get_view_basis(view)
    scalars = [row[0] for row in ordered]
    min_scalar = min(scalars)
    max_scalar = max(scalars)
    margin = max(1.0, (max_scalar - min_scalar) * 0.15)

    offset_dir = uv_normalize(base_dir)
    if offset_dir is None:
        offset_dir = base_dir

    base_uv = uv_add(centroid, uv_scale(offset_dir, DIMENSION_OFFSET_FT * side_sign))
    start_uv = uv_add(base_uv, uv_scale(dim_dir, min_scalar - margin))
    end_uv = uv_add(base_uv, uv_scale(dim_dir, max_scalar + margin))

    start = uv_to_xyz(start_uv[0], start_uv[1], right, up)
    end = uv_to_xyz(end_uv[0], end_uv[1], right, up)
    return DB.Line.CreateBound(start, end)


def create_dimension(doc, view, group, side_sign):
    ordered, dim_dir, centroid = sort_group_items(view, group)
    if ordered is None or dim_dir is None or centroid is None:
        return None

    references = DB.ReferenceArray()
    for _, item in ordered:
        references.Append(item["ref"])

    dim_line = build_dimension_line(view, ordered, dim_dir, centroid, group["base_dir"], side_sign)
    return doc.Create.NewDimension(view, dim_line, references)


def print_skipped(skipped):
    if not skipped:
        return
    rows = []
    for item in skipped[:100]:
        rows.append([item.get("name", ""), item.get("reason", "")])
    output.print_md("## Omitidos")
    output.print_table(table_data=rows, columns=["Grid", "Motivo"])


def main():
    if doc is None:
        forms.alert("No hay documento activo.", title="Autodim by Axis")
        return

    selected_views = choose_views(doc)
    if not selected_views:
        forms.alert("No se seleccionaron vistas.", title="Autodim by Axis")
        return

    output.print_md("# Autodim by Axis")
    output.print_md("Vistas seleccionadas: **{0}**".format(len(selected_views)))

    report_rows = []
    skipped_all = []
    total_created = 0
    errors = []

    with revit.Transaction("EstimBot - Autodim by Axis"):
        for view in selected_views:
            items, skipped = collect_grid_items(view, doc)
            skipped_all.extend(skipped)
            rows_before = len(report_rows)

            if len(items) < 2:
                report_rows.append([
                    clean(view.Name),
                    "n/a",
                    len(items),
                    0,
                    "Sin suficientes grids",
                ])
                continue

            groups = group_parallel_grids(items)
            created_in_view = 0

            for idx, group in enumerate(groups):
                if len(group["items"]) < 2:
                    continue

                created_here = 0
                side_errors = []
                for side_sign in (1, -1):
                    try:
                        dim = create_dimension(doc, view, group, side_sign)
                        if dim:
                            created_here += 1
                            total_created += 1
                    except Exception as ex:
                        side_errors.append(str(ex))
                        errors.append("{0}: {1}".format(clean(view.Name), ex))

                created_in_view += created_here
                if created_here:
                    reason = ""
                elif side_errors:
                    reason = side_errors[0]
                else:
                    reason = "No se pudo crear la dimension"

                report_rows.append([
                    clean(view.Name),
                    "grupo {0}".format(idx + 1),
                    len(group["items"]),
                    created_here,
                    reason,
                ])

            if len(report_rows) == rows_before:
                report_rows.append([
                    clean(view.Name),
                    "n/a",
                    len(items),
                    0,
                    "Sin grupos validos",
                ])

    output.print_md("## Resultado")
    if report_rows:
        output.print_table(
            table_data=report_rows,
            columns=["Vista", "Grupo", "Grid(s)", "Creadas", "Motivo"],
        )
    else:
        output.print_md("Sin resultados para mostrar.")
    output.print_md("- Dimensiones creadas total: **{0}**".format(total_created))
    print_skipped(skipped_all)

    if errors:
        output.print_md("## Errores")
        for err in errors[:30]:
            output.print_md("- `{0}`".format(err))
        forms.alert("Se produjo un error en una o mas vistas.", title="Autodim by Axis")
        return

    forms.alert(
        "Autodim ejecutado en {0} vista(s). Dimensiones creadas: {1}".format(
            len(selected_views),
            total_created,
        ),
        title="Autodim by Axis",
    )


if __name__ == "__main__":
    main()
