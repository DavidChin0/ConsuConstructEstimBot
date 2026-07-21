"""Build CASE-MAT-001 replacement contract from audit correlations + EstimaStruct catalog.

This script does not write to Revit.
It converts the existing correlation artifacts into a repeatable contract with
three explicit decisions:
  - KEEP
  - REPLACE_SAFE
  - REVIEW_DIRECTOR

Current use:
  CASE-MAT-001 first real iteration, using the 2026-07-16 correlation outputs
  and the live EstimaStruct catalog available in SQLite + fichas JSON.
"""
import csv
import json
import os
import sqlite3
from collections import OrderedDict

STAMP = "20260717"
OUT_DIR = r"D:\OneDrive\Bots\Estimbot\auditorias Revit MCP"
CORRELATION_CSV = os.path.join(
    OUT_DIR,
    "archive",
    "intermediate_20260716",
    "template_complex_correlation_all_20260716.csv",
)
DB_PATH = r"C:\EstimaStruct\data\estimacion.db"
FICHAS_JSON = (
    r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT"
    r"\development\Template2_Updated\v1.2\fichas\fichas_v1.2.live.json"
)
OUT_CSV = os.path.join(OUT_DIR, "case_mat_001_material_contract_20260717.csv")


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def normalize_token(value):
    value = (value or "").strip().lower()
    for old, new in (
        ("á", "a"),
        ("é", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ú", "u"),
        ("ñ", "n"),
        (" ", ""),
        ("-", ""),
        ("_", ""),
        ('"', ""),
        ("'", ""),
        (".", ""),
    ):
        value = value.replace(old, new)
    return value


def load_partida_catalog():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT clave_csi, descripcion, unidad, type_mark
        FROM partida
        WHERE clave_csi IS NOT NULL AND TRIM(clave_csi) <> ''
        ORDER BY clave_csi, descripcion
        """
    ).fetchall()
    conn.close()

    catalog = OrderedDict()
    for row in rows:
        csi = (row["clave_csi"] or "").strip()
        if not csi:
            continue
        bucket = catalog.setdefault(
            csi,
            {
                "csi": csi,
                "descripcion": (row["descripcion"] or "").strip(),
                "unidad": (row["unidad"] or "").strip(),
                "type_mark": (row["type_mark"] or "").strip(),
                "source": "db",
            },
        )
        if not bucket["type_mark"] and row["type_mark"]:
            bucket["type_mark"] = (row["type_mark"] or "").strip()
    return catalog


def load_fichas_catalog():
    data = json.loads(open(FICHAS_JSON, encoding="utf-8").read())
    catalog = OrderedDict()
    for item in data:
        csi = (item.get("csi") or "").strip()
        if not csi:
            continue
        if csi not in catalog:
            catalog[csi] = {
                "csi": csi,
                "descripcion": (item.get("descripcion") or "").strip(),
                "unidad": (item.get("unidad") or "").strip(),
                "type_mark": (item.get("type_mark") or "").strip(),
                "source": "fichas_v1.2.live",
            }
    return catalog


MATERIAL_TO_CSI = {
    normalize_token("CC-Steel Framing"): "05 31 33",
    normalize_token("CC-Plycem"): "09 29 00.6",
    normalize_token("CC-Tablayeso"): "09 29 00",
    normalize_token("CC-DensGlass"): "09 29 00.1",
    normalize_token("CC- DensGlass"): "09 29 00.1",
    normalize_token("CC-R14"): "07 61 13.4",
    normalize_token("CC-BaseSW"): "09 91 13.1",
    normalize_token("CC-PinturaSW"): "09 91 23.2",
    normalize_token("CC-WPC ext"): "07 42 33",
    normalize_token("CC-WPCInt"): "06 86 13",
    normalize_token("CC-Vynil"): "09 29 00.7",
    normalize_token("CC-VinylPVCInt"): "09 29 00.7",
    normalize_token("CC-Ceramica Pared"): "09 30 13.7",
    normalize_token("CC-Fachaleta"): "04 43 13.1",
    normalize_token("CC-Bloque4"): "04 26 00.1",
    normalize_token("CC-Bloque6"): "04 26 00.2",
    normalize_token("CC- Repello"): "04 05 13.1",
    normalize_token("CC - PULIDO"): "04 05 13.2",
    normalize_token("CC-Porcelanato"): "09 30 13.2",
    normalize_token("CC-PisoConcreto"): "03 31 03.2",
    normalize_token("CC-PVC Vinilo"): "09 29 00.2",
    normalize_token("CC - PVC Vinilo"): "09 29 00.2",
    normalize_token("CC-Plafon"): "09 29 00.4",
    normalize_token("CC-Aluzinc"): "07 61 13.1",
    normalize_token("CC-Impermeabilizante"): "07 97 26",
}


IGNORED_TOKENS = {
    "",
    "<empty>",
    "air",
    "default",
    "ccnone",
}


def split_signature(signature):
    if not signature:
        return []
    return [part.strip() for part in str(signature).split("|") if part.strip()]


def extract_material_tokens(row):
    tokens = []
    for chunk in split_signature(row.get("material_signature", "")):
        parts = [part.strip() for part in chunk.split(":")]
        if len(parts) < 2:
            continue
        material = parts[1]
        norm = normalize_token(material)
        if norm in IGNORED_TOKENS:
            continue
        tokens.append(material)
    deduped = []
    seen = set()
    for token in tokens:
        key = normalize_token(token)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token)
    return deduped


def resolve_csis(row):
    csis = []
    if row.get("primary_csi"):
        csis.append(row["primary_csi"].strip())

    unmapped_materials = []
    for token in extract_material_tokens(row):
        mapped = MATERIAL_TO_CSI.get(normalize_token(token))
        if mapped:
            if mapped not in csis:
                csis.append(mapped)
        else:
            unmapped_materials.append(token)
    return csis, unmapped_materials


def lookup_catalog_entries(csis, db_catalog, fichas_catalog):
    matches = []
    missing = []
    for csi in csis:
        entry = db_catalog.get(csi) or fichas_catalog.get(csi)
        if entry:
            matches.append(entry)
        else:
            missing.append(csi)
    return matches, missing


def classify_contract(row, catalog_missing, unmapped_materials):
    corr_decision = (row.get("decision") or "").strip().upper()
    if corr_decision != "AUTO":
        return "REVIEW_DIRECTOR"
    if catalog_missing or unmapped_materials:
        return "REVIEW_DIRECTOR"
    return "REPLACE_SAFE"


def build_rows():
    correlation_rows = read_csv(CORRELATION_CSV)
    db_catalog = load_partida_catalog()
    fichas_catalog = load_fichas_catalog()
    out_rows = []

    for row in correlation_rows:
        resolved_csis, unmapped_materials = resolve_csis(row)
        catalog_matches, missing_csis = lookup_catalog_entries(
            resolved_csis,
            db_catalog,
            fichas_catalog,
        )
        contract_decision = classify_contract(row, missing_csis, unmapped_materials)
        out_rows.append(
            OrderedDict(
                [
                    ("case_id", "CASE-MAT-001"),
                    ("stamp", STAMP),
                    ("category", row.get("category", "")),
                    ("source_type_id", row.get("source_type_id", "")),
                    ("source_type_name", row.get("source_type_name", "")),
                    ("type_mark", row.get("type_mark", "")),
                    ("type_keynote", row.get("type_keynote", "")),
                    ("primary_material", row.get("primary_material", "")),
                    ("target_bucket", row.get("correlation_group", "")),
                    ("correlation_decision", row.get("decision", "")),
                    ("contract_decision", contract_decision),
                    ("confidence", row.get("confidence", "")),
                    ("use_scope", row.get("use_scope", "")),
                    ("resolved_csis", " | ".join(resolved_csis)),
                    (
                        "catalog_descriptions",
                        " | ".join(
                            "{} -> {}".format(match["csi"], match["descripcion"])
                            for match in catalog_matches
                        ),
                    ),
                    (
                        "catalog_type_marks",
                        " | ".join(
                            "{} -> {}".format(match["csi"], match["type_mark"])
                            for match in catalog_matches
                            if match.get("type_mark")
                        ),
                    ),
                    (
                        "catalog_sources",
                        " | ".join(
                            "{} -> {}".format(match["csi"], match["source"])
                            for match in catalog_matches
                        ),
                    ),
                    ("missing_csis", " | ".join(missing_csis)),
                    ("unmapped_materials", " | ".join(unmapped_materials)),
                    ("material_signature", row.get("material_signature", "")),
                    ("keynote_signature", row.get("keynote_signature", "")),
                    ("blocking_red_layers", row.get("blocking_red_layers", "")),
                    ("nonblocking_red_layers", row.get("nonblocking_red_layers", "")),
                    ("rationale", row.get("rationale", "")),
                    ("execution_gate", "PROJECT_NEW_EMPTY_TARGET"),
                    (
                        "execution_note",
                        "Villarreal-MCP.rvt fue verificado el 2026-07-17 y sigue con 0 instancias fisicas.",
                    ),
                ]
            )
        )
    return out_rows


def write_csv(rows):
    if not rows:
        raise SystemExit("No rows built for contract.")
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows):
    summary = OrderedDict()
    for row in rows:
        key = (row["contract_decision"], row["category"])
        summary[key] = summary.get(key, 0) + 1
    print("Contrato generado: {}".format(OUT_CSV))
    print("Filas: {}".format(len(rows)))
    for key, count in summary.items():
        print("{} | {} -> {}".format(key[0], key[1], count))


if __name__ == "__main__":
    contract_rows = build_rows()
    write_csv(contract_rows)
    print_summary(contract_rows)
