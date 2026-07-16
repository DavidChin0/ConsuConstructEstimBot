"""Push the CSI audit result (Revit vs catalog, from audit_keynotes.py) into
Partida.color_tipo colors: verde = at least one Revit instance confirmed this
CSI correct (GREEN in the audit), blanco = not confirmed (no green evidence —
either never modeled with this keynote in Revit, or a mismatch was found).

**Preserva colores manuales (2026-07-08):** si una ficha ya tiene rosa/amarillo/
azul (colores fuera del vocabulario del audit, puestos a mano por el Director
para otra categorización, ej. dependencias), NO se pisa — solo se tocan fichas
en blanco/verde (el vocabulario propio del audit). Antes (2026-07-07) esto
pisaba TODO sin excepción y se comió 9 fichas rosa puestas a mano en la misma
sesión — restauradas a mano desde backup. Ver gotcha en
project_audit_keynotes_v12.md. BACK UP fichas_v1.2*.json y estimacion.db antes
de correr esto de todos modos (por si acaso).

There is no "rojo" value in EstimaStruct's color_tipo CHECK constraint
(allowed: amarillo|verde|azul|rosa|blanco per backend/models.py), so
unconfirmed CSI get "blanco" (neutral/default), not a red equivalent.

Writes to:
  - fichas_v1.2.json / fichas_v1.2.live.json (catalog, color_tipo field)
  - Partida.color_tipo in estimacion.db, for a given obra_id, matched by
    normalized CSI (same _normalize_csi_key as import_quantities.py)

Usage: python sync_audit_colors.py <obra_id>
"""
import json
import os
import re
import sys
import csv
import sqlite3
from collections import defaultdict

DB_PATH = r"C:\EstimaStruct\data\estimacion.db"
FICHAS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas"
FICHA_PATH = os.path.join(FICHAS_DIR, "fichas_v1.2.json")
LIVE_PATH = os.path.join(FICHAS_DIR, "fichas_v1.2.live.json")
AUDIT_CSV = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP\audit_keynotes_report.csv"


def normalize_csi_key(key):
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


def load_audit_status():
    """normalized_csi -> 'verde' if ANY keyed object (type/material/instance) for
    that CSI is GREEN in the audit, else 'blanco'. Considers every row with a
    non-empty keynote regardless of kind (the audit now keys off types + materials,
    not just placed instances)."""
    green_csi = set()
    seen_csi = set()
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            keynote = row.get("keynote")
            if not keynote:
                continue
            key = normalize_csi_key(keynote)
            seen_csi.add(key)
            if row.get("status") == "GREEN":
                green_csi.add(key)
    return green_csi, seen_csi


def sync(obra_id):
    green_csi, seen_csi = load_audit_status()
    print("CSI vistos en auditoría (con keynote): {}".format(len(seen_csi)))
    print("CSI confirmados verde (>=1 instancia OK): {}".format(len(green_csi)))

    # --- Catalog fichas ---
    with open(FICHA_PATH, encoding="utf-8") as f:
        fichas = json.load(f)

    AUDIT_COLORS = {"verde", "blanco", None, ""}

    updated_verde = 0
    updated_blanco = 0
    preserved_manual = 0
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        key = normalize_csi_key(ficha.get("csi", ""))
        current_color = ficha.get("color_tipo")
        if key in green_csi:
            ficha["color_tipo"] = "verde"
            updated_verde += 1
        elif current_color not in AUDIT_COLORS:
            # color manual (rosa/amarillo/azul) fuera del vocabulario del audit — preservar
            preserved_manual += 1
        else:
            ficha["color_tipo"] = "blanco"
            updated_blanco += 1

    for target in (FICHA_PATH, LIVE_PATH):
        with open(target, "w", encoding="utf-8") as f:
            json.dump(fichas, f, ensure_ascii=False, indent=2)

    print("Catálogo V1.2: {} verde, {} blanco, {} manual preservado (de {} fichas)".format(
        updated_verde, updated_blanco, preserved_manual, len(fichas)))

    # --- Obra Partida ---
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id, p.clave_csi, p.color_tipo
        FROM partida p
        JOIN capitulo c ON p.capitulo_id = c.id
        WHERE c.presupuesto_id = ?
        """,
        (obra_id,),
    )
    partidas = cur.fetchall()

    obra_verde = 0
    obra_blanco = 0
    obra_preserved = 0
    for pid, clave_csi, current_color in partidas:
        key = normalize_csi_key(clave_csi)
        if key in green_csi:
            color = "verde"
        elif current_color not in AUDIT_COLORS:
            obra_preserved += 1
            continue
        else:
            color = "blanco"
        cur.execute("UPDATE partida SET color_tipo = ? WHERE id = ?", (color, pid))
        if color == "verde":
            obra_verde += 1
        else:
            obra_blanco += 1

    conn.commit()
    conn.close()

    print("Obra {}: {} partidas -> {} verde, {} blanco, {} manual preservado".format(
        obra_id, len(partidas), obra_verde, obra_blanco, obra_preserved))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python sync_audit_colors.py <obra_id>")
        sys.exit(1)
    sync(sys.argv[1])
