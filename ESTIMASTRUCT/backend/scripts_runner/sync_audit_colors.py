"""Push the CSI audit result (Revit vs catalog, from audit_keynotes.py) into
Partida.color_tipo colors. Semántica canónica (Director, 2026-08-01):
  verde  = asignado en Revit a una familia y coincide con el catálogo (GREEN)
  rojo   = CSI SI aparece en Revit pero con conflicto/mismatch (visto en el
           audit, cero filas GREEN para ese CSI)
  rosa   = NO asignado en Revit (CSI del catálogo que nunca aparece en el
           audit — ni GREEN ni RED)
  amarillo = depende de labor manual — eje ajeno al audit, nunca lo toca este script
  azul   = manual, otra categorización del Director — nunca lo toca este script
`blanco` queda retirado del vocabulario activo: fichas/partidas que lo tengan
se reclasifican a rosa/rojo/verde en la próxima corrida (no es un color manual
a preservar).

**Preserva colores manuales (2026-07-08):** si una ficha ya tiene amarillo/azul
(colores fuera del vocabulario del audit, puestos a mano por el Director para
otra categorización, ej. dependencias), NO se pisa. Antes (2026-07-07) esto
pisaba TODO sin excepción y se comió 9 fichas rosa puestas a mano en la misma
sesión — restauradas a mano desde backup. Ver gotcha en
project_audit_keynotes_v12.md. **rosa ya NO se preserva como manual** (2026-08-01):
pasó a ser parte del vocabulario propio del audit (= no asignado en Revit).
BACK UP fichas_v1.2*.json antes de correr esto (paso manual, este script no
lo hace solo).

Writes to:
  - fichas_v1.2.json / fichas_v1.2.live.json (catalog, color_tipo field)
  - Partida.color_tipo en Postgres (estimastruct DB via backend.db.SessionLocal,
    2026-08-01 -- antes escribia a estimacion.db SQLite legacy, quedo huerfano
    de la migracion 2026-07-20 y no tocaba la obra real), matched by
    normalized CSI (same _normalize_csi_key as import_quantities.py)

Usage: python sync_audit_colors.py <obra_id>
"""
import json
import os
import re
import sys
import csv
from collections import defaultdict

from backend.db import SessionLocal
from backend.models import Presupuesto, Capitulo, Partida

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
    """normalized_csi -> 'verde' si AL MENOS UN objeto keyeado (type/material/
    instance) para ese CSI salio GREEN en el audit. 'rojo' si el CSI aparece
    en el audit pero NUNCA en GREEN (solo RED — conflicto/mismatch). Un CSI
    que no aparece en absoluto en el audit = 'rosa' (nunca asignado en Revit),
    decidido en sync() comparando contra el universo de CSI del catalogo."""
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
    red_csi = seen_csi - green_csi
    return green_csi, red_csi


def _classify(key, green_csi, red_csi):
    if key in green_csi:
        return "verde"
    if key in red_csi:
        return "rojo"
    return "rosa"


def sync(obra_id):
    green_csi, red_csi = load_audit_status()
    print("CSI confirmados verde (>=1 instancia OK): {}".format(len(green_csi)))
    print("CSI con conflicto (visto en Revit, 0 GREEN): {}".format(len(red_csi)))

    # --- Catalog fichas ---
    with open(FICHA_PATH, encoding="utf-8") as f:
        fichas = json.load(f)

    AUDIT_COLORS = {"verde", "rojo", "rosa", "blanco", None, ""}

    counts = {"verde": 0, "rojo": 0, "rosa": 0}
    preserved_manual = 0
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        key = normalize_csi_key(ficha.get("csi", ""))
        current_color = ficha.get("color_tipo")
        if current_color not in AUDIT_COLORS:
            # amarillo/azul — manual, fuera del vocabulario del audit — preservar
            preserved_manual += 1
            continue
        color = _classify(key, green_csi, red_csi)
        ficha["color_tipo"] = color
        counts[color] += 1

    for target in (FICHA_PATH, LIVE_PATH):
        with open(target, "w", encoding="utf-8") as f:
            json.dump(fichas, f, ensure_ascii=False, indent=2)

    print("Catálogo V1.2: {} verde, {} rojo, {} rosa, {} manual preservado (de {} fichas)".format(
        counts["verde"], counts["rojo"], counts["rosa"], preserved_manual, len(fichas)))

    # --- Obra Partida (Postgres) ---
    db = SessionLocal()
    try:
        obra = db.query(Presupuesto).filter(Presupuesto.id == obra_id).first()
        if not obra:
            print("Obra {} no encontrada en Postgres".format(obra_id))
            return
        partidas = db.query(Partida).join(Capitulo).filter(
            Capitulo.presupuesto_id == obra_id
        ).all()

        obra_counts = {"verde": 0, "rojo": 0, "rosa": 0}
        obra_preserved = 0
        for p in partidas:
            current_color = p.color_tipo
            if current_color not in AUDIT_COLORS:
                obra_preserved += 1
                continue
            key = normalize_csi_key(p.clave_csi)
            color = _classify(key, green_csi, red_csi)
            p.color_tipo = color
            obra_counts[color] += 1

        db.commit()
    finally:
        db.close()

    print("Obra {}: {} partidas -> {} verde, {} rojo, {} rosa, {} manual preservado".format(
        obra_id, len(partidas), obra_counts["verde"], obra_counts["rojo"],
        obra_counts["rosa"], obra_preserved))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python sync_audit_colors.py <obra_id>")
        sys.exit(1)
    sync(sys.argv[1])
