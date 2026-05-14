"""Actualiza revit_q de las partidas de la obra activa desde un export de schedules.

Importa solamente archivos generados por PYR_S5_exportar_schedules.py:
`schedules_YYYYMMDD_HHMMSS.csv` dentro de `EXPORTS/S5_schedules`.

La lectura es estricta: cada bloque debe tener su marcador `###`, una fila de
cabeceras con columna `keynote` y una columna de cantidad reconocible. No hay
fallbacks inventados ni valores por defecto arbitrarios.

Uso (CLI):
  python import_quantities.py <obra_id> <csv_path>
"""
import csv, os, re, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
from models import Presupuesto, Capitulo, Partida

SCHEDULES_PREFIX = "schedules_"


def _is_supported_schedules_export(csv_path: str) -> bool:
    name = os.path.basename(csv_path).lower()
    return name.startswith(SCHEDULES_PREFIX) and name.endswith(".csv")


def _parse_schedules_csv(csv_path: str) -> dict:
    totals = defaultdict(float)
    headers = []
    keynote_col = qty_col = None
    in_schedule = False
    saw_valid_schedule = False
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            first = (row[0] or "").strip()
            if first.startswith("###"):
                headers = []
                keynote_col = qty_col = None
                in_schedule = True
                continue
            if not in_schedule:
                continue
            if not headers:
                headers = [cell.strip() for cell in row]
                for i, h in enumerate(headers):
                    hl = h.strip().lower()
                    if keynote_col is None and (
                        "keynote" in hl or
                        hl == "csi" or
                        hl.startswith("csi ") or
                        "csi /" in hl or
                        "csi/" in hl
                    ):
                        keynote_col = i
                    if qty_col is None and (
                        hl in ("count", "length", "area", "volume", "value", "cantidad", "quantity", "qty") or
                        "cantidad" in hl or
                        "count" in hl
                    ):
                        qty_col = i
                if keynote_col is None:
                    raise ValueError("El export de schedules no contiene una columna keynote válida")
                if qty_col is None:
                    raise ValueError("El export de schedules no contiene una columna de cantidad válida")
                saw_valid_schedule = True
                continue
            if keynote_col is None or qty_col is None:
                continue
            keynote = row[keynote_col].strip() if keynote_col < len(row) else ""
            if not keynote:
                continue
            qty_raw = row[qty_col].strip() if qty_col is not None and qty_col < len(row) else ""
            qty_clean = re.sub(r"[^\d\.\,]", "", qty_raw).replace(",", ".")
            if not qty_clean:
                continue
            try:
                qty = float(qty_clean)
            except ValueError:
                continue
            totals[keynote] += qty
    if not saw_valid_schedule:
        return {}
    return dict(totals)


def import_quantities(obra_id: str, csv_path: str) -> dict:
    if not os.path.exists(csv_path):
        return {"ok": False, "error": f"CSV no existe: {csv_path}"}
    if not _is_supported_schedules_export(csv_path):
        return {
            "ok": False,
            "error": "Solo se admiten exports de schedules generados por PyRevit: schedules_*.csv",
        }

    totals = _parse_schedules_csv(csv_path)
    if not totals:
        return {"ok": False, "error": "El export de schedules no contiene keynotes/cantidades válidos"}

    db = SessionLocal()
    try:
        obra = db.query(Presupuesto).filter(Presupuesto.id == obra_id).first()
        if not obra:
            return {"ok": False, "error": f"Obra {obra_id} no encontrada"}

        partidas = db.query(Partida).join(Capitulo).filter(
            Capitulo.presupuesto_id == obra.id
        ).all()

        matched = 0
        zeroed = 0
        bd_keys = set()
        for p in partidas:
            key = (p.clave_csi or "").strip()
            bd_keys.add(key)
            if key in totals:
                qty = round(totals[key], 4)
                p.revit_q = qty
                p.cantidad = qty  # sync para cálculo de total
                matched += 1
            else:
                p.revit_q = 0
                p.cantidad = 0
                zeroed += 1

        # Recalcular totales por partida
        sobrecosto = float(obra.config.sobrecosto) if (obra.config and obra.config.sobrecosto is not None) else 20.0
        for p in partidas:
            base = float(p.costo_mo or 0) + float(p.costo_ma or 0) + float(p.unitario_matriz or 0)
            p.costo_base = base
            p.precio_unitario = base * (1 + sobrecosto / 100)
            p.total = float(p.cantidad or 0) * p.precio_unitario

        db.commit()

        unmatched_csv = sorted([k for k in totals if k not in bd_keys])
        return {
            "ok": True,
            "csv_path": csv_path,
            "csv_keynotes": len(totals),
            "matched": matched,
            "zeroed": zeroed,
            "unmatched_csv": unmatched_csv[:30],
            "unmatched_count": len(unmatched_csv),
            "message": f"✓ Cantidades importadas: {matched} actualizadas, {zeroed} en cero, {len(unmatched_csv)} keynotes del CSV sin contraparte en la obra",
        }
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python import_quantities.py <obra_id> <csv_path>")
        sys.exit(1)
    res = import_quantities(sys.argv[1], sys.argv[2])
    print(res.get("message") or res.get("error"))
    sys.exit(0 if res.get("ok") else 1)
