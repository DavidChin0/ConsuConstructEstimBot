"""
revit_fix_compound_structure.py — CLI ADAPTED version
==================================================================
Purpose: Fix CompoundStructure validation errors (3 problematic assemblies)
Original snippet: D:/GitHub/EstimBot/ConsuConstructEstimBot/ESTIMASTRUCT/backend/scripts_runner/revit_fix_compound_structure.py
Pattern: sys.path → DriverConfig → run_script(kind='execute_code', models=[VDA_CANON])

USAGE:
    D:\LLM\python\python.exe revit_fix_compound_structure.py [optional_model_path]

Default model: VDA_Valle_de_Angeles2_CANON.rvt
"""
import sys, os, json
from datetime import datetime

sys.path.insert(0, r'D:/GitHub/pyrevit-mcp-stdio')
os.environ['PYREVIT_COMMAND'] = r'C:/Users/consu/AppData/Roaming/pyRevit-Master/bin/pyrevit'

from pyrevit_driver import DriverConfig, run_script

# Default model: VDA2 canon (OLE Compound, auto-detect)
DEFAULT_MODEL = r'D:/GitHub/EstimBot/ConsuConstructEstimBot/ESTIMASTRUCT/backend/scripts_runner/vda_canon/VDA_Valle_de_Angeles2_CANON.rvt'

# IronPython code block (extracted from original snippet)
CODE = r'''

from pyrevit import revit, DB
import json

doc = revit.doc

MIN_WIDTH_MM = 1.0  # Minimum width for non-Membrane layers (Revit requires >0)

def mm_to_ft(mm):
    return mm / 304.8

def ft_to_mm(ft):
    return ft * 304.8

def get_material_id(mat_name):
    
'''

def main():
    # Allow CLI override of model path
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
