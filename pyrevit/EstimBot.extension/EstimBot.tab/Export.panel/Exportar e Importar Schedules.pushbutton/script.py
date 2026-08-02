# -*- coding: utf-8 -*-
"""
PYR_S5 - Export Revit schedules to one CSV for EstimBot.

IronPython/pyRevit version. Exports schedules whose names start with:
- two digits: 01..99
- T + two digits: T01..T99

Output:
D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules\schedules_YYYYMMDD_HHMMSS.csv
"""

from pyrevit import revit, DB, forms, script

import os
import re
import json
from datetime import datetime

from System.IO import StreamWriter
from System.Text import UTF8Encoding
from System.Net import WebClient


doc = revit.doc
output = script.get_output()
output.set_title("EstimBot - Exportar Schedules")

EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"

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


def import_to_estimastruct(csv_path):
    """Ofrece importar el CSV recien escrito a una obra de EstimaStruct via el
    backend FastAPI (:8002). No crashea si el backend no responde."""
    if not csv_path or not os.path.isfile(csv_path):
        return

    quiere = forms.alert(
        "¿Importar estas cantidades a una obra de EstimaStruct ahora?\n\n"
        "El CSV ya quedo guardado en disco:\n{0}".format(csv_path),
        title="EstimBot - Importar a EstimaStruct",
        yes=True, no=True
    )
    if not quiere:
        return

    # Listar obras
    try:
        obras = _http_get_json(ESTIMASTRUCT_API + "/presupuestos")
    except Exception as e:
        forms.alert(
            "No se pudo conectar a EstimaStruct (:8002). "
            "¿Esta corriendo el backend? Podes importar manualmente desde la web.\n\n"
            "Detalle: {0}".format(str(e)),
            title="EstimBot - Error de conexion"
        )
        return

    nombre_a_id = {}
    for o in (obras or []):
        try:
            if o.get("es_template"):
                continue
            nombre = (o.get("nombre") or "(sin nombre)")
            try:
                nombre = str(nombre).strip()
            except Exception:
                nombre = "(sin nombre)"
            oid = o.get("id")
            if oid is None:
                continue
            label = nombre
            n = 2
            while label in nombre_a_id:
                label = "{0} ({1})".format(nombre, n)
                n += 1
            nombre_a_id[label] = oid
        except Exception:
            continue

    if not nombre_a_id:
        forms.alert(
            "El backend respondio pero no hay obras disponibles para importar.",
            title="EstimBot - Sin obras"
        )
        return

    seleccion = forms.SelectFromList.show(
        sorted(nombre_a_id.keys()),
        title="Selecciona la obra EstimaStruct",
        button_name="Importar cantidades",
        multiselect=False
    )
    if not seleccion:
        return

    pid = nombre_a_id.get(seleccion)
    if pid is None:
        return

    url = "{0}/revit-mcp/obras/{1}/import-quantities".format(ESTIMASTRUCT_API, pid)
    try:
        resp = _http_post_json(url, {"csv_path": csv_path})
    except Exception as e:
        forms.alert(
            "No se pudo importar a EstimaStruct (:8002). "
            "¿Esta corriendo el backend? Podes importar manualmente desde la web.\n\n"
            "Obra: {0}\nDetalle: {1}".format(seleccion, str(e)),
            title="EstimBot - Error de importacion"
        )
        return

    salida = ""
    try:
        salida = resp.get("output") or ""
    except Exception:
        salida = str(resp)
    forms.alert(
        "Importacion a '{0}' completada.\n\n{1}".format(seleccion, salida),
        title="EstimBot - Importacion EstimaStruct"
    )


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


def should_export(name):
    if not name:
        return False
    n = name.strip()
    if re.match(r"^\d{2}", n):
        return True
    if re.match(r"^T\d{2}", n, re.IGNORECASE):
        return True
    return False


def csv_escape(value):
    if value is None:
        text = ""
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    must_quote = "," in text or '"' in text or "\n" in text
    text = text.replace('"', '""')
    if must_quote:
        return '"' + text + '"'
    return text


def csv_line(values):
    return ",".join([csv_escape(value) for value in values])


def read_schedule(view_schedule):
    rows = []
    try:
        section = view_schedule.GetTableData().GetSectionData(DB.SectionType.Body)
        for row_idx in range(section.NumberOfRows):
            row = []
            for col_idx in range(section.NumberOfColumns):
                try:
                    cell = view_schedule.GetCellText(DB.SectionType.Body, row_idx, col_idx)
                    row.append(cell or "")
                except Exception:
                    row.append("")
            rows.append(row)
    except Exception as ex:
        rows.append(["ERROR: {0}".format(ex)])
    return rows


def has_keynote_header(headers):
    for header in headers:
        if "keynote" in (header or "").lower():
            return True
    return False


# --- Categorias que NO se pueden poner en un ViewSchedule regular (Cables) o que
# no exponen el campo Keynote en schedules (Conduit), pero SI tienen keynote en el
# tipo + longitud. Se emiten como bloques ### por API para que EstimaStruct los
# importe igual que un schedule normal (columnas Keynote/Type/Length). ---
_KP = DB.BuiltInParameter.KEYNOTE_PARAM


def _keynote(elem):
    if elem is None:
        return None
    p = elem.get_Parameter(_KP)
    return (p.AsString() if p else None) or None


def _to_meters(feet):
    try:
        return DB.UnitUtils.ConvertFromInternalUnits(feet, DB.UnitTypeId.Meters)
    except Exception:
        try:
            return DB.UnitUtils.ConvertFromInternalUnits(feet, DB.DisplayUnitType.DUT_METERS)
        except Exception:
            return feet * 0.3048


def api_length_blocks():
    """Devuelve [(title, [row,...]), ...] para Cables y Conduit (keynote de tipo +
    longitud total en metros por keynote)."""
    from collections import defaultdict
    out = []
    targets = [
        ("18Cable Schedule", DB.BuiltInCategory.OST_Wire),
        ("19Conduit Schedule", DB.BuiltInCategory.OST_Conduit),
    ]
    for title, bic in targets:
        try:
            elems = DB.FilteredElementCollector(doc).OfCategory(bic)\
                .WhereElementIsNotElementType().ToElements()
        except Exception:
            continue
        agg = defaultdict(lambda: [0.0, ""])
        for e in elems:
            etype = doc.GetElement(e.GetTypeId())
            key = _keynote(etype) or _keynote(e)
            if not key:
                continue
            lp = e.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)
            length = lp.AsDouble() if lp else 0.0
            tname = safe_name(etype)
            agg[key][0] += _to_meters(length)
            agg[key][1] = tname
        if not agg:
            continue
        rows = [["Keynote", "Type", "Length"]]
        for key in sorted(agg.keys()):
            rows.append([key, agg[key][1], round(agg[key][0], 2)])
        out.append((title, rows))
    return out


def write_csv(path, schedules):
    exported = []
    skipped_empty = []
    missing_keynote = []
    read_errors = []

    encoding = UTF8Encoding(True)
    writer = StreamWriter(path, False, encoding)
    try:
        for view_schedule in schedules:
            schedule_name = safe_name(view_schedule)
            rows = read_schedule(view_schedule)

            if len(rows) < 2:
                skipped_empty.append(schedule_name)
                continue

            headers = rows[0]
            data_rows = rows[1:]

            if headers and str(headers[0]).startswith("ERROR:"):
                read_errors.append("{0}: {1}".format(schedule_name, headers[0]))
                continue

            if not has_keynote_header(headers):
                missing_keynote.append(schedule_name)

            writer.WriteLine(csv_line(["### {0} ###".format(schedule_name)]))
            writer.WriteLine(csv_line(headers))
            for row in data_rows:
                writer.WriteLine(csv_line(row))
            writer.WriteLine("")

            exported.append(schedule_name)

        # Bloques API (Cables/Conduit) que no salen de un ViewSchedule normal.
        for title, rows in api_length_blocks():
            writer.WriteLine(csv_line(["### {0} ###".format(title)]))
            for row in rows:
                writer.WriteLine(csv_line(row))
            writer.WriteLine("")
            exported.append(title + " (API)")
    finally:
        writer.Close()

    return exported, skipped_empty, missing_keynote, read_errors


def main():
    if doc is None:
        forms.alert("No hay documento activo en Revit.", title="Exportar Schedules")
        return

    if not os.path.isdir(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    output_path = os.path.join(
        EXPORT_DIR,
        "schedules_{0}.csv".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
    )

    all_schedules = DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule).ToElements()
    schedules = sorted(
        [schedule for schedule in all_schedules if should_export(safe_name(schedule))],
        key=lambda schedule: safe_name(schedule)
    )

    exported, skipped_empty, missing_keynote, read_errors = write_csv(output_path, schedules)

    output.print_md("## Export S5 completado")
    output.print_md("- Archivo: `{0}`".format(output_path))
    output.print_md("- Schedules exportados: `{0}`".format(len(exported)))
    output.print_md("- Schedules vacios omitidos: `{0}`".format(len(skipped_empty)))
    output.print_md("- Schedules candidatos revisados: `{0}`".format(len(schedules)))

    if missing_keynote:
        output.print_md("### Advertencia: schedules sin columna Keynote")
        for name in missing_keynote:
            output.print_md("- {0}".format(name))

    if read_errors:
        output.print_md("### Errores de lectura")
        for error in read_errors:
            output.print_md("- {0}".format(error))

    output.print_md("### Exportados")
    for name in exported:
        output.print_md("- {0}".format(name))

    forms.alert(
        "Schedules exportados: {0}\n\n{1}".format(len(exported), output_path),
        title="Exportar Schedules"
    )

    # --- Importar a EstimaStruct (solo si se genero el CSV) ---
    if output_path and os.path.isfile(output_path):
        try:
            import_to_estimastruct(output_path)
        except Exception as e:
            forms.alert(
                "La importacion a EstimaStruct fallo, pero el CSV ya quedo "
                "guardado en disco. Podes importar manualmente desde la web.\n\n"
                "Detalle: {0}".format(str(e)),
                title="EstimBot - Importacion error"
            )


if __name__ == "__main__":
    main()
