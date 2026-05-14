"""Importa Type Mark desde BaseDatosOpus2026.xlsx (col A=CSI, col B=Type Mark)
y los aplica a las partidas de la obra 'OBRA #1 TEST' (y/o template) por CSI."""
# MIGRATION TOOL — Solo para import inicial desde Excel/OPUS.
# No usar en operación normal. Fuente activa: estimacion.db
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import openpyxl
from db import SessionLocal
from models import Presupuesto, Capitulo, Partida

XLSX = r"D:\OneDrive\Bots\Estimbot\MasterFiles\BaseDatosOpus2026.xlsx"
TARGET_OBRAS = ["Template 2026", "Template CC 2026"]

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active
csi_to_tm = {}
for row in ws.iter_rows(min_row=3, values_only=True):
    if not row or row[0] is None:
        continue
    csi = str(row[0]).strip()
    tm = str(row[1]).strip() if row[1] is not None else ""
    if csi and tm:
        csi_to_tm[csi] = tm
print(f"Mapa CSI->Type Mark: {len(csi_to_tm)} entradas")

db = SessionLocal()
try:
    obras = db.query(Presupuesto).filter(Presupuesto.nombre.in_(TARGET_OBRAS)).all()
    print(f"Obras destino: {[o.nombre for o in obras]}")
    total_updated = 0
    total_no_match = 0
    no_match_csis = []
    for obra in obras:
        partidas = db.query(Partida).join(Capitulo).filter(
            Capitulo.presupuesto_id == obra.id
        ).all()
        upd = 0
        for p in partidas:
            tm = csi_to_tm.get(p.clave_csi)
            if tm:
                if p.type_mark != tm:
                    p.type_mark = tm
                    upd += 1
            else:
                total_no_match += 1
                no_match_csis.append(p.clave_csi)
        total_updated += upd
        print(f"  {obra.nombre}: {upd} actualizadas / {len(partidas)} totales")
    db.commit()
    print(f"\nTotal actualizadas: {total_updated}")
    print(f"Sin match en BaseDatos: {total_no_match}")
    if no_match_csis:
        print("Ejemplos sin match:", no_match_csis[:10])
finally:
    db.close()
