"""
Merge: agrega a V1.1 todas las fichas de V1.0 que no existen en V1.1.
Las fichas ya presentes en V1.1 NO se modifican.
"""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

BASE = r"D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated"

path_v10 = os.path.join(BASE, "v1.0", "fichas", "fichas_v1.0.json")
path_v11 = os.path.join(BASE, "v1.1", "fichas", "fichas_v1.1.json")
path_v11_ins = os.path.join(BASE, "v1.1", "insumos", "insumos_v1.1.json")

with open(path_v10, encoding='utf-8') as f:
    v10 = json.load(f)
with open(path_v11, encoding='utf-8') as f:
    v11 = json.load(f)

codigos_v11 = {fi['codigo'] for fi in v11 if 'codigo' in fi}
print(f"V1.1 actuales (revisadas, intocables): {len(v11)} fichas")
print(f"V1.0 total:                             {len(v10)} fichas")

agregadas = [fi for fi in v10 if fi.get('codigo') not in codigos_v11]
print(f"Fichas de V1.0 a agregar:               {len(agregadas)}")

v11_merged = v11 + agregadas
print(f"V1.1 final:                             {len(v11_merged)} fichas")

# Guardar fichas
with open(path_v11, 'w', encoding='utf-8') as f:
    json.dump(v11_merged, f, ensure_ascii=False, indent=2)

# Regenerar insumos únicos
insumos_map = {}
for fi in v11_merged:
    for ins in fi.get('insumos', []):
        c = ins['codigo']
        if c not in insumos_map:
            insumos_map[c] = {
                'codigo':         c,
                'descripcion':    ins['descripcion'],
                'unidad':         ins['unidad'],
                'precioUnitario': ins['precioUnitario'],
            }

with open(path_v11_ins, 'w', encoding='utf-8') as f:
    json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

print(f"Insumos únicos V1.1:                    {len(insumos_map)}")
print()
print("Códigos revisados (intocables, de Excel):")
print(" ", sorted(codigos_v11))
print()
print(f"Guardado: {path_v11}")
print("LISTO — reinicia el backend y crea una obra nueva con V1.1.")
