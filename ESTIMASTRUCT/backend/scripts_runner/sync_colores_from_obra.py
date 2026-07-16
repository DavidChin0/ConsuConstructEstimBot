"""Copy Partida.color_tipo from a live obra (project) into the EstimaStruct V1.2
catalog fichas, matched by normalized CSI, so the catalog itself can be color-audited
(green/pink/yellow/blue per Director's per-partida coloring convention) without
opening a specific project.

Read-only against the obra (SQLite); writes only to the V1.2 fichas JSON (both
canonical + .live, mirroring routers/bases.py::_write_fichas). Always back up the
fichas files before running this (see fichas_v1.2*.bak_colores_<timestamp>).

Usage: python sync_colores_from_obra.py <obra_id>
"""
import json
import os
import re
import sys
import sqlite3
from collections import Counter

DB_PATH = r"C:\EstimaStruct\data\estimacion.db"
FICHAS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas"
FICHA_PATH = os.path.join(FICHAS_DIR, "fichas_v1.2.json")
LIVE_PATH = os.path.join(FICHAS_DIR, "fichas_v1.2.live.json")


def normalize_csi_key(key):
    """Same normalization as scripts_runner/import_quantities.py::_normalize_csi_key."""
    if not key:
        return ""
    raw = str(key).replace("_x000D_", "").strip()
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


def load_partida_colors(obra_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.clave_csi, p.color_tipo
        FROM partida p
        JOIN capitulo c ON p.capitulo_id = c.id
        WHERE c.presupuesto_id = ?
        """,
        (obra_id,),
    )
    rows = cur.fetchall()
    conn.close()
    by_csi = {}
    for r in rows:
        key = normalize_csi_key(r["clave_csi"])
        if key:
            by_csi[key] = r["color_tipo"] or "blanco"
    return by_csi, len(rows)


def sync(obra_id):
    colors_by_csi, n_partidas = load_partida_colors(obra_id)
    print("Obra: {} partidas leídas, {} claves CSI únicas".format(n_partidas, len(colors_by_csi)))
    print("Distribución de colores en la obra:", Counter(colors_by_csi.values()))

    with open(FICHA_PATH, encoding="utf-8") as f:
        fichas = json.load(f)

    updated = 0
    changed_color = 0
    unmatched_fichas = []
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        key = normalize_csi_key(ficha.get("csi", ""))
        color = colors_by_csi.get(key)
        if color is None:
            unmatched_fichas.append(ficha.get("csi"))
            continue
        old = ficha.get("color_tipo")
        ficha["color_tipo"] = color
        updated += 1
        if old != color:
            changed_color += 1

    unmatched_obra = [csi for csi in colors_by_csi if csi not in
                      {normalize_csi_key(f.get("csi", "")) for f in fichas if isinstance(f, dict)}]

    for target in (FICHA_PATH, LIVE_PATH):
        with open(target, "w", encoding="utf-8") as f:
            json.dump(fichas, f, ensure_ascii=False, indent=2)

    print("")
    print("Fichas actualizadas con color: {} de {}".format(updated, len(fichas)))
    print("Fichas SIN match en la obra (quedan sin color/'color' no seteado): {}".format(len(unmatched_fichas)))
    if unmatched_fichas:
        print("  ->", unmatched_fichas[:20])
    print("CSI de la obra que no existen en catálogo: {}".format(len(unmatched_obra)))
    if unmatched_obra:
        print("  ->", unmatched_obra[:20])
    print("")
    print("Escrito: {} y {}".format(FICHA_PATH, LIVE_PATH))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python sync_colores_from_obra.py <obra_id>")
        sys.exit(1)
    sync(sys.argv[1])
