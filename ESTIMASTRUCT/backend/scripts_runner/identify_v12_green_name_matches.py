"""Cruza CSI verdes del audit MCP Revit contra EstimaStruct v1.2.

Objetivo:
- detectar CSI que ya están GREEN en `audit_keynotes_report.csv`
- pero todavía NO figuran como verde en la BD SQLite
- y dejar evidencia de su match por nombre contra fichas v1.2

Salida:
- `audit_green_name_match_v12_YYYYMMDD.csv`
- `audit_green_name_match_v12_YYYYMMDD.md`
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher


AUDIT_CSV = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP\audit_keynotes_report.csv"
DB_PATH = r"C:\EstimaStruct\data\estimacion.db"
FICHAS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\Template2_Updated\v1.2\fichas"
OUT_DIR = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP"


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


def normalize_text(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def text_ratio(a, b):
    na = normalize_text(a)
    nb = normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def load_fichas():
    live = os.path.join(FICHAS_DIR, "fichas_v1.2.live.json")
    canon = os.path.join(FICHAS_DIR, "fichas_v1.2.json")
    candidates = [p for p in (live, canon) if os.path.exists(p)]
    path = max(candidates, key=os.path.getmtime)
    with open(path, encoding="utf-8") as f:
        fichas = json.load(f)
    clean = [x for x in fichas if isinstance(x, dict)]
    by_csi = {normalize_csi_key(x.get("csi", "")): x for x in clean if x.get("csi")}
    return clean, by_csi, path


def load_db_state():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT clave_csi, descripcion, type_mark, color_tipo
        FROM partida
        """
    )
    rows = cur.fetchall()
    conn.close()
    by_csi = defaultdict(list)
    green_csi = set()
    for row in rows:
        key = normalize_csi_key(row["clave_csi"])
        if not key:
            continue
        by_csi[key].append(dict(row))
        if (row["color_tipo"] or "").lower() == "verde":
            green_csi.add(key)
    return rows, by_csi, green_csi


def load_audit_green():
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    green_rows = [r for r in rows if r.get("status") == "GREEN" and r.get("keynote")]
    by_csi = defaultdict(list)
    for row in green_rows:
        by_csi[normalize_csi_key(row["keynote"])].append(row)
    return green_rows, by_csi


def pick_best_name(csi, audit_rows, ficha):
    audit_names = []
    for row in audit_rows:
        for candidate in (row.get("keynote_text"), row.get("ficha_desc"), row.get("type"), row.get("family")):
            if candidate and normalize_text(candidate):
                audit_names.append(candidate)
    audit_names = list(dict.fromkeys(audit_names))

    ficha_desc = ficha.get("descripcion", "") if ficha else ""
    best_name = ""
    best_ratio = 0.0
    for name in audit_names:
        ratio = text_ratio(name, ficha_desc)
        if ratio > best_ratio:
            best_ratio = ratio
            best_name = name
    return best_name, best_ratio


def build():
    fichas, fichas_by_csi, ficha_path = load_fichas()
    _, db_by_csi, db_green_csi = load_db_state()
    _, audit_green_by_csi = load_audit_green()

    target_csis = sorted(csi for csi in audit_green_by_csi if csi not in db_green_csi)
    ts = datetime.now().strftime("%Y%m%d")
    csv_path = os.path.join(OUT_DIR, f"audit_green_name_match_v12_{ts}.csv")
    md_path = os.path.join(OUT_DIR, f"audit_green_name_match_v12_{ts}.md")

    rows_out = []
    for csi in target_csis:
        audit_rows = audit_green_by_csi[csi]
        ficha = fichas_by_csi.get(csi)
        best_name, best_ratio = pick_best_name(csi, audit_rows, ficha or {})
        categories = Counter((r.get("category") or "").strip() for r in audit_rows if (r.get("category") or "").strip())
        types = Counter((r.get("type") or "").strip() for r in audit_rows if (r.get("type") or "").strip())
        db_rows = db_by_csi.get(csi, [])

        rows_out.append({
            "csi": csi,
            "audit_green_rows": len(audit_rows),
            "audit_categories": " | ".join(f"{k} ({v})" for k, v in categories.most_common(3)),
            "audit_types": " | ".join(f"{k} ({v})" for k, v in types.most_common(3)),
            "audit_name_probe": best_name,
            "v12_codigo": ficha.get("codigo", "") if ficha else "",
            "v12_descripcion": ficha.get("descripcion", "") if ficha else "",
            "v12_color_tipo": ficha.get("color_tipo", "") if ficha else "",
            "name_similarity": f"{best_ratio:.3f}",
            "db_partidas_same_csi": len(db_rows),
            "db_green_same_csi": sum(1 for r in db_rows if (r.get("color_tipo") or "").lower() == "verde"),
            "resolution_hint": (
                "SYNC_V12_COLOR"
                if ficha and best_ratio >= 0.82
                else "REVIEW_NAME"
                if ficha
                else "MISSING_IN_V12"
            ),
        })

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()) if rows_out else [
            "csi", "audit_green_rows", "audit_categories", "audit_types",
            "audit_name_probe", "v12_codigo", "v12_descripcion", "v12_color_tipo",
            "name_similarity", "db_partidas_same_csi", "db_green_same_csi", "resolution_hint",
        ])
        writer.writeheader()
        writer.writerows(rows_out)

    sync_ready = [r for r in rows_out if r["resolution_hint"] == "SYNC_V12_COLOR"]
    review = [r for r in rows_out if r["resolution_hint"] != "SYNC_V12_COLOR"]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Audit GREEN -> Match Name v1.2\n\n")
        f.write(f"- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- Fichas fuente: `{ficha_path}`\n")
        f.write(f"- CSI GREEN en audit pero no verdes en DB: `{len(rows_out)}`\n")
        f.write(f"- Listos para sync por nombre/CSI en v1.2: `{len(sync_ready)}`\n")
        f.write(f"- Requieren revisión: `{len(review)}`\n\n")
        if sync_ready:
            f.write("## Sync Ready\n\n")
            for row in sync_ready:
                f.write(
                    f"- `{row['csi']}` | `{row['v12_codigo']}` | "
                    f"{row['v12_descripcion']} | sim `{row['name_similarity']}`\n"
                )
            f.write("\n")
        if review:
            f.write("## Review\n\n")
            for row in review:
                f.write(
                    f"- `{row['csi']}` | `{row['v12_codigo']}` | "
                    f"{row['v12_descripcion']} | sim `{row['name_similarity']}` | "
                    f"hint `{row['resolution_hint']}`\n"
                )

    return {
        "csv_path": csv_path,
        "md_path": md_path,
        "target_csi": len(rows_out),
        "sync_ready": len(sync_ready),
        "review": len(review),
    }


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, ensure_ascii=False, indent=2))
