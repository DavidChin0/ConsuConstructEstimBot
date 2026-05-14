import json
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

def generate_fichas_csv(version):
    print(f"\nGenerating fichas CSV for {version}...")

    # Cargar JSON
    json_file = rf"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\{version}\fichas\fichas_{version}.json"
    csv_file = rf"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\{version}\fichas\fichas_{version}.csv"

    try:
        with open(json_file, 'r', encoding='utf-8-sig') as f:
            fichas = json.load(f)
    except:
        with open(json_file, 'r', encoding='utf-8') as f:
            fichas = json.load(f)

    # Escribir CSV
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['CSI', 'Código', 'Descripción', 'Unidad', 'Cantidad', 'Costo Total', 'Insumos'])

        for ficha in fichas:
            if isinstance(ficha, dict) and 'codigo' in ficha:
                num_insumos = len(ficha.get('insumos', []))
                writer.writerow([
                    ficha.get('csi', ''),
                    ficha.get('codigo', ''),
                    ficha.get('descripcion', ''),
                    ficha.get('unidad', ''),
                    ficha.get('cantidad', ''),
                    ficha.get('costoTotal', ''),
                    num_insumos
                ])

    print(f"  Saved: {csv_file}")
    print(f"  Fichas: {len([f for f in fichas if isinstance(f, dict) and 'codigo' in f])}")

def generate_insumos_csv(version):
    print(f"\nGenerating insumos CSV for {version}...")

    # Cargar JSON
    json_file = rf"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\{version}\insumos\insumos_{version}.json"
    csv_file = rf"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 Automation Projects\ESTIMASTRUCT\development\Template2_Updated\{version}\insumos\insumos_{version}.csv"

    try:
        with open(json_file, 'r', encoding='utf-8-sig') as f:
            insumos = json.load(f)
    except:
        with open(json_file, 'r', encoding='utf-8') as f:
            insumos = json.load(f)

    # Escribir CSV
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Código', 'Descripción', 'Unidad', 'Precio Unitario (L)'])

        for insumo in insumos:
            if isinstance(insumo, dict):
                writer.writerow([
                    insumo.get('codigo', ''),
                    insumo.get('descripcion', ''),
                    insumo.get('unidad', ''),
                    insumo.get('precioUnitario', '')
                ])

    print(f"  Saved: {csv_file}")
    print(f"  Insumos: {len([i for i in insumos if isinstance(i, dict)])}")

# Generar CSVs para ambas versiones
generate_fichas_csv('v1.0')
generate_fichas_csv('v1.1')

generate_insumos_csv('v1.0')
generate_insumos_csv('v1.1')

print("\n=== FINAL SUMMARY ===")
print("✓ V1.0: fichas_v1.0.csv, insumos_v1.0.csv")
print("✓ V1.1: fichas_v1.1.csv, insumos_v1.1.csv")
print("\nAll CSVs generated for easy reference")
