"""
revit_get_keynote_path.py — CLI ADAPTED version
==================================================================
Purpose: Obtiene ruta del TXT de keynotes cargado
Pattern: sys.path → DriverConfig → run_script(kind='execute_code', models=[VDA_CANON])

USAGE:
    D:\LLM\python\python.exe revit_get_keynote_path.py [optional_model_path]

Default model: VDA_Valle_de_Angeles2_CANON.rvt
"""
import sys, os, json
from datetime import datetime

sys.path.insert(0, r'D:/GitHub/pyrevit-mcp-stdio')
os.environ['PYREVIT_COMMAND'] = r'C:/Users/consu/AppData/Roaming/pyRevit-Master/bin/pyrevit'

from pyrevit_driver import DriverConfig, run_script

DEFAULT_MODEL = r'D:/GitHub/EstimBot/ConsuConstructEstimBot/ESTIMASTRUCT/backend/scripts_runner/vda_canon/VDA_Valle_de_Angeles2_CANON.rvt'

CODE = r'''

import json as _j
from Autodesk.Revit import DB
ktp = DB.KeynoteTable.GetKeynoteTable(doc)
try:
    external = ktp.GetExternalFileReference()
    path = str(external.GetAbsolutePath()) if external else "INTERNAL_KEYNOTE_TABLE"
except Exception:
    path = "INTERNAL_KEYNOTE_TABLE"
result = _j.dumps({"keynote_table_path": path})

'''

def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    
    if not os.path.exists(model):
        print(f"ERROR: Model not found: {model}")
        sys.exit(1)
    
    config = DriverConfig(timeout_seconds=900)
    
    print(f"[{datetime.now().isoformat()}] Executing {os.path.basename(__file__)}")
    print(f"Model: {model}")
    
    r = run_script(
        config,
        kind='execute_code',
        models=[model],
        code=CODE
    )
    
    res = r.get('result', {})
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except:
            pass
    
    print(f"Result: {res}")
    return r

if __name__ == '__main__':
    main()
