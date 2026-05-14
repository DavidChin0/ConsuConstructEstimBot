import json
import sys

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Cargar V1.1 merged
with open(r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json", 'r', encoding='utf-8') as f:
    v11 = json.load(f)

print(f"V1.1: {len(v11)} fichas")

# Extraer insumos únicos de todas las fichas
insumos_map = {}

for ficha in v11:
    if not isinstance(ficha, dict):
        continue

    # Procesar insumos de la ficha
    if 'insumos' in ficha and isinstance(ficha['insumos'], list):
        for insumo in ficha['insumos']:
            if isinstance(insumo, dict) and 'codigo' in insumo:
                codigo = insumo['codigo']
                if codigo not in insumos_map:
                    insumos_map[codigo] = {
                        'codigo': codigo,
                        'descripcion': insumo.get('descripcion', ''),
                        'unidad': insumo.get('unidad', ''),
                        'precioUnitario': insumo.get('precioUnitario', 0)
                    }

print(f"Total unique insumos: {len(insumos_map)}")

# Guardar JSON de insumos
output_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\insumos\insumos_v1.1.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

print(f"\nSaved: {output_file}")
print(f"Size: {len(json.dumps(list(insumos_map.values())))} bytes")

# Mostrar algunos insumos
print(f"\nFirst 5 insumos:")
for i, insumo in enumerate(list(insumos_map.values())[:5]):
    print(f"  {insumo['codigo']}: {insumo['descripcion'][:40]}")
