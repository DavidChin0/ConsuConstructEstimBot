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
from datetime import datetime

from System.IO import StreamWriter
from System.Text import UTF8Encoding


doc = revit.doc
output = script.get_output()
output.set_title("EstimBot - Exportar Schedules")

EXPORT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"


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


if __name__ == "__main__":
    main()
