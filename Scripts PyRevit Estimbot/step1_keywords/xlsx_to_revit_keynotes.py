"""
xlsx_to_revit_keynotes.py
=========================
EstimBot — Paso 1
Convierte MASTERFORMAT_CODES_Final.xlsx (o cualquier CSV/XLSX de 2 columnas)
al formato exacto de Revit Keynotes .txt

FORMATO DE SALIDA (VERIFICADO CONTRA RevitKeynotes_Updated.txt):
  - Encoding  : latin-1  (NO UTF-8, NO UTF-8-BOM)
  - Separador : TAB (\t)
  - Fin línea : CRLF (\r\n)  ← Windows, requerido por Revit
  - Columnas  : CODIGO \t DESCRIPCION \t PADRE
  - Headers   : PADRE vacío  →  "XX 00 00\tDescripcion\t"
  - Items     : PADRE = "XX 00 00" de su división

MODO DE USO:
  python xlsx_to_revit_keynotes.py                         # interactivo
  python xlsx_to_revit_keynotes.py input.xlsx output.txt   # argumentos
  python xlsx_to_revit_keynotes.py input.csv  output.txt   # también CSV

COLUMNAS ESPERADAS EN EL INPUT (cualquiera de estas variantes):
  Col A (índice 0): Keynote Number / CSI_Code / Codigo CSI / Clave
  Col B (índice 1): Keynote Name / Descripcion / Description / desc
"""

import os, re, sys, csv

# ─── Dependencias opcionales ────────────────────────────────────────────────
try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ─── Divisiones estándar CONSUCONSTRUCT ─────────────────────────────────────
DIVISIONS = {
    '00': 'Preliminares de Contratacion',
    '01': 'Requerimientos Generales',
    '02': 'Condiciones Existentes',
    '03': 'Concreto',
    '04': 'Albañilería',
    '05': 'Metales',
    '06': 'Maderas',
    '07': 'Aislantes Térmicos e Impermeabilizantes',
    '08': 'Puertas y Ventanas',
    '09': 'Acabados',
    '12': 'Muebles',
    '22': 'Fontanería',
    '23': 'HVAC (Calentador, Ventilador y Aire Acondicionado)',
    '25': 'Automatización y Control',
    '26': 'Electricidad',
    '27': 'Instalaciones Para Comunicación',
    '28': 'Seguridad Electrónica',
    '31': 'Movimiento de Tierra',
    '32': 'Obras Exteriores',
    '33': 'Servicios Básicos',
}

# ─── Utilidades ──────────────────────────────────────────────────────────────

def clean_desc(s):
    """Limpia descripciones que vienen de Excel con _x000D_ o saltos de línea."""
    s = str(s).strip()
    s = re.sub(r'_x000D_\s*', '', s)
    s = re.sub(r'\s*[\r\n]+\s*', ' ', s)
    return s.strip()

def quote_if_needed(s):
    """Agrega comillas si la descripción contiene comas (formato Revit)."""
    if ',' in s or '"' in s:
        return '"' + s.replace('"', '""') + '"'
    return s

def is_division_code(code):
    """True si el código es un encabezado de división (termina en 00 00)."""
    return bool(re.match(r'^\d{2} 00 00$', code.strip()))

def get_div_prefix(code):
    """Retorna los 2 dígitos de la división: '03 31 00.1' → '03'"""
    return code.strip()[:2]

# ─── Lectura de fuentes de datos ─────────────────────────────────────────────

def read_xlsx(path):
    """Lee archivo XLSX. Retorna lista de (code, desc)."""
    if not HAS_OPENPYXL:
        raise RuntimeError(
            "openpyxl no está instalado.\n"
            "Ejecuta: pip install openpyxl --break-system-packages"
        )
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        code = str(row[0]).strip() if row[0] is not None else ''
        desc = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ''
        # Saltar header row
        if i == 0 and not re.match(r'^\d{2}', code):
            continue
        if code and code != 'None':
            rows.append((code, clean_desc(desc)))
    return rows

def read_csv(path):
    """Lee archivo CSV (detecta encoding automáticamente). Retorna lista de (code, desc)."""
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            with open(path, 'r', encoding=enc) as f:
                reader = csv.reader(f)
                rows = []
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    code = row[0].strip()
                    desc = clean_desc(row[1]) if len(row) > 1 else ''
                    # Saltar header
                    if i == 0 and not re.match(r'^\d{2}', code):
                        continue
                    if code:
                        rows.append((code, desc))
            return rows
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise RuntimeError(f"No se pudo leer {path} con ningún encoding conocido.")

def read_input(path):
    """Detecta formato y lee el archivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xlsm', '.xls'):
        return read_xlsx(path)
    elif ext in ('.csv', '.tsv', '.txt'):
        return read_csv(path)
    else:
        # Intentar como CSV
        return read_csv(path)

# ─── Construcción del output ──────────────────────────────────────────────────

def build_keynotes(raw_rows):
    """
    Recibe lista de (code, desc) y genera las líneas del archivo .txt de Revit.
    
    Orden de salida:
      1. Encabezados de división (XX 00 00) — sin padre
      2. Todos los ítems (con padre = XX 00 00)
    """
    items = []
    divs_in_data = set()

    for code, desc in raw_rows:
        if not re.match(r'^\d{2}', code):
            continue  # Saltar filas que no sean códigos
        div = get_div_prefix(code)
        divs_in_data.add(div)
        if is_division_code(code):
            continue  # Las divisiones se manejan desde DIVISIONS dict
        items.append((code, desc, div))

    lines = []

    # ── Sección 1: encabezados de división ──────────────────────────────────
    for div_num in sorted(DIVISIONS.keys()):
        if div_num in divs_in_data:
            div_code = f'{div_num} 00 00'
            div_desc = quote_if_needed(DIVISIONS[div_num])
            lines.append(f'{div_code}\t{div_desc}\t')

    # ── Sección 2: ítems de actividad ────────────────────────────────────────
    for code, desc, div in items:
        parent = f'{div} 00 00'
        lines.append(f'{code}\t{quote_if_needed(desc)}\t{parent}')

    return lines

# ─── Escritura del archivo final ──────────────────────────────────────────────

def write_keynotes_txt(lines, out_path):
    """
    Escribe el archivo con:
      - Encoding : latin-1  (requerido por Revit — NO UTF-8)
      - Fin línea: CRLF (\r\n)  (Windows — requerido por Revit)
    
    Caracteres que no existen en latin-1 se reemplazan con '?' para no
    romper el archivo. El español estándar (ñ, á, é, í, ó, ú, ü) está
    completamente cubierto por latin-1.
    """
    content = '\r\n'.join(lines) + '\r\n'
    encoded = content.encode('latin-1', errors='replace')
    with open(out_path, 'wb') as f:
        f.write(encoded)
    return len(encoded)

# ─── Verificación post-escritura ──────────────────────────────────────────────

def verify_output(out_path, expected_lines):
    """Lee el archivo escrito y verifica integridad."""
    with open(out_path, 'rb') as f:
        raw = f.read()
    
    issues = []
    
    # Verificar encoding (no debe tener BOM)
    if raw[:3] == b'\xef\xbb\xbf':
        issues.append("ERROR: Archivo tiene BOM UTF-8 — Revit puede rechazarlo")
    if raw[:2] == b'\xff\xfe':
        issues.append("ERROR: Archivo tiene BOM UTF-16 — Revit lo rechazará")
    
    # Verificar line endings
    crlf = raw.count(b'\r\n')
    lf_only = raw.count(b'\n') - crlf
    if lf_only > 0:
        issues.append(f"ADVERTENCIA: {lf_only} líneas con LF en lugar de CRLF")
    
    # Verificar conteo de líneas
    actual_lines = crlf
    if actual_lines != expected_lines:
        issues.append(f"ADVERTENCIA: Se esperaban {expected_lines} líneas, se encontraron {actual_lines}")
    
    return {
        'file_size_bytes': len(raw),
        'total_lines': actual_lines,
        'crlf_lines': crlf,
        'issues': issues,
        'ok': len(issues) == 0
    }

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  EstimBot — XLSX/CSV → RevitKeynotes.txt")
    print("  Encoding: latin-1 | Line endings: CRLF | Format: TAB-sep")
    print("=" * 65)

    # Argumentos de línea de comando o modo interactivo
    if len(sys.argv) >= 3:
        in_path  = sys.argv[1]
        out_path = sys.argv[2]
    elif len(sys.argv) == 2:
        in_path  = sys.argv[1]
        out_path = None
    else:
        print()
        print("INPUT: archivo XLSX o CSV con columnas [Código, Descripción]")
        in_path = input("  Ruta del archivo: ").strip().strip('"')
        out_path = None

    # Validar input
    if not os.path.isfile(in_path):
        print(f"\n  ERROR: Archivo no encontrado: {in_path}")
        sys.exit(1)

    # Determinar output
    if not out_path:
        base_dir = os.path.dirname(in_path) or '.'
        out_path = os.path.join(base_dir, 'RevitKeynotes_EstimBot.txt')
        print(f"\n  Output: {out_path}")
        confirm = input("  ¿Continuar? (Enter=Sí / n=No): ").strip().lower()
        if confirm == 'n':
            sys.exit(0)

    # ── Leer input ──────────────────────────────────────────────────────────
    print(f"\n  Leyendo: {in_path}")
    try:
        raw_rows = read_input(in_path)
    except Exception as e:
        print(f"\n  ERROR al leer archivo: {e}")
        sys.exit(1)
    print(f"  Filas leídas: {len(raw_rows)}")

    # ── Construir keynotes ──────────────────────────────────────────────────
    lines = build_keynotes(raw_rows)
    n_divs  = sum(1 for l in lines if l.endswith('\t'))
    n_items = len(lines) - n_divs
    print(f"  Divisiones : {n_divs}")
    print(f"  Actividades: {n_items}")
    print(f"  Total líneas: {len(lines)}")

    # ── Escribir output ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else '.', exist_ok=True)
    file_size = write_keynotes_txt(lines, out_path)
    print(f"\n  Archivo escrito: {out_path}")
    print(f"  Tamaño: {file_size} bytes")

    # ── Verificar ───────────────────────────────────────────────────────────
    result = verify_output(out_path, len(lines))
    if result['ok']:
        print("\n  ✓ Verificación OK")
        print(f"  ✓ Encoding: latin-1 (sin BOM)")
        print(f"  ✓ Line endings: CRLF ({result['crlf_lines']} líneas)")
        print(f"  ✓ Listo para importar en Revit → Manage → Keynotes")
    else:
        print("\n  PROBLEMAS DETECTADOS:")
        for issue in result['issues']:
            print(f"  ✗ {issue}")

    print("\n" + "=" * 65)
    return 0 if result['ok'] else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Cancelado.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR INESPERADO: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
