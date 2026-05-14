"""
Regenera fichas_v1.1.json desde el Excel con campo csi correcto.
Regenera fichas_v1.0.json desde MatricesImport.xlsx con campo csi correcto.
"""
import json, os, re, sys, openpyxl
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

BASE   = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated"
EXCEL_V11 = r"D:\OneDrive\Bots\Estimbot\MasterFiles\Fichas revisadas 26 abril.xlsx"
EXCEL_V10 = r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.xlsx"

def clean(s):
    if s is None: return ''
    return re.sub(r'_x000D_|\r', '', str(s)).strip()

def safe_float(v, default=0.0):
    try: return float(v)
    except: return default


# ─── GENERAR V1.1 ─────────────────────────────────────────────────────────────
print("=" * 60)
print("Generando V1.1 desde Fichas revisadas 26 abril.xlsx")
print("=" * 60)

wb = openpyxl.load_workbook(EXCEL_V11, data_only=True)
ws = wb.active

fichas_v11 = []
current = None

for row in ws.iter_rows(min_row=2, values_only=True):
    csi_col, desc, unidad, cantidad, precio_u, total = row
    if csi_col is None and desc is None:
        continue
    csi_str = str(csi_col).strip() if csi_col else ''
    desc_str = clean(desc)

    # Saltar headers repetidos
    if desc_str == 'Descripción' or csi_str == 'CSI / Recurso':
        continue

    if csi_str.lower() == 'recurso':
        if current is None: continue
        codigo_ins = desc_str.split()[0] if desc_str else ''
        current['insumos'].append({
            'codigo':         codigo_ins,
            'descripcion':    desc_str,
            'unidad':         clean(unidad) or 'global',
            'cantidad':       safe_float(cantidad),
            'precioUnitario': safe_float(precio_u),
        })
    else:
        if current: fichas_v11.append(current)
        if not desc_str: current = None; continue
        codigo_ficha = desc_str.split()[0] if desc_str else ''
        # CSI: columna A tiene el código (ej: "09 22 13")
        csi_value = csi_str if re.match(r'^\d{2}\s', csi_str) else '09 00 00'
        current = {
            'codigo':          codigo_ficha,
            'descripcion':     desc_str,
            'unidad':          clean(unidad) or 'm2',
            'cantidad':        1.0,
            'precio_unitario': safe_float(total),
            'csi':             csi_value,
            'insumos':         [],
        }

if current: fichas_v11.append(current)

print(f"  Fichas V1.1: {len(fichas_v11)}")
for f in fichas_v11[:3]:
    print(f"  {f['codigo']:12} csi={f['csi']:12} ins={len(f['insumos'])} pu={f['precio_unitario']}")


# ─── GENERAR V1.0 ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("Generando V1.0 desde MatricesImport.xlsx")
print("=" * 60)

wb0 = openpyxl.load_workbook(EXCEL_V10, data_only=True)
ws0 = wb0.active

fichas_v10 = []
cur0 = None
FICHA_RX = re.compile(r'^\d+')

for row in ws0.iter_rows(min_row=2, values_only=True):
    if all(c is None for c in row): continue
    a = str(row[0]).strip() if row[0] is not None else ''
    if a in ('', 'Clave', 'C', 'None'): continue

    if a in ('Recurso', 'Simple'):
        if cur0 is None: continue
        codigo = clean(row[1])
        if not codigo: continue
        desc = clean(row[2])
        cur0['insumos'].append({
            'codigo':         codigo,
            'descripcion':    f"{codigo} {desc}" if not desc.startswith(codigo) else desc,
            'unidad':         clean(row[3]) or 'global',
            'cantidad':       safe_float(row[4]),
            'precioUnitario': safe_float(row[5]),
        })
    elif FICHA_RX.match(a):
        if cur0: fichas_v10.append(cur0)
        codigo = clean(row[1])
        desc   = clean(row[2])
        unidad = clean(row[3]) or 'global'
        precio = safe_float(row[8])
        if not codigo: cur0 = None; continue
        cur0 = {
            'codigo':          codigo,
            'descripcion':     f"{codigo} {desc}" if not desc.startswith(codigo) else desc,
            'unidad':          unidad,
            'cantidad':        1.0,
            'precio_unitario': round(precio, 4),
            'csi':             a,   # ej: "09 22 13"
            'insumos':         [],
        }

if cur0: fichas_v10.append(cur0)

print(f"  Fichas V1.0: {len(fichas_v10)}")
for f in fichas_v10[:3]:
    print(f"  {f['codigo']:12} csi={f['csi']:12} ins={len(f['insumos'])} pu={f['precio_unitario']}")


# ─── GUARDAR ──────────────────────────────────────────────────────────────────
def guardar(fichas, version):
    path_f = os.path.join(BASE, version, "fichas",  f"fichas_{version}.json")
    path_i = os.path.join(BASE, version, "insumos", f"insumos_{version}.json")
    os.makedirs(os.path.dirname(path_f), exist_ok=True)
    os.makedirs(os.path.dirname(path_i), exist_ok=True)

    with open(path_f, 'w', encoding='utf-8') as f:
        json.dump(fichas, f, ensure_ascii=False, indent=2)

    insumos_map = {}
    for fi in fichas:
        for ins in fi.get('insumos', []):
            c = ins['codigo']
            if c not in insumos_map:
                insumos_map[c] = {'codigo': c, 'descripcion': ins['descripcion'],
                                  'unidad': ins['unidad'], 'precioUnitario': ins['precioUnitario']}
    with open(path_i, 'w', encoding='utf-8') as f:
        json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

    print(f"  {version}: {len(fichas)} fichas | {len(insumos_map)} insumos → {path_f}")

print()
print("=" * 60)
print("Guardando")
print("=" * 60)
guardar(fichas_v11, "v1.1")
guardar(fichas_v10, "v1.0")
print()
print("LISTO. Reinicia el backend y crea obras NUEVAS para probar.")
