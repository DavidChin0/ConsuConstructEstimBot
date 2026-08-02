# -*- coding: utf-8 -*-
"""
PYREVIT_S10 - Export keynote_map.json for Babylon.js Viewer.

Revit 2027 / IronPython 2.7

Collects Types + Instances with Keynote assigned.
Writes keynote_map.json to Viewer projects folder.

MANUAL STEP AFTER: Export OBJ from Revit UI:
  File → Export → CAD Formats → OBJ
  Save as {project_name}.obj in the printed output folder.

Then run:
  D:\LLM\python\python.exe viewer_postprocess.py --inspect <project_dir>
"""

from pyrevit import revit, DB, forms, script
from System.IO import Directory
import json
import os
import re
import codecs
from datetime import datetime

doc = revit.doc
output = script.get_output()
output.set_title("Viewer — Export Keynote Map")

VIEWER_ROOT = r"D:\OneDrive\Bots\Viewer\projects"


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def to_str(value):
    if value is None:
        return u""
    return u"{0}".format(value)


def get_keynote(element):
    try:
        param = element.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
        if param is None:
            return u""
        val = param.AsString()
        if val:
            return val.strip()
        val = param.AsValueString()
        if val:
            return val.strip()
    except Exception:
        pass
    return u""


def get_category_name(element):
    try:
        if element.Category is not None:
            return to_str(element.Category.Name)
    except Exception:
        pass
    return u""


def get_family_name(element):
    for bip in (DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM,
                DB.BuiltInParameter.ELEM_FAMILY_PARAM):
        try:
            p = element.get_Parameter(bip)
            if p is not None:
                val = p.AsString() or p.AsValueString()
                if val:
                    return to_str(val)
        except Exception:
            pass
    return u""


def get_type_name(element):
    for bip in (DB.BuiltInParameter.SYMBOL_NAME_PARAM,
                DB.BuiltInParameter.ELEM_TYPE_PARAM):
        try:
            p = element.get_Parameter(bip)
            if p is not None:
                val = p.AsString() or p.AsValueString()
                if val:
                    return to_str(val)
        except Exception:
            pass
    return u""


def get_level_name(element):
    try:
        level_id = element.LevelId
        if level_id and level_id != DB.ElementId.InvalidElementId:
            level = doc.GetElement(level_id)
            if level:
                return to_str(DB.Element.Name.__get__(level))
    except Exception:
        pass
    return u""


def get_material_name(element):
    try:
        mat_ids = element.GetMaterialIds(False)
        if mat_ids and mat_ids.Count > 0:
            mat = doc.GetElement(list(mat_ids)[0])
            if mat:
                return to_str(DB.Element.Name.__get__(mat))
    except Exception:
        pass
    return u""


def elem_id_str(element):
    try:
        return u"{0}".format(element.Id.Value)
    except Exception:
        try:
            return u"{0}".format(element.Id.IntegerValue)
        except Exception:
            return u"?"


def sanitize_name(name):
    name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return name or "model"


def get_project_name():
    """Filename first (what Revit titlebar shows). ProjectInformation.Name as fallback."""
    try:
        path = doc.PathName
        if path:
            fname = os.path.splitext(os.path.basename(path))[0]
            if fname:
                return fname
    except Exception:
        pass
    try:
        name = doc.ProjectInformation.Name
        if name and name.strip():
            return name.strip()
    except Exception:
        pass
    return u"unnamed_project"


# ---------------------------------------------------------------------------
# KEYNOTE COLLECTION
# ---------------------------------------------------------------------------

def collect_keynote_map():
    keynote_map = {}

    # Types
    type_count = 0
    try:
        for el in DB.FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
            try:
                kn = get_keynote(el)
                if not kn:
                    continue
                keynote_map[elem_id_str(el)] = {
                    "keynote":       kn,
                    "category":      get_category_name(el),
                    "family_name":   get_family_name(el),
                    "type_name":     get_type_name(el),
                    "material_name": get_material_name(el),
                    "source":        "Type",
                }
                type_count += 1
            except Exception:
                pass
    except Exception as ex:
        output.print_md("Type collector error: `{0}`".format(ex))
    output.print_md("- Types with keynote: **{0}**".format(type_count))

    # Instances
    inst_count = 0
    try:
        for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
            try:
                kn = get_keynote(el)
                if not kn:
                    continue
                keynote_map[elem_id_str(el)] = {
                    "keynote":       kn,
                    "category":      get_category_name(el),
                    "family_name":   get_family_name(el),
                    "type_name":     get_type_name(el),
                    "material_name": get_material_name(el),
                    "level":         get_level_name(el),
                    "source":        "Instance",
                }
                inst_count += 1
            except Exception:
                pass
    except Exception as ex:
        output.print_md("Instance collector error: `{0}`".format(ex))
    output.print_md("- Instances with keynote: **{0}**".format(inst_count))

    return keynote_map


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    if doc is None:
        forms.alert("No active document.", title="Export Keynote Map")
        return

    project_name = get_project_name()
    safe_proj    = sanitize_name(project_name)
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")

    export_dir = os.path.join(VIEWER_ROOT, safe_proj)
    if not Directory.Exists(export_dir):
        Directory.CreateDirectory(export_dir)

    output.print_md("## Viewer — Export Keynote Map")
    output.print_md("**Project:** {0}".format(project_name))
    output.print_md("**Folder:**  `{0}`".format(export_dir))
    output.print_md("---")
    output.print_md("### Collecting keynotes...")

    keynote_map = collect_keynote_map()
    total = len(keynote_map)
    output.print_md("- **Total: {0}**".format(total))

    if total == 0:
        output.print_md("**WARNING:** No keynotes found. Assign Keynotes on element types in Revit.")

    # Write JSON
    meta = {
        "project_name": to_str(project_name),
        "safe_name":    safe_proj,
        "exported_at":  timestamp,
        "total":        total,
    }
    kmap_path = os.path.join(export_dir, "keynote_map.json")
    try:
        with codecs.open(kmap_path, 'w', encoding='utf-8') as f:
            json.dump({"_meta": meta, "elements": keynote_map},
                      f, indent=2, ensure_ascii=False)
        output.print_md("**keynote_map.json written.**")
    except Exception as e:
        output.print_md("**ERROR writing JSON:** `{0}`".format(e))
        return

    output.print_md("---")
    output.print_md("### Next steps")
    output.print_md(
        "1. Export OBJ manually:  \n"
        "   `File → Export → CAD Formats → OBJ`  \n"
        "   Save as **{0}.obj** in:  \n"
        "   `{1}`".format(safe_proj, export_dir)
    )
    output.print_md(
        "2. Run post-processor:  \n"
        "```\n"
        "D:\\LLM\\python\\python.exe "
        "D:\\GitHub\\EstimBot\\ConsuConstructEstimBot\\pyrevit\\scripts\\viewer_postprocess.py "
        "--inspect \"{0}\"\n"
        "```".format(export_dir)
    )


main()
