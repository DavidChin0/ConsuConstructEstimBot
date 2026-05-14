"""
Sincroniza nombres de V1.1 usando CSI como clave de match (no el type mark).
Si CSI coincide entre V1.0 y V1.1 → copia nombre de V1.0.
Si CSI no coincide → conserva nombre original de V1.1.
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

BASE = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated"
path_v10 = fr"{BASE}\v1.0\fichas\fichas_v1.0.json"
path_v11 = fr"{BASE}\v1.1\fichas\fichas_v1.1.json"

with open(path_v10, encoding='utf-8') as f:
    v10 = json.load(f)
with open(path_v11, encoding='utf-8') as f:
    v11 = json.load(f)

# Índice V1.0 por CSI (puede haber varios por CSI, tomamos el primero)
v10_by_csi = {}
for fi in v10:
    csi = fi.get('csi', '').strip()
    if csi and csi not in v10_by_csi:
        v10_by_csi[csi] = fi

print(f"V1.0: {len(v10)} fichas | {len(v10_by_csi)} CSI únicos")
print(f"V1.1: {len(v11)} fichas")
print()

actualizadas = []
conservadas  = []
sin_csi      = []

for fi in v11:
    csi = fi.get('csi', '').strip()
    codigo = fi.get('codigo', '')

    if not csi:
        sin_csi.append(codigo)
        continue

    if csi in v10_by_csi:
        nombre_v10 = v10_by_csi[csi]['descripcion']
        if fi['descripcion'] != nombre_v10:
            actualizadas.append({
                'codigo': codigo, 'csi': csi,
                'antes': fi['descripcion'], 'despues': nombre_v10
            })
            fi['descripcion'] = nombre_v10
    else:
        conservadas.append(f"  {codigo} (csi={csi}) — sin match en V1.0, nombre conservado")

print(f"Nombres actualizados por CSI: {len(actualizadas)}")
for c in actualizadas:
    print(f"  [{c['csi']}] {c['codigo']}: '{c['antes']}' → '{c['despues']}'")

print(f"\nConservados (CSI no existe en V1.0): {len(conservadas)}")
for c in conservadas:
    print(c)

if sin_csi:
    print(f"\nSin campo CSI (intactos): {sin_csi}")

with open(path_v11, 'w', encoding='utf-8') as f:
    json.dump(v11, f, ensure_ascii=False, indent=2)

print(f"\nGuardado: {path_v11}")
