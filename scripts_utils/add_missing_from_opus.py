"""
Agrega a fichas_v1.1.json las actividades de BaseDatosOpus2026.xlsx
que no existen aún en V1.1 (comparación por codigo/type mark).
Las fichas nuevas se agregan sin insumos (insumos: []).
"""
import json, sys, openpyxl, re, shutil, tempfile, os
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from csi_utils import infer_csi as _infer_csi

XLSX   = r"D:\OneDrive\Bots\Estimbot\MasterFiles\BaseDatosOpus2026.xlsx"
V11    = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json"

CSI_RE = re.compile(r"^\d{2}\s\d{2}")

# --- Cargar V1.1 ---
with open(V11, encoding='utf-8') as f:
    fichas_v11 = json.load(f)

existing_codigos = {fi['codigo'].strip() for fi in fichas_v11 if fi.get('codigo')}
print(f"V1.1 actual: {len(fichas_v11)} fichas")
print(f"Codigos existentes: {len(existing_codigos)}\n")

# --- Leer Excel (copia temp para evitar lock) ---
tmp_fd, tmp = tempfile.mkstemp(suffix='.xlsx')
os.close(tmp_fd)
shutil.copy2(XLSX, tmp)
try:
    wb = openpyxl.load_workbook(tmp, data_only=True)
finally:
    try: os.unlink(tmp)
    except: pass

ws = wb.active

def cell(row, i):
    v = row[i].value if i < len(row) else None
    return str(v).strip() if v is not None else ''

agregadas = []

for row in ws.iter_rows(min_row=3):
    csi = cell(row, 0)
    tm  = cell(row, 1)
    if not tm or tm in ('Type Mark', 'Clave', 'None'):
        continue
    if tm in existing_codigos:
        continue

    desc  = cell(row, 2) or tm
    unid  = cell(row, 3) or 'global'

    # Use CSI from column A when available; otherwise infer from type mark / description
    if CSI_RE.match(csi):
        resolved_csi = csi
    else:
        resolved_csi = _infer_csi(tm, desc)

    ficha = {
        'csi':             resolved_csi,
        'codigo':          tm,
        'descripcion':     desc,
        'unidad':          unid,
        'precio_unitario': 0.0,
        'insumos':         [],
    }
    fichas_v11.append(ficha)
    existing_codigos.add(tm)
    agregadas.append((csi, tm, desc))

# --- Guardar ---
with open(V11, 'w', encoding='utf-8') as f:
    json.dump(fichas_v11, f, ensure_ascii=False, indent=2)

print(f"Fichas agregadas: {len(agregadas)}")
print(f"Total V1.1 ahora: {len(fichas_v11)}\n")
if agregadas:
    print("Lista de fichas agregadas:")
    for csi, tm, desc in agregadas:
        print(f"  [{csi}] {tm} — {desc}")
else:
    print("No se encontraron fichas nuevas para agregar.")
