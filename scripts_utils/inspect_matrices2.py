import openpyxl, sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

EXCEL = r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.xlsx"
wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb.active

# Mostrar filas 1..30 para entender el patrón completo
print("Primeras 30 filas:")
for i, row in enumerate(ws.iter_rows(min_row=1, max_row=30, values_only=True), 1):
    a = str(row[0]).strip() if row[0] is not None else "None"
    print(f"  [{i:3}] A={a!r:15} | {[str(v)[:15] if v is not None else '-' for v in row[1:8]]}")
