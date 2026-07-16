"""Aplica a SQLite los CSI verdes validados por audit-mcp Revit para v1.2.

Scope deliberadamente acotado:
- lee el reporte `audit_green_name_match_v12_YYYYMMDD.csv`
- actualiza solo partidas con esos CSI en las obras objetivo
- fuerza `color_tipo='verde'`
- opcionalmente marca `config_presupuesto.template_version='v1.2'`
- genera CSV antes/después para cotejo en EstimaStruct
"""
from __future__ import annotations

import csv
import os
import shutil
import sqlite3
from datetime import datetime


DB_PATH = r"C:\EstimaStruct\data\estimacion.db"
REPORT_CSV = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP\audit_green_name_match_v12_20260716.csv"
OUT_DIR = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP"

TARGET_OBRAS = {
    "283ef660-d3aa-4fa8-a3c0-3b30c54a54ed": "XX",
    "92de239d-e672-4f21-8aba-c38ed894cb9c": "CC132 — Camilo Almendárez (Checkers)",
    "1e472efb-e44f-4759-9ebe-81f590938a49": "CC132 — Camilo Almendárez (Checkers) (copia)",
}


def load_target_csis():
    with open(REPORT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [row["csi"] for row in rows if row.get("resolution_hint") == "SYNC_V12_COLOR"]


def fetch_rows(conn, csis):
    placeholders = ",".join("?" for _ in csis)
    sql = f"""
        SELECT
            p.id AS obra_id,
            p.nombre AS obra_nombre,
            cfg.template_version AS template_version,
            pa.id AS partida_id,
            pa.clave_csi,
            pa.type_mark,
            pa.descripcion,
            pa.color_tipo
        FROM partida pa
        JOIN capitulo c ON pa.capitulo_id = c.id
        JOIN presupuesto p ON c.presupuesto_id = p.id
        LEFT JOIN config_presupuesto cfg ON cfg.presupuesto_id = p.id
        WHERE p.id IN ({",".join("?" for _ in TARGET_OBRAS)})
          AND pa.clave_csi IN ({placeholders})
        ORDER BY p.nombre, pa.clave_csi, pa.descripcion
    """
    params = list(TARGET_OBRAS.keys()) + list(csis)
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def write_csv(path, rows):
    fieldnames = [
        "obra_id", "obra_nombre", "template_version", "partida_id",
        "clave_csi", "type_mark", "descripcion", "color_tipo",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def apply():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DB_PATH}.bak_v12greens_{ts}"
    shutil.copy2(DB_PATH, backup_path)

    csis = load_target_csis()
    conn = sqlite3.connect(DB_PATH)
    before_rows = fetch_rows(conn, csis)
    before_csv = os.path.join(OUT_DIR, f"v12_green_db_before_{ts}.csv")
    write_csv(before_csv, before_rows)

    changed = 0
    for obra_id in TARGET_OBRAS:
        conn.execute(
            "UPDATE config_presupuesto SET template_version='v1.2' WHERE presupuesto_id=?",
            (obra_id,),
        )

    for row in before_rows:
        if (row.get("color_tipo") or "").lower() != "verde":
            conn.execute(
                "UPDATE partida SET color_tipo='verde' WHERE id=?",
                (row["partida_id"],),
            )
            changed += 1

    conn.commit()
    after_rows = fetch_rows(conn, csis)
    after_csv = os.path.join(OUT_DIR, f"v12_green_db_after_{ts}.csv")
    write_csv(after_csv, after_rows)
    conn.close()

    diff_csv = os.path.join(OUT_DIR, f"v12_green_db_diff_{ts}.csv")
    with open(diff_csv, "w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "obra_nombre", "clave_csi", "type_mark", "descripcion",
            "color_before", "color_after", "template_after",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        after_by_id = {row["partida_id"]: row for row in after_rows}
        for before in before_rows:
            after = after_by_id[before["partida_id"]]
            if (before.get("color_tipo") or "") != (after.get("color_tipo") or "") or (
                before.get("template_version") or ""
            ) != (after.get("template_version") or ""):
                writer.writerow({
                    "obra_nombre": before["obra_nombre"],
                    "clave_csi": before["clave_csi"],
                    "type_mark": before["type_mark"],
                    "descripcion": before["descripcion"],
                    "color_before": before["color_tipo"],
                    "color_after": after["color_tipo"],
                    "template_after": after["template_version"],
                })

    return {
        "backup_path": backup_path,
        "before_csv": before_csv,
        "after_csv": after_csv,
        "diff_csv": diff_csv,
        "rows_seen": len(before_rows),
        "rows_changed": changed,
        "obras_updated": len(TARGET_OBRAS),
    }


if __name__ == "__main__":
    print(apply())
