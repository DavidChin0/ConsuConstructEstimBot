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


def _raw_kind(raw: str) -> str:
    """Unidad que Revit escribe junto al valor: '4.40 m'->mL, '62 m²'->m2, '1'->pza."""
    r = raw.strip().lower()
    if re.search(r"m\s*[²2]\s*$", r):
        return "m2"
    if re.search(r"m\s*[³3]\s*$", r):
        return "m3"
    if re.search(r"\d\s*m\s*$", r):
        return "mL"
    return "pza"


def _unit_kind(unidad: str):
    """Unidad de la partida -> mismo vocabulario que _raw_kind; None si no es comparable."""
    u = (unidad or "").strip().lower().replace("²", "2").replace("³", "3")
    return {"m2": "m2", "m3": "m3", "ml": "mL", "m": "mL",
            "pza": "pza", "und": "pza", "unidad": "pza"}.get(u)


def _pick_qty(by_kind: dict, unidad: str):
    """Devuelve (cantidad, None) o (None, motivo). Sin coincidencia de unidad NO se importa."""
    want = _unit_kind(unidad)
    if want in by_kind:
        return by_kind[want], None
    if want is None and len(by_kind) == 1:  # unidad no comparable (lance, kg...) y Revit da una sola
        return next(iter(by_kind.values())), None
    return None, f"partida en '{unidad}' pero Revit trae {sorted(by_kind)}"


def _parse_schedules_csv(csv_path: str) -> dict:
    """{keynote: {unidad_revit: suma}} -- lee TODAS las columnas de cantidad."""
    totals = defaultdict(lambda: defaultdict(float))
    headers = []
    keynote_col = None
    qty_cols = []
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
                keynote_col = None
                qty_cols = []
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
                    if (
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
                        qty_cols.append(i)
                if keynote_col is None or not qty_cols:
                    headers = []
                    keynote_col = None
                    qty_cols = []
                    in_schedule = False
                    continue
                saw_valid_schedule = True
                continue
            if keynote_col is None or not qty_cols:
                continue
            keynote = row[keynote_col].strip() if keynote_col < len(row) else ""
            if not keynote:
                continue
            for qc in qty_cols:
                qty_raw = row[qc].strip() if qc < len(row) else ""
                qty_clean = re.sub(r"[^\d\.\,]", "", qty_raw).replace(",", ".")
                if not qty_clean:
                    continue
                try:
                    qty = float(qty_clean)
                except ValueError:
                    continue
                totals[_normalize_csi_key(keynote)][_raw_kind(qty_raw)] += qty
    if not saw_valid_schedule:
        return {}
    return {k: dict(v) for k, v in totals.items()}


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
        unit_mismatch = []
        for csv_key in sorted(totals.keys()):
            candidates = partidas_by_key.get(csv_key, [])
            matched = bool(candidates)
            if matched:
                matched_csv += 1
                matched_rows += len(candidates)
            qty = None
            for p in candidates:
                q, why = _pick_qty(totals[csv_key], p.unidad)
                if why:
                    unit_mismatch.append({"csi": csv_key, "unidad_partida": p.unidad, "motivo": why})
                elif qty is None:
                    qty = q
            rows.append({
                "csv_key": csv_key,
                "csv_qty": math.ceil(qty) if qty is not None else None,
                "csv_units": {k: round(v, 2) for k, v in totals[csv_key].items()},
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
            "unit_mismatch": unit_mismatch,
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
        unit_mismatch = []
        for key, by_kind in totals.items():
            candidates = partidas_by_key.get(key, [])
            if not candidates:
                continue
            matched_keys.add(key)  # tiene contraparte: no se pone en cero aunque la unidad no coincida
            for p in candidates:
                value, why = _pick_qty(by_kind, p.unidad)
                if why:  # unidad Revit != unidad partida: NO se escribe, se deja el valor anterior
                    unit_mismatch.append(f"{p.clave_csi}: {why}")
                    continue
                qty = math.ceil(float(value or 0))
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
            "unit_mismatch": unit_mismatch,
            "message": f"✓ Cantidades importadas: {matched} actualizadas, {zeroed} en cero, {len(unmatched_csv)} keynotes del CSV sin contraparte en la obra"
                       + (f", {len(unit_mismatch)} OMITIDAS por unidad distinta: " + "; ".join(unit_mismatch[:8]) if unit_mismatch else ""),
        }
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python import_quantities.py <obra_id> <csv_path>")
        sys.exit(1)
    res = import_quantities(sys.argv[1], sys.argv[2])
    # cp1252 no soporta ✓ (U+2713) — usar ASCII
    msg = res.get("message") or res.get("error") or ""
    msg = msg.replace("\u2713", "[OK]").replace("\u2717", "[ERR]")
    print(msg)
    sys.exit(0 if res.get("ok") else 1)
