"""
setup_v10_v11.py
- Copia las fichas actuales (v1.1 existente) → v1.0
- Genera nuevas fichas v1.1 desde "Fichas revisadas 26 abril.xlsx"
"""
import json
import os
import shutil
import re
import sys
import openpyxl

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

BASE = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated"
EXCEL = r"D:\OneDrive\Bots\Estimbot\MasterFiles\Fichas revisadas 26 abril.xlsx"

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_FICHAS   = os.path.join(BASE, "v1.1", "fichas",  "fichas_v1.1.json")
SRC_INSUMOS  = os.path.join(BASE, "v1.1", "insumos", "insumos_v1.1.json")

DST_V10_FICHAS  = os.path.join(BASE, "v1.0", "fichas",  "fichas_v1.0.json")
DST_V10_INSUMOS = os.path.join(BASE, "v1.0", "insumos", "insumos_v1.0.json")

DST_V11_FICHAS  = os.path.join(BASE, "v1.1", "fichas",  "fichas_v1.1.json")
DST_V11_INSUMOS = os.path.join(BASE, "v1.1", "insumos", "insumos_v1.1.json")


# ── PASO 1: Copiar actuales → v1.0 ───────────────────────────────────────────
print("=" * 60)
print("PASO 1: Copiar fichas actuales → v1.0")
print("=" * 60)

os.makedirs(os.path.dirname(DST_V10_FICHAS),  exist_ok=True)
os.makedirs(os.path.dirname(DST_V10_INSUMOS), exist_ok=True)

shutil.copy2(SRC_FICHAS,  DST_V10_FICHAS)
shutil.copy2(SRC_INSUMOS, DST_V10_INSUMOS)

with open(DST_V10_FICHAS, encoding='utf-8') as f:
    v10_fichas = json.load(f)

print(f"  v1.0 fichas:  {len(v10_fichas)}")
print(f"  Guardado en:  {DST_V10_FICHAS}")


# ── PASO 2: Parsear Excel → fichas v1.1 ──────────────────────────────────────
print()
print("=" * 60)
print("PASO 2: Generar v1.1 desde Excel")
print("=" * 60)

wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb.active

fichas = []
ficha_actual = None
CODIGO_RX = re.compile(r'^([A-Z][\w\-]+(?:\-\d+(?:\.\d+)?)?)\s+')

for row in ws.iter_rows(min_row=2, values_only=True):
    csi, desc, unidad, cantidad, precio_u, total = row

    if csi is None and desc is None:
        continue

    # Saltar filas de encabezado repetidas (CSI / Recurso | Descripción | ...)
    if str(desc).strip() == 'Descripción' or str(csi).strip() == 'CSI / Recurso':
        continue

    if str(csi).strip().lower() == 'recurso':
        # Fila de insumo
        if ficha_actual is None:
            continue
        if desc is None:
            continue

        # Extraer código del insumo desde descripción
        m = CODIGO_RX.match(str(desc).strip())
        codigo_ins = m.group(1) if m else str(desc).strip()[:20]

        # precio unitario: columna E (precio_u), si falla usar total/cantidad
        try:
            pu = float(precio_u)
        except (TypeError, ValueError):
            try:
                pu = float(total) / float(cantidad) if cantidad else 0
            except (TypeError, ValueError):
                pu = 0

        try:
            cant = float(cantidad) if cantidad is not None else 0
        except (TypeError, ValueError):
            cant = 0

        ficha_actual['insumos'].append({
            'codigo':       codigo_ins,
            'descripcion':  str(desc).strip(),
            'unidad':       str(unidad).strip() if unidad else '',
            'cantidad':     cant,
            'precioUnitario': round(pu, 4),
        })

    else:
        # Nueva ficha: guardar la anterior
        if ficha_actual is not None:
            fichas.append(ficha_actual)

        if desc is None:
            ficha_actual = None
            continue

        desc_str = str(desc).strip()
        m = CODIGO_RX.match(desc_str)
        codigo_ficha = m.group(1) if m else desc_str[:20]

        try:
            pu_ficha = float(total) if total is not None else 0
        except (TypeError, ValueError):
            pu_ficha = 0

        ficha_actual = {
            'codigo':          codigo_ficha,
            'descripcion':     desc_str,
            'unidad':          str(unidad).strip() if unidad else '',
            'cantidad':        1.0,
            'precio_unitario': round(pu_ficha, 4),
            'insumos':         [],
        }

# Agregar última ficha
if ficha_actual is not None:
    fichas.append(ficha_actual)

print(f"  Fichas extraídas del Excel: {len(fichas)}")

# Verificar
for f in fichas[:3]:
    print(f"  {f['codigo']}: {f['descripcion'][:50]} — {len(f['insumos'])} insumos — PU={f['precio_unitario']}")


# ── PASO 3: Guardar v1.1 ─────────────────────────────────────────────────────
print()
print("=" * 60)
print("PASO 3: Guardar fichas v1.1")
print("=" * 60)

with open(DST_V11_FICHAS, 'w', encoding='utf-8') as f:
    json.dump(fichas, f, ensure_ascii=False, indent=2)

print(f"  v1.1 fichas: {len(fichas)}")
print(f"  Guardado en: {DST_V11_FICHAS}")


# ── PASO 4: Regenerar insumos v1.1 ───────────────────────────────────────────
print()
print("=" * 60)
print("PASO 4: Regenerar insumos v1.1")
print("=" * 60)

insumos_map = {}
for ficha in fichas:
    for ins in ficha.get('insumos', []):
        cod = ins['codigo']
        if cod not in insumos_map:
            insumos_map[cod] = {
                'codigo':        cod,
                'descripcion':   ins['descripcion'],
                'unidad':        ins['unidad'],
                'precioUnitario': ins['precioUnitario'],
            }

with open(DST_V11_INSUMOS, 'w', encoding='utf-8') as f:
    json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

print(f"  v1.1 insumos únicos: {len(insumos_map)}")
print(f"  Guardado en: {DST_V11_INSUMOS}")


# ── RESUMEN ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("RESUMEN FINAL")
print("=" * 60)
print(f"  V1.0: {len(v10_fichas)} fichas  →  {DST_V10_FICHAS}")
print(f"  V1.1: {len(fichas)} fichas      →  {DST_V11_FICHAS}")
print(f"  V1.1 insumos: {len(insumos_map)} únicos")
print()
print("OK — Ahora corregir el path en backend/routers/presupuestos.py")
