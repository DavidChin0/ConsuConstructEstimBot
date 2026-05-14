"""
Corrige los nombres (descripcion) de V1.1 para que sean iguales a V1.0.
Solo actualiza el campo 'descripcion'. Precios, rendimientos e insumos de V1.1 no se tocan.
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

v10_map = {fi['codigo']: fi for fi in v10 if 'codigo' in fi}

actualizadas = []
sin_match = []

for fi in v11:
    codigo = fi.get('codigo', '')
    if codigo in v10_map:
        nombre_v10 = v10_map[codigo]['descripcion']
        if fi['descripcion'] != nombre_v10:
            actualizadas.append(f"  {codigo}: '{fi['descripcion']}' → '{nombre_v10}'")
            fi['descripcion'] = nombre_v10
    else:
        sin_match.append(codigo)

print(f"Fichas V1.1:          {len(v11)}")
print(f"Nombres actualizados: {len(actualizadas)}")
print(f"Sin match en V1.0:    {len(sin_match)}")

if actualizadas:
    print("\nCambios:")
    for c in actualizadas:
        print(c)

if sin_match:
    print(f"\nSin match (solo en V1.1, nombres intactos): {sin_match}")

with open(path_v11, 'w', encoding='utf-8') as f:
    json.dump(v11, f, ensure_ascii=False, indent=2)

print(f"\nGuardado: {path_v11}")
