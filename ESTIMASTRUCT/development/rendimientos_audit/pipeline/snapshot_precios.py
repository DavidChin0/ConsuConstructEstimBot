#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
snapshot_precios.py  —  goal-21170 (rol estimastruct)

Paso 1 de la secuencia obligatoria: INVENTARIO + HASH de solo lectura de las
tablas de precios/catalogo antes de cualquier escritura de rendimientos.

No escribe nada en la BD. Produce:
  - data/precios_snapshot_<ts>.json   : hash SHA256 por tabla + fila totales
  - data/precios_snapshot_latest.json : alias "latest" para comparar despues

Tablas de precios (catalogo vivo) a proteger con hash de contenido completo:
  partida, insumo_partida, recurso, capitulo, presupuesto
Ademas se hashean TODAS las tablas para el invariante global (cero cambios).

Correr: D:\\LLM\\python\\python.exe snapshot_precios.py
"""
import os, sys, json, sqlite3, hashlib, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DB = os.getenv("ESTIMA_DB_PATH", r"D:\EstimaStruct\data\estimacion.db")

PRICE_TABLES = ["partida", "insumo_partida", "recurso", "capitulo", "presupuesto"]


def table_hash(con, t):
    cur = con.cursor()
    cur.execute(f'SELECT * FROM [{t}]')
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    h = hashlib.sha256()
    h.update(("|".join(cols)).encode("utf-8", "replace"))
    for r in rows:
        line = "|".join("" if v is None else str(v) for v in r)
        h.update(line.encode("utf-8", "replace"))
        h.update(b"\n")
    return h.hexdigest(), len(rows), cols


def main():
    if not os.path.exists(DB):
        sys.exit(f"ERROR: no existe la BD canonica: {DB}")
    con = sqlite3.connect(DB)
    cur = con.cursor()
    all_tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    snap = {
        "db_path": DB,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "tool": "snapshot_precios.py goal-21170",
        "tables": {},
        "price_tables": {},
    }
    for t in all_tables:
        h, n, cols = table_hash(con, t)
        snap["tables"][t] = {"rows": n, "sha256": h}
        if t in PRICE_TABLES:
            snap["price_tables"][t] = {"rows": n, "sha256": h, "columns": cols}
    snap["total_tables"] = len(all_tables)
    snap["price_invariant"] = {
        "rows_sum": sum(snap["price_tables"][t]["rows"] for t in PRICE_TABLES),
        "hash_concat": hashlib.sha256(
            "|".join(snap["price_tables"][t]["sha256"] for t in PRICE_TABLES).encode()).hexdigest(),
    }
    con.close()
    os.makedirs(DATA, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_ts = os.path.join(DATA, f"precios_snapshot_{ts}.json")
    out_latest = os.path.join(DATA, "precios_snapshot_latest.json")
    for p in (out_ts, out_latest):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
    print(f"[SNAP] DB               : {DB}")
    print(f"[SNAP] tablas           : {snap['total_tables']}")
    print(f"[SNAP] tablas de precio : {list(snap['price_tables'].keys())}")
    print(f"[SNAP] invariante precio: rows={snap['price_invariant']['rows_sum']} "
          f"hash={snap['price_invariant']['hash_concat']}")
    print(f"[SNAP] snapshot ts      : {out_ts}")
    print(f"[SNAP] snapshot latest  : {out_latest}")


if __name__ == "__main__":
    main()