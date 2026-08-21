"""Generate fichas_v1.4.json from canonical SQLite (estimacion.db) including rendimiento_audit data.

v1.4 = SQLite is truth for descripcion/unidad/precio_unitario/insumos + rendimiento_audit.
       JSON v1.3 provides: codigo, color_tipo (not stored in SQLite partida).

Writes:
  development/Template2_Updated/v1.4/fichas/fichas_v1.4.json
  development/Template2_Updated/v1.4/fichas/fichas_v1.4.live.json

Run from D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\:
  D:\LLM\python\python.exe -m backend.scripts_runner.generate_fichas_v14
"""
import json
import os
import re
import sqlite3

# ─── paths ─────────────────────────────────────────────────────────────────
_THIS  = os.path.dirname(os.path.abspath(__file__))
_REPO  = os.path.abspath(os.path.join(_THIS, "..", ".."))
_V13   = os.path.join(_REPO, "development", "Template2_Updated", "v1.3", "fichas", "fichas_v1.3.live.json")
_OUT_D = os.path.join(_REPO, "development", "Template2_Updated", "v1.4", "fichas")
_OUT   = os.path.join(_OUT_D, "fichas_v1.4.json")
_LIVE  = os.path.join(_OUT_D, "fichas_v1.4.live.json")
_DB    = r"D:\EstimaStruct\data\estimacion.db"


def _normalize_csi(key):
    if not key:
        return ""
    raw = str(key).replace("_x000D_", "").strip()
    raw = re.sub(r"\s*\.\s*", ".", raw)
    raw = re.sub(r"\s+", " ", raw)
    parts = raw.split(" ")
    if len(parts) <= 3:
        return raw
    return " ".join(parts[:3]) + "." + ".".join(parts[3:])


def _fetch_from_sqlite():
    con = sqlite3.connect(_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Get all partidas with their insumos
    cur.execute("""
        SELECT 
            p.id, p.clave_csi, p.descripcion, p.unidad,
            p.costo_mo, p.costo_ma, p.unitario_matriz,
            p.precio_unitario, p.color_tipo
        FROM partida p
        WHERE p.clave_csi IS NOT NULL AND p.clave_csi != ''
        ORDER BY p.clave_csi
    """)
    partidas = cur.fetchall()

    # Fetch rendimiento_audit data grouped by partida_clave_csi
    cur.execute("""
        SELECT 
            partida_clave_csi,
            fuente,
            fuente_edicion,
            fuente_codigo,
            fuente_url,
            fuente_pagina,
            fecha_consulta,
            recurso_tipo,
            recurso_descripcion,
            coeficiente_nativo,
            unidad_nativa,
            coeficiente_normalizado,
            formula_conversion,
            tipo_match,
            confianza,
            evidencia,
            condiciones_alcance,
            hash_insumo,
            notas_discrepancia
        FROM rendimiento_audit
        ORDER BY partida_clave_csi, fuente, recurso_tipo
    """)
    audit_rows = cur.fetchall()
    
    # Group audit data by normalized CSI
    audit_by_csi = {}
    for ar in audit_rows:
        csi_norm = _normalize_csi(ar["partida_clave_csi"])
        if csi_norm not in audit_by_csi:
            audit_by_csi[csi_norm] = []
        audit_by_csi[csi_norm].append({
            "fuente": ar["fuente"],
            "fuente_edicion": ar["fuente_edicion"],
            "fuente_codigo": ar["fuente_codigo"],
            "fuente_url": ar["fuente_url"],
            "fuente_pagina": ar["fuente_pagina"],
            "fecha_consulta": ar["fecha_consulta"],
            "recurso_tipo": ar["recurso_tipo"],
            "recurso_descripcion": ar["recurso_descripcion"],
            "coeficiente_nativo": float(ar["coeficiente_nativo"] or 0),
            "unidad_nativa": ar["unidad_nativa"],
            "coeficiente_normalizado": float(ar["coeficiente_normalizado"] or 0),
            "formula_conversion": ar["formula_conversion"],
            "tipo_match": ar["tipo_match"],
            "confianza": float(ar["confianza"] or 0),
            "evidencia": ar["evidencia"],
            "condiciones_alcance": ar["condiciones_alcance"],
            "hash_insumo": ar["hash_insumo"],
            "notas_discrepancia": ar["notas_discrepancia"],
        })

    result = []
    for p in partidas:
        cur.execute("""
            SELECT i.clave, i.descripcion, i.unidad, i.tipo,
                   i.cantidad, i.costo_unit, i.total, i.orden
            FROM insumo_partida i
            WHERE i.partida_id = ?
            ORDER BY i.orden, i.clave
        """, (p["id"],))
        insumos_rows = cur.fetchall()
        insumos = [
            {
                "clave":       ir["clave"],
                "descripcion": ir["descripcion"],
                "unidad":      ir["unidad"],
                "tipo":        ir["tipo"],
                "cantidad":    float(ir["cantidad"] or 0),
                "costo_unit":  float(ir["costo_unit"] or 0),
                "total":       float(ir["total"] or 0),
            }
            for ir in insumos_rows
        ]
        
        # Attach rendimiento_audit for this CSI
        csi_norm = _normalize_csi(p["clave_csi"])
        rendimiento_audit = audit_by_csi.get(csi_norm, [])
        
        p_dict = dict(p)
        p_dict["rendimiento_audit"] = rendimiento_audit
        result.append((p_dict, insumos))

    con.close()
    return result


def main():
    pg_rows = _fetch_from_sqlite()
    print(f"SQLite: {len(pg_rows)} unique CSI loaded")

    # Load v1.3 JSON for codigo/color_tipo fallback
    with open(_V13, encoding="utf-8") as f:
        v13 = json.load(f)

    v13_by_csi = {}
    for fi in v13:
        csi = fi.get("csi") or fi.get("clave_csi") or ""
        if csi:
            v13_by_csi[_normalize_csi(csi)] = fi

    # Build v1.4 fichas list
    fichas = []
    sqlite_csi_set = set()

    for row, insumos in pg_rows:
        csi_raw = row["clave_csi"]
        csi_norm = _normalize_csi(csi_raw)
        sqlite_csi_set.add(csi_norm)

        v13_fi = v13_by_csi.get(csi_norm, {})
        codigo = v13_fi.get("codigo") or ""
        color  = row.get("color_tipo") or v13_fi.get("color_tipo") or ""
        rendimiento_audit = row.get("rendimiento_audit", [])

        ficha = {
            "csi":              csi_raw,
            "codigo":           codigo,
            "descripcion":      row["descripcion"] or "",
            "unidad":           row["unidad"] or "",
            "precio_unitario":  float(row["precio_unitario"] or 0),
            "costo_mo":         float(row["costo_mo"] or 0),
            "costo_ma":         float(row["costo_ma"] or 0),
            "unitario_matriz":  float(row["unitario_matriz"] or 0),
            "insumos":          insumos,
            "color_tipo":       color,
            "rendimiento_audit": rendimiento_audit,
        }
        fichas.append(ficha)

    # Add JSON-only fichas (in v1.3 but not in SQLite)
    json_only = 0
    for csi_norm, fi in v13_by_csi.items():
        if csi_norm not in sqlite_csi_set:
            csi_raw = fi.get("csi") or fi.get("clave_csi") or ""
            ficha = {
                "csi":              csi_raw,
                "codigo":           fi.get("codigo") or "",
                "descripcion":      fi.get("descripcion") or "",
                "unidad":           fi.get("unidad") or "",
                "precio_unitario":  float(fi.get("precio_unitario") or 0),
                "costo_mo":         0.0,
                "costo_ma":         0.0,
                "unitario_matriz":  0.0,
                "insumos":          fi.get("insumos") or [],
                "color_tipo":       fi.get("color_tipo") or "",
                "rendimiento_audit": [],
            }
            fichas.append(ficha)
            json_only += 1

    # Fixes (same as v1.3)
    _FIXES = {
        "05 31 13.3": {
            "descripcion": "Suministro e instalación de Cercha Metálica con Canal Laminado CG-05 (estructura de techo o entrepiso)",
            "codigo":      "CG-05",
            "unidad":      "m2",
            "_note":       "GAP-05 era Deck de madera — incorrecto bajo Div 05 Steel Framing",
        },
        "08 51 13.4": {
            "descripcion": "Muro Cortina de Vidrio / Pared Cortina Vidriada (Storefront Aluminio)",
            "codigo":      "MCV-01",
            "unidad":      "m2",
            "_note":       "GAP-08 era descripción técnica Revit — renombrado a español canónico",
        },
    }
    for fi in fichas:
        csi_n = _normalize_csi(fi["csi"])
        for csi_fix, vals in _FIXES.items():
            if csi_n == _normalize_csi(csi_fix):
                note = vals.pop("_note", "")
                fi.update(vals)
                vals["_note"] = note
                print(f"  FIXED: {csi_fix} -> {vals['codigo']} ({note})")

    # Sort by CSI
    fichas.sort(key=lambda f: f.get("csi", ""))

    os.makedirs(_OUT_D, exist_ok=True)
    with open(_OUT,  "w", encoding="utf-8") as f:
        json.dump(fichas, f, ensure_ascii=False, indent=2)
    with open(_LIVE, "w", encoding="utf-8") as f:
        json.dump(fichas, f, ensure_ascii=False, indent=2)

    print(f"Written v1.4: {len(fichas)} fichas ({len(pg_rows)} from SQLite + {json_only} JSON-only)")
    print(f"  -> {_OUT}")
    print(f"  -> {_LIVE}")


if __name__ == "__main__":
    main()