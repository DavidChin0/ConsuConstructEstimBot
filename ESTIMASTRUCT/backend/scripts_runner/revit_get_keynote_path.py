"""IronPython snippet — inyectar via execute_revit_code para obtener la ruta del TXT de keynotes cargado en el proyecto activo.

Run pattern (same as revit_dump_snippet.py):
    with open(r"...revit_get_keynote_path.py") as f: src = f.read()
    import re; m = re.search(r"^CODE = r'''(.*?)'''", src, re.DOTALL | re.MULTILINE)
    mcp__revit__execute_revit_code(code=m.group(1))

Output: KEYNOTE_FILE: <ruta absoluta al TXT>
"""

CODE = r'''
from pyrevit import revit, DB
import os
doc = revit.doc

# Debe vivir bajo la carpeta que EstimaStruct usa para exportar el TXT de
# keynotes (CONFIG.KEYNOTES_DIR = EXPORTS_DIR/S1_keynotes, ver
# generate_keynotes_catalog.py) -- si el proyecto tiene cargado un TXT de
# otro lado, esta desincronizado del catalogo canonico.
CANON_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S1_keynotes"

kt = DB.KeynoteTable.GetKeynoteTable(doc)
if kt is None:
    print("NO keynote table loaded in this project")
else:
    ext = kt.GetExternalFileReference()
    if ext is None:
        print("NO external file reference — keynote table embedded or missing")
    else:
        abs_path = ext.GetAbsolutePath()
        user_path = str(DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(abs_path))
        print("KEYNOTE_FILE: " + user_path)
        actual_dir = os.path.dirname(user_path)
        if os.path.normcase(actual_dir) == os.path.normcase(CANON_DIR):
            print("MATCH: cargado desde el canon de EstimaStruct (" + CANON_DIR + ")")
        else:
            print("MISMATCH: esperado bajo " + CANON_DIR + " -- proyecto desincronizado del catalogo canonico")
'''

if __name__ == "__main__":
    import re
    m = re.search(r"^CODE = r'''(.*?)'''", open(__file__, encoding="utf-8").read(), re.DOTALL | re.MULTILINE)
    print(m.group(1) if m else "CODE block not found")
