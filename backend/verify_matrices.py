"""Verifica que cada matriz del CSV exista en proyecto 'test' con los insumos
y rendimientos correctos, y que NO haya insumos extra."""
import csv
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from db import SessionLocal
from models import Presupuesto, Capitulo, Partida, InsumoPartida
from import_matrices_csv import parse_csv

CSV_FILE = r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.csv"
TOL = Decimal('0.000001')


def main():
    db = SessionLocal()
    matrices = parse_csv(CSV_FILE)
    print(f"CSV: {len(matrices)} matrices")

    obra = db.query(Presupuesto).filter(Presupuesto.nombre == 'test').first()
    if not obra:
        print("ERROR: obra 'test' no existe")
        return 1

    matrices_ok = 0
    matrices_missing = []
    matrices_extra_insumos = []
    matrices_missing_insumos = []
    matrices_rend_mismatch = []

    csi_set_csv = set()

    for m in matrices:
        csi = m['csi']
        csi_set_csv.add(csi)
        cap_code = csi.split()[0]
        capitulo = db.query(Capitulo).filter(
            Capitulo.presupuesto_id == obra.id,
            Capitulo.clave == cap_code
        ).first()
        if not capitulo:
            matrices_missing.append((csi, "capitulo no existe"))
            continue
        partida = db.query(Partida).filter(
            Partida.capitulo_id == capitulo.id,
            Partida.clave_csi == csi
        ).first()
        if not partida:
            matrices_missing.append((csi, "partida no existe"))
            continue

        insumos_db = db.query(InsumoPartida).filter(
            InsumoPartida.partida_id == partida.id
        ).all()

        csv_claves = [r['clave'] for r in m['recursos']]
        db_claves = [i.clave for i in insumos_db]

        # extras en DB que no estan en CSV
        extra = set(db_claves) - set(csv_claves)
        if extra:
            matrices_extra_insumos.append((csi, list(extra)))

        # faltantes en DB
        falt = set(csv_claves) - set(db_claves)
        if falt:
            matrices_missing_insumos.append((csi, list(falt)))

        # comparar rendimientos por clave
        db_map = {i.clave: i for i in insumos_db}
        for r in m['recursos']:
            ins = db_map.get(r['clave'])
            if not ins:
                continue
            csv_rend = Decimal(str(r['rendimiento']))
            db_rend = Decimal(str(ins.cantidad))
            if abs(csv_rend - db_rend) > TOL:
                matrices_rend_mismatch.append(
                    (csi, r['clave'], str(csv_rend), str(db_rend))
                )

        if not extra and not falt and not any(
            x[0] == csi for x in matrices_rend_mismatch
        ):
            matrices_ok += 1

    # Buscar partidas en DB que NO esten en CSV (insumos extra a nivel matriz)
    todas_partidas = db.query(Partida).join(Capitulo).filter(
        Capitulo.presupuesto_id == obra.id
    ).all()
    partidas_extra_db = [
        p.clave_csi for p in todas_partidas if p.clave_csi not in csi_set_csv
    ]

    print()
    print("=" * 70)
    print(f"OK (matriz completa, rendimientos correctos): {matrices_ok}/{len(matrices)}")
    print(f"Matrices faltantes en DB: {len(matrices_missing)}")
    for c, why in matrices_missing[:10]:
        print(f"  - {c}: {why}")

    print(f"Matrices con insumos EXTRA en DB: {len(matrices_extra_insumos)}")
    for c, claves in matrices_extra_insumos[:10]:
        print(f"  - {c}: {claves}")

    print(f"Matrices con insumos FALTANTES en DB: {len(matrices_missing_insumos)}")
    for c, claves in matrices_missing_insumos[:10]:
        print(f"  - {c}: {claves}")

    print(f"Discrepancias de rendimiento: {len(matrices_rend_mismatch)}")
    for c, k, csv_v, db_v in matrices_rend_mismatch[:10]:
        print(f"  - {c} / {k}: CSV={csv_v} DB={db_v}")

    print(f"Partidas en DB sin contraparte en CSV: {len(partidas_extra_db)}")
    for c in partidas_extra_db[:10]:
        print(f"  - {c}")
    print("=" * 70)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
