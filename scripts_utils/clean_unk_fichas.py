import json
import sys

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Cargar V1.1
with open(r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json", 'r', encoding='utf-8') as f:
    v11 = json.load(f)

print(f"V1.1 original: {len(v11)} fichas")

# Separar fichas con problemas
unk_fichas = []
valid_fichas = []

for ficha in v11:
    if isinstance(ficha, dict) and ficha.get('codigo', '').startswith('UNK-'):
        unk_fichas.append(ficha)
        print(f"  Removed: {ficha.get('codigo')} - {ficha.get('descripcion')[:50]}")
    else:
        valid_fichas.append(ficha)

print(f"\nRemoved {len(unk_fichas)} invalid fichas (UNK-*)")
print(f"V1.1 cleaned: {len(valid_fichas)} fichas")

# Guardar versión limpia
output_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(valid_fichas, f, ensure_ascii=False, indent=2)

print(f"\nSaved cleaned V1.1: {output_file}")

# Regenerar insumos sin las fichas UNK
insumos_map = {}
for ficha in valid_fichas:
    if isinstance(ficha, dict) and 'insumos' in ficha:
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

print(f"Total insumos: {len(insumos_map)}")

# Guardar insumos limpios
insumos_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\insumos\insumos_v1.1.json"
with open(insumos_file, 'w', encoding='utf-8') as f:
    json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

print(f"Saved insumos: {insumos_file}")

print(f"\n=== FINAL V1.1 ===")
print(f"Fichas: {len(valid_fichas)}")
print(f"Insumos: {len(insumos_map)}")
