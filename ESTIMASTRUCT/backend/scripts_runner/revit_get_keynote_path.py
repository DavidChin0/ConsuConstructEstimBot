"""IronPython snippet — inyectar via execute_revit_code para obtener la ruta del TXT de keynotes cargado en el proyecto activo.

Run pattern (same as revit_dump_snippet.py):
    with open(r"...revit_get_keynote_path.py") as f: src = f.read()
    import re; m = re.search(r"CODE = r'''(.*?)'''", src, re.DOTALL)
    mcp__revit__execute_revit_code(code=m.group(1))

Output: KEYNOTE_FILE: <ruta absoluta al TXT>
"""

CODE = r'''
from pyrevit import revit, DB
doc = revit.doc

kt = DB.KeynoteTable.GetKeynoteTable(doc)
if kt is None:
    print("NO keynote table loaded in this project")
else:
    ext = kt.GetExternalFileReference()
    if ext is None:
        print("NO external file reference — keynote table embedded or missing")
    else:
        abs_path = ext.GetAbsolutePath()
        user_path = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(abs_path)
        print("KEYNOTE_FILE: " + str(user_path))
'''

if __name__ == "__main__":
    import re
    m = re.search(r"CODE = r'''(.*?)'''", open(__file__, encoding="utf-8").read(), re.DOTALL)
    print(m.group(1) if m else "CODE block not found")
