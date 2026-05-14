"""
generate_v10.py
Genera fichas_v1.0.json desde MatricesImport.xlsx
"""
import json, os, re, sys, openpyxl
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

EXCEL   = r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.xlsx"
BASE    = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated"
OUT_FICHAS  = os.path.join(BASE, "v1.0", "fichas",  "fichas_v1.0.json")
OUT_INSUMOS = os.path.join(BASE, "v1.0", "insumos", "insumos_v1.0.json")

os.makedirs(os.path.dirname(OUT_FICHAS),  exist_ok=True)
os.makedirs(os.path.dirname(OUT_INSUMOS), exist_ok=True)

def clean(s):
    """Elimina artefactos de Excel (_x000D_, saltos de línea extra)."""
    if s is None:
        return ''
    return re.sub(r'_x000D_|\r', '', str(s)).strip()

def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

# ── Parsear Excel ─────────────────────────────────────────────────────────────
wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb.active

fichas = []
current = None
FICHA_RX = re.compile(r'^\d+')   # A empieza con dígito

for row in ws.iter_rows(min_row=2, values_only=True):
    if all(c is None for c in row):
        continue

    a = str(row[0]).strip() if row[0] is not None else ''

    # Saltar encabezados y líneas totales
    if a in ('', 'Clave', 'C', 'None') or a is None:
        continue

    if a in ('Recurso', 'Simple'):
        # Fila de insumo
        if current is None:
            continue
        codigo = clean(row[1])
        if not codigo:
            continue
        desc = clean(row[2])
        current['insumos'].append({
            'codigo':         codigo,
            'descripcion':    f"{codigo} {desc}" if not desc.startswith(codigo) else desc,
            'unidad':         clean(row[3]) or 'global',
            'cantidad':       safe_float(row[4]),
            'precioUnitario': safe_float(row[5]),
        })

    elif FICHA_RX.match(a):
        # Nueva ficha
        if current is not None:
            fichas.append(current)

        codigo  = clean(row[1])
        desc    = clean(row[2])
        unidad  = clean(row[3]) or 'global'
        precio  = safe_float(row[8])   # columna I: Precio Unitario

        if not codigo:
            current = None
            continue

        current = {
            'codigo':          codigo,
            'descripcion':     f"{codigo} {desc}" if not desc.startswith(codigo) else desc,
            'unidad':          unidad,
            'cantidad':        1.0,
            'precio_unitario': round(precio, 4),
            'insumos':         [],
        }

if current is not None:
    fichas.append(current)

# ── Estadísticas ──────────────────────────────────────────────────────────────
total_insumos = sum(len(f['insumos']) for f in fichas)
print(f"Fichas extraídas:  {len(fichas)}")
print(f"Insumos totales:   {total_insumos}")
print(f"Promedio insumos:  {total_insumos/len(fichas):.1f} por ficha")
print("\nPrimeras 5 fichas:")
for f in fichas[:5]:
    print(f"  {f['codigo']:12} | {len(f['insumos']):2} ins | PU={f['precio_unitario']:>10.2f} | {f['descripcion'][:45]}")

# ── Guardar fichas ────────────────────────────────────────────────────────────
with open(OUT_FICHAS, 'w', encoding='utf-8') as fh:
    json.dump(fichas, fh, ensure_ascii=False, indent=2)
print(f"\nGuardado: {OUT_FICHAS}")

# ── Generar insumos únicos ────────────────────────────────────────────────────
insumos_map = {}
for ficha in fichas:
    for ins in ficha['insumos']:
        cod = ins['codigo']
        if cod not in insumos_map:
            insumos_map[cod] = {
                'codigo':         cod,
                'descripcion':    ins['descripcion'],
                'unidad':         ins['unidad'],
                'precioUnitario': ins['precioUnitario'],
            }

with open(OUT_INSUMOS, 'w', encoding='utf-8') as fh:
    json.dump(list(insumos_map.values()), fh, ensure_ascii=False, indent=2)
print(f"Insumos únicos: {len(insumos_map)}")
print(f"Guardado: {OUT_INSUMOS}")
