import json
import sys

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Cargar V1.0
print("Loading V1.0...")
with open(r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.0\fichas\fichas_v1.0.json", 'r', encoding='utf-8') as f:
    v10 = json.load(f)

# Cargar V1.1 (actualizado)
print("Loading V1.1...")
with open(r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json", 'r', encoding='utf-8') as f:
    v11 = json.load(f)

print(f"\nV1.0: {len(v10)} fichas")
print(f"V1.1 (actual): {len(v11)} fichas")

# Mapas por código
v10_map = {f['codigo']: f for f in v10 if isinstance(f, dict) and 'codigo' in f}
v11_map = {f['codigo']: f for f in v11 if isinstance(f, dict) and 'codigo' in f}

print(f"\nV1.0 unique codes: {len(v10_map)}")
print(f"V1.1 unique codes: {len(v11_map)}")

# Códigos en V1.1
codigos_v11 = set(v11_map.keys())
codigos_v10 = set(v10_map.keys())

# Faltantes (en V1.0 pero no en V1.1)
faltantes = codigos_v10 - codigos_v11
print(f"\nMissing in V1.1 (from V1.0): {len(faltantes)} fichas")

if faltantes:
    print(f"  Examples: {list(faltantes)[:10]}")

# Nuevos (en V1.1, no en V1.0)
nuevos = codigos_v11 - codigos_v10
print(f"\nNew in V1.1 (not in V1.0): {len(nuevos)}")
if nuevos:
    print(f"  Examples: {list(nuevos)[:10]}")

# MERGE: V1.1 debe tener todas las fichas
print(f"\n--- MERGING V1.1 ---")
v11_merged = list(v11_map.values())  # Empezar con V1.1 actualizadas

# Agregar fichas de V1.0 que faltan
fichas_agregadas = 0
for codigo in faltantes:
    v11_merged.append(v10_map[codigo])
    fichas_agregadas += 1

print(f"Added {fichas_agregadas} fichas from V1.0 to V1.1")
print(f"\nV1.1 merged: {len(v11_merged)} fichas")

# Guardar V1.1 actualizado
output_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(v11_merged, f, ensure_ascii=False, indent=2)

print(f"\nSaved merged V1.1: {output_file}")
print(f"Size: {len(json.dumps(v11_merged))} bytes")

# Verificar
print(f"\nVerification:")
print(f"  V1.0: {len(v10_map)} fichas")
print(f"  V1.1 merged: {len(v11_merged)} fichas")
print(f"  All codes in V1.1 merged: {len(set(f['codigo'] for f in v11_merged if 'codigo' in f))}")
