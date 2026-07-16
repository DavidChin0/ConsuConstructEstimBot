"""Actualiza revit_q de las partidas de la obra activa desde un export de schedules.

Importa solamente archivos generados por PYR_S5_exportar_schedules.py:
`schedules_YYYYMMDD_HHMMSS.csv` dentro de `EXPORTS/S5_schedules`.

La lectura es estricta: cada bloque debe tener su marcador `###`, una fila de
cabeceras con columna `keynote` y una columna de cantidad reconocible. No hay
fallbacks inventados ni valores por defecto arbitrarios.

Uso (CLI):
  python import_quantities.py <obra_id> <csv_path>
"""
import csv, os, re, sys, math
from collections import defaultdict


from backend.db import SessionLocal
from backend.models import Presupuesto, Capitulo, Partida
from backend.services.pricing import recalcular_partida

SCHEDULES_PREFIX = "schedules_"


def _is_supported_schedules_export(csv_path: str) -> bool:
    name = os.path.basename(csv_path).lower()
    return name.startswith(SCHEDULES_PREFIX) and name.endswith(".csv")


def _normalize_csi_key(key: str) -> str:
    """Normaliza CSI para tolerar variantes como '22 41 13 13.1' vs '22 41 13.13.1'."""
    if not key:
        return ""
    raw = str(key).replace("_x000D_", "").strip()
    # Revit a veces concatena el mismo keynote repetido en varias líneas
    # (tag multi-selección); si todas las líneas son iguales, usar solo una.
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if lines and all(ln == lines[0] for ln in lines):
        raw = lines[0]
    else:
        raw = " ".join(lines)
    raw = re.sub(r"\s*\.\s*", ".", raw)
    raw = re.sub(r"\s+", " ", raw)
    parts = raw.split(" ")
    if len(parts) <= 3:
        return raw
    return " ".join(parts[:3]) + "." + ".".join(parts[3:])


def _parse_schedules_csv(csv_path: str) -> dict:
    totals = defaultdict(float)
    headers = []
    keynote_col = qty_col = None
    in_schedule = False
    saw_valid_schedule = False
    current_schedule = None
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
                current_schedule = first.strip("# ").strip()
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
                        "count" in hl or
                        "length" in hl or
                        "area" in hl or
                        "volume" in hl or
                        "perimeter" in hl or
                        "value" in hl or
                        "cantidad" in hl or
                        "quantity" in hl or
                        "qty" in hl
                    ):
                        qty_col = i
                if keynote_col is None or qty_col is None:
                    headers = []
                    keynote_col = qty_col = None
                    in_schedule = False
                    continue
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
            totals[_normalize_csi_key(keynote)] += qty
    if not saw_valid_schedule:
        return {}
    return dict(totals)


def _build_import_report(obra_id: str, csv_path: str) -> dict:
    """Genera un reporte de cruce CSI entre el CSV y la obra activa."""
    totals = _parse_schedules_csv(csv_path)

    db = SessionLocal()
    try:
        obra = db.query(Presupuesto).filter(Presupuesto.id == obra_id).first()
        if not obra:
            return {"ok": False, "error": f"Obra {obra_id} no encontrada"}

        partidas = db.query(Partida).join(Capitulo).filter(
            Capitulo.presupuesto_id == obra.id
        ).all()

        partidas_by_key = defaultdict(list)
        for p in partidas:
            partidas_by_key[_normalize_csi_key(p.clave_csi)].append(p)

        rows = []
        matched_csv = 0
        matched_rows = 0
        for csv_key in sorted(totals.keys()):
            candidates = partidas_by_key.get(csv_key, [])
            matched = bool(candidates)
            if matched:
                matched_csv += 1
                matched_rows += len(candidates)
            rows.append({
                "csv_key": csv_key,
                "csv_qty": math.ceil(totals[csv_key]),
                "matched": matched,
                "matched_count": len(candidates),
                "db_keys": [p.clave_csi for p in candidates[:5]],
            })

        unmatched_csv = [row["csv_key"] for row in rows if not row["matched"]]
        unmatched_db = [p.clave_csi for p in partidas if _normalize_csi_key(p.clave_csi) not in totals]

        return {
            "ok": True,
            "csv_path": csv_path,
            "csv_keynotes": len(totals),
            "matched_csv": matched_csv,
            "matched_rows": matched_rows,
            "unmatched_csv": unmatched_csv[:30],
            "unmatched_count": len(unmatched_csv),
            "unmatched_db_count": len(unmatched_db),
            "rows": rows,
        }
    finally:
        db.close()


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
        partidas_by_key = defaultdict(list)
        for p in partidas:
            key = _normalize_csi_key(p.clave_csi)
            bd_keys.add(key)
            partidas_by_key[key].append(p)

        matched_keys = set()
        for key, qty_value in totals.items():
            candidates = partidas_by_key.get(key, [])
            if not candidates:
                continue
            qty = math.ceil(float(qty_value or 0))
            matched_keys.add(key)
            for p in candidates:
                p.revit_q = qty
                p.cantidad = qty  # sync para cálculo de total
                matched += 1

        for p in partidas:
            if _normalize_csi_key(p.clave_csi) not in matched_keys:
                p.revit_q = 0
                p.cantidad = 0
                zeroed += 1

        # Recalcular totales por partida
        sobrecosto = float(obra.config.sobrecosto) if (obra.config and obra.config.sobrecosto is not None) else 20.0
        for p in partidas:
            recalcular_partida(p, sobrecosto)

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
