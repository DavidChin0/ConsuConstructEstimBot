import json
import sys

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

print("FIXING V1.1 — Keep ONLY updated fichas\n")

# Las 40 fichas que fueron actualizadas en "Fichas revisadas 26 abril"
updated_codigos = [
    'CEI-01', 'CEI-02', 'WS-01', 'WS-03',
    'PB-08', 'SN-17', 'SN-21', 'SN-23',
    'EL-01', 'EL-02', 'EL-03', 'EL-04', 'EL-06', 'EL-08', 'EL-10',
    'STR-01', 'STR-06', 'STR-07', 'STR-13',
    'VA-1', 'VA-8', 'C-3', 'RAI-01',
    'MD-01', 'MD-02', 'MD-03',
    'AT-01', 'AT-03', 'AT-05', 'AT-06',
    'R-2', 'V-5', 'CM-02'
]

print(f"Updated fichas to keep: {len(updated_codigos)}")

# Cargar V1.1 actual (que es igual a V1.0)
with open(r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json", 'r', encoding='utf-8-sig') as f:
    v11_current = json.load(f)

print(f"V1.1 current: {len(v11_current)} fichas")

# Filtrar solo las fichas actualizadas
v11_updated = [f for f in v11_current if isinstance(f, dict) and f.get('codigo') in updated_codigos]

print(f"V1.1 filtered (updated only): {len(v11_updated)} fichas")

# Extraer códigos para verificar
v11_updated_codigos = [f['codigo'] for f in v11_updated]
print(f"\nActual updated fichas in V1.1: {sorted(v11_updated_codigos)}")

# Verificar qué falta
missing = set(updated_codigos) - set(v11_updated_codigos)
if missing:
    print(f"\nMissing from updated list: {missing}")

# Guardar V1.1 actualizado (solo las 40)
output_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(v11_updated, f, ensure_ascii=False, indent=2)

print(f"\nSaved V1.1 (updated only): {len(v11_updated)} fichas")
print(f"File: {output_file}")

# Regenerar insumos para V1.1
insumos_map = {}
for ficha in v11_updated:
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

insumos_file = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\v1.1\insumos\insumos_v1.1.json"
with open(insumos_file, 'w', encoding='utf-8') as f:
    json.dump(list(insumos_map.values()), f, ensure_ascii=False, indent=2)

print(f"Saved V1.1 insumos: {len(insumos_map)} unique")
print(f"File: {insumos_file}")

print(f"\n=== RESULT ===")
print(f"V1.0: 277 fichas (original)")
print(f"V1.1: {len(v11_updated)} fichas (updated only)")
print(f"V1.1 insumos: {len(insumos_map)} unique")
