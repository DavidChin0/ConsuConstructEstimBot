"""validate_units.py — Cruza CSI del schedule CSV contra unidades en PG (catálogo v1.3).

Detecta mismatches entre la unidad Revit (inferida del schedule) y la unidad
en la partida PG, para que el Director apruebe o corrija antes de import_quantities.

Uso:
  python -m backend.scripts_runner.validate_units <csv_path>
  python -m backend.scripts_runner.validate_units  (usa el schedule más reciente en S5_schedules)

Output: tabla consola — OK / WARN / MISS por CSI.

Regla de inferencia de unidad desde schedule:
  T04Wall Material Takeoff → m2
  T02Pisos                 → m2
  T01Material Cielo Falso  → m2
  C10_connections          → pza
  schedules genérico       → depende de la columna cantidad (area→m2, count→pza, length→ml)
"""
import os, re, sys, csv, glob
from collections import defaultdict

# ─── paths ─────────────────────────────────────────────────────────────────
_THIS   = os.path.dirname(os.path.abspath(__file__))
_REPO   = os.path.abspath(os.path.join(_THIS, "..", ".."))
_S5_DIR = os.path.join(_REPO, os.pardir, os.pardir, os.pardir,
                       "OneDrive", "Bots", "Estimbot", "EXPORTS", "S5_schedules")
# Ruta absoluta alternativa si la relativa falla
_S5_ABS = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"

_SEC    = r"D:\Secrets\postgres_credentials.txt"
_PG_HOST, _PG_PORT, _PG_DB, _PG_USER = "127.0.0.1", 5432, "estimastruct", "postgres"

_QTY_COL_UNIT = {
    "area":       "m2",
    "length":     "ml",
    "perimeter":  "ml",
    "volume":     "m3",
    "count":      "pza",
    "quantity":   "pza",
    "qty":        "pza",
    "value":      "global",
    "cantidad":   None,  # ambiguous without context
}

_SCHEDULE_UNIT_HINTS = {
    "t04": "m2",
    "t02": "m2",
    "t01": "m2",
    "c10": "pza",
}


def _latest_csv():
    s5 = _S5_ABS if os.path.isdir(_S5_ABS) else _S5_DIR
    files = sorted(glob.glob(os.path.join(s5, "schedules_*.csv")))
    return files[-1] if files else None


def _pg_password():
    try:
        for line in open(_SEC, encoding="utf-8"):
            if line.strip().startswith("password="):
                return line.strip()[9:]
    except Exception:
        pass
    return None


def _load_pg_units():
    """Returns {csi_norm: unidad} from partida table."""
    import asyncio, asyncpg

    async def _fetch(pw):
        conn = await asyncpg.connect(
            host=_PG_HOST, port=_PG_PORT,
            database=_PG_DB, user=_PG_USER, password=pw
        )
        rows = await conn.fetch("""
            SELECT DISTINCT ON (clave_csi) clave_csi, unidad
            FROM partida
            WHERE clave_csi IS NOT NULL AND clave_csi != ''
            ORDER BY clave_csi, precio_unitario DESC NULLS LAST
        """)
        await conn.close()
        return {_norm(r["clave_csi"]): (r["unidad"] or "").strip() for r in rows}

    pw = _pg_password()
    if not pw:
        raise RuntimeError("No PG password in " + _SEC)
    return asyncio.run(_fetch(pw))


def _norm(key):
    if not key:
        return ""
    raw = str(key).replace("_x000D_", "").strip()
    raw = re.sub(r"\s*\.\s*", ".", raw)
    raw = re.sub(r"\s+", " ", raw)
    parts = raw.split(" ")
    if len(parts) <= 3:
        return raw
    return " ".join(parts[:3]) + "." + ".".join(parts[3:])


def _infer_unit_from_col(col_name, schedule_name):
    sched_lower = (schedule_name or "").lower()
    for hint, unit in _SCHEDULE_UNIT_HINTS.items():
        if hint in sched_lower:
            return unit
    col_lower = (col_name or "").lower()
    for kw, unit in _QTY_COL_UNIT.items():
        if kw in col_lower:
            return unit
    return None


def validate(csv_path):
    pg_units = _load_pg_units()

    results = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = []
        keynote_col = qty_col = None
        in_schedule = False
        current_schedule = None
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
                    hl = h.lower()
                    if keynote_col is None and ("keynote" in hl or hl.startswith("csi")):
                        keynote_col = i
                    if qty_col is None:
                        for kw in _QTY_COL_UNIT:
                            if kw in hl:
                                qty_col = i
                                break
                if keynote_col is None:
                    headers = []
                    in_schedule = False
                continue
            keynote = row[keynote_col].strip() if keynote_col < len(row) else ""
            if not keynote:
                continue
            csi_n = _norm(keynote)
            inferred = _infer_unit_from_col(
                headers[qty_col] if qty_col is not None else "",
                current_schedule
            )
            pg_unit = pg_units.get(csi_n)
            if pg_unit is None:
                status = "MISS"
            elif inferred and pg_unit.lower() != inferred.lower():
                status = "WARN"
            else:
                status = "OK"
            results.append({
                "csi":       csi_n,
                "schedule":  current_schedule,
                "inferred":  inferred or "?",
                "pg_unit":   pg_unit or "NOT IN PG",
                "status":    status,
            })

    seen = set()
    deduped = []
    for r in results:
        k = r["csi"]
        if k not in seen:
            seen.add(k)
            deduped.append(r)

    ok   = [r for r in deduped if r["status"] == "OK"]
    warn = [r for r in deduped if r["status"] == "WARN"]
    miss = [r for r in deduped if r["status"] == "MISS"]

    print(f"\nValidación de unidades — {os.path.basename(csv_path)}")
    print(f"  OK:   {len(ok)}")
    print(f"  WARN: {len(warn)}  ← unidad Revit ≠ PG (revisar antes de import)")
    print(f"  MISS: {len(miss)}  ← CSI no en catálogo PG v1.3")
    if warn:
        print("\n  WARNs:")
        for r in warn:
            print(f"    {r['csi']:<30} inferred={r['inferred']:<6} pg={r['pg_unit']}")
    if miss:
        print("\n  MISSes:")
        for r in miss:
            print(f"    {r['csi']}")
    return {"ok": len(ok), "warn": len(warn), "miss": len(miss), "rows": deduped}


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else _latest_csv()
    if not csv_path or not os.path.exists(csv_path):
        print("No CSV encontrado. Pasar ruta como argumento.")
        sys.exit(1)
    validate(csv_path)
