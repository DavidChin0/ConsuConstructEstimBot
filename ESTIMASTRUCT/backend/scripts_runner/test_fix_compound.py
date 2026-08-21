import sys
sys.path.insert(0, r"D:\GitHub\revit-mcp-stdio")
from revit_mcp.pipe.helpers import execute_code

with open(r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\backend\scripts_runner\revit_fix_compound_structure.py", "r") as f:
    content = f.read()
import re
m = re.search(r'CODE = r\'\'\'(.*?)\'\'\'', content, re.DOTALL)
if m:
    code = m.group(1)
    print('Code extracted, length:', len(code))
    print('First 500 chars:')
    print(code[:500])
else:
    print('CODE block not found')