"""
Importa el catalogo de recursos desde ejemplo opus.xls a la DB de Estimacion.
Solo inserta recursos que no existan (por clave). No toca presupuestos.
"""
import xlrd
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from db import engine, SessionLocal
from models import Base, Recurso

# LEGACY — archivo de referencia histórica, no usar en operación normal
XLS = r"D:\OneDrive\Bots\Estimbot\OpusBot\ejemplo opus.xls"

TIPO_MAP = {
    "MA": "MATERIAL",
    "MO": "MANO_OBRA",
    "HE": "HERRAMIENTA",
    "HER": "HERRAMIENTA",
    "EQ": "EQUIPO",
    "FL": "FLETE",
    "SC": "SUBCONTRATO",
    "SUB": "SUBCONTRATO",
}

def tipo_de_clave(clave: str) -> str:
    prefix = clave.split("-")[0].upper() if "-" in clave else ""
    return TIPO_MAP.get(prefix, "MATERIAL")


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    wb = xlrd.open_workbook(XLS)
    ws = wb.sheet_by_index(0)

    inserted = 0
    skipped = 0

    # Pre-load existing claves and track seen in this run
    existing_claves = {r.clave for r in db.query(Recurso.clave).all()}
    seen_this_run = set()

    for row_idx in range(1, ws.nrows):
        row = ws.row_values(row_idx)
        nivel = str(row[0]).strip()
        clave = str(row[1]).strip()
        desc  = str(row[2]).strip()
        unidad = str(row[3]).strip() if row[3] else "GL"

        try:
            precio = float(row[5]) if row[5] else 0.0
        except (ValueError, TypeError):
            precio = 0.0

        # Solo filas de recursos
        if nivel not in ("Simple", "Compuesto") and "-" not in clave:
            continue
        if not clave or not desc:
            continue
        if nivel in ("0", "1", "2", "C"):
            continue

        tipo = tipo_de_clave(clave)

        if clave in existing_claves or clave in seen_this_run:
            skipped += 1
            continue

        seen_this_run.add(clave)
        r = Recurso(
            clave=clave,
            descripcion=desc,
            unidad=unidad,
            tipo=tipo,
            precio_unitario=precio
        )
        db.add(r)
        inserted += 1

    db.commit()
    db.close()
    print(f"Seed completo: {inserted} recursos insertados, {skipped} omitidos (ya existian).")


if __name__ == "__main__":
    run()
