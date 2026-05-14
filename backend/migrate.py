"""
migrate.py — Añade columnas revit_q, factor_e, factor_f, color_tipo
y las puebla desde BaseDatosOpus2026.xlsx
Uso: python migrate.py
"""
# MIGRATION TOOL — Solo para import inicial desde Excel/OPUS.
# No usar en operación normal. Fuente activa: estimacion.db
import os, sys
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(__file__))

import sqlite3
import openpyxl
from db import SessionLocal
from models import Partida

XLSX_PATH = r"D:\OneDrive\Bots\Estimbot\MasterFiles\BaseDatosOpus2026.xlsx"
DB_PATH   = os.path.join(os.path.dirname(__file__), "estimacion.db")

# ── 1. ALTER TABLE ───────────────────────────────────────────────────
print("Añadiendo columnas...")
con = sqlite3.connect(DB_PATH)
cur = con.cursor()
for col, defn in [
    ("revit_q",    "NUMERIC DEFAULT 0"),
    ("factor_e",   "NUMERIC DEFAULT 1"),
    ("factor_f",   "NUMERIC DEFAULT 1"),
    ("color_tipo", "TEXT DEFAULT 'blanco'"),
]:
    try:
        cur.execute(f"ALTER TABLE partida ADD COLUMN {col} {defn}")
        print(f"  + {col}")
    except sqlite3.OperationalError:
        print(f"  = {col} ya existe")
con.commit()
con.close()

# ── 2. Leer Excel ────────────────────────────────────────────────────
print(f"Leyendo {XLSX_PATH} ...")
wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
ws = wb.active
rows = list(ws.iter_rows(min_row=3, values_only=True))

def to_factor(v):
    """Retorna float si es número válido != 0, sino 1.0 (sin multiplicación)"""
    try:
        f = float(v)
        return f if f else 1.0
    except (TypeError, ValueError):
        return 1.0

# clave_csi -> (factor_e, factor_f)
xlsx_factors = {}
for row in rows:
    clave = str(row[0]).strip() if row[0] else None
    if not clave:
        continue
    fe = to_factor(row[4])  # col E
    ff = to_factor(row[5])  # col F
    xlsx_factors[clave] = (fe, ff)

print(f"  {len(xlsx_factors)} actividades en Excel")

# ── 3. Actualizar todas las partidas en DB ───────────────────────────
print("Actualizando partidas...")
db = SessionLocal()
try:
    partidas = db.query(Partida).all()
    n = 0
    for p in partidas:
        # color_tipo desde es_formula
        if not p.color_tipo or p.color_tipo == 'blanco':
            p.color_tipo = 'amarillo' if p.es_formula else 'blanco'

        # factores desde Excel
        if p.clave_csi in xlsx_factors:
            p.factor_e, p.factor_f = xlsx_factors[p.clave_csi]
        elif p.formula_ref:
            try:
                p.factor_e = float(p.formula_ref)
            except (TypeError, ValueError):
                p.factor_e = 1.0
            p.factor_f = 1.0
        else:
            p.factor_e = 1.0
            p.factor_f = 1.0

        n += 1

    db.commit()
    print(f"  {n} partidas actualizadas")
finally:
    db.close()

print("\nMigración completada ✓")
