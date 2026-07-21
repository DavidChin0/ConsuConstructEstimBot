"""Generate fichas_v1.3.json from PostgreSQL (primary) + fichas_v1.2.live.json (codigo/color fallback).

v1.3 = PG is truth for descripcion/unidad/precio_unitario/insumos.
       JSON v1.2 provides: codigo, color_tipo (not stored in PG partida).

Writes:
  development/Template2_Updated/v1.3/fichas/fichas_v1.3.json
  development/Template2_Updated/v1.3/fichas/fichas_v1.3.live.json

Run from D:\\GitHub\\EstimBot\\ConsuConstructEstimBot\\ESTIMASTRUCT\\:
  D:\\LLM\\python\\python.exe -m backend.scripts_runner.generate_fichas_v13
"""
import asyncio, json, os, re

# ─── paths ─────────────────────────────────────────────────────────────────
_THIS  = os.path.dirname(os.path.abspath(__file__))
_REPO  = os.path.abspath(os.path.join(_THIS, "..", ".."))
_V12   = os.path.join(_REPO, "development", "Template2_Updated", "v1.2", "fichas", "fichas_v1.2.live.json")
_OUT_D = os.path.join(_REPO, "development", "Template2_Updated", "v1.3", "fichas")
_OUT   = os.path.join(_OUT_D, "fichas_v1.3.json")
_LIVE  = os.path.join(_OUT_D, "fichas_v1.3.live.json")
_SEC   = r"D:\Secrets\postgres_credentials.txt"

# ─── PG config ─────────────────────────────────────────────────────────────
_PG_HOST = "127.0.0.1"
_PG_PORT = 5432
_PG_DB   = "estimastruct"
_PG_USER = "postgres"

_SQL = """
    SELECT DISTINCT ON (p.clave_csi)
        p.id, p.clave_csi, p.descripcion, p.unidad,
        p.costo_mo, p.costo_ma, p.unitario_matriz,
        p.precio_unitario, p.color_tipo
    FROM partida p
    WHERE p.clave_csi IS NOT NULL AND p.clave_csi != ''
    ORDER BY p.clave_csi, p.precio_unitario DESC NULLS LAST
"""

_SQL_INSUMOS = """
    SELECT i.clave, i.descripcion, i.unidad, i.tipo,
           i.cantidad, i.costo_unit, i.total, i.orden
    FROM insumo_partida i
    WHERE i.partida_id = $1
    ORDER BY i.orden, i.clave
"""


def _pg_password():
    try:
        for line in open(_SEC, encoding="utf-8"):
            line = line.strip()
            if line.startswith("password="):
                return line[9:]
    except Exception:
        pass
    return None


async def _fetch(pw):
    import asyncpg
    conn = await asyncpg.connect(
        host=_PG_HOST, port=_PG_PORT,
        database=_PG_DB, user=_PG_USER, password=pw
    )
    rows = await conn.fetch(_SQL)
    # Fetch insumos for each partida id
    result = []
    for r in rows:
        insumos_rows = await conn.fetch(_SQL_INSUMOS, r["id"])
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
        result.append((dict(r), insumos))
    await conn.close()
    return result


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


def main():
    pw = _pg_password()
    if not pw:
        raise RuntimeError("No PG password found in " + _SEC)

    pg_rows = asyncio.run(_fetch(pw))
    print(f"PG: {len(pg_rows)} unique CSI loaded")

    # Load v1.2 JSON for codigo/color_tipo fallback
    with open(_V12, encoding="utf-8") as f:
        v12 = json.load(f)

    v12_by_csi = {}
    for fi in v12:
        csi = fi.get("csi") or fi.get("clave_csi") or ""
        if csi:
            v12_by_csi[_normalize_csi(csi)] = fi

    # Build v1.3 fichas list
    fichas = []
    pg_csi_set = set()

    for row, insumos in pg_rows:
        csi_raw = row["clave_csi"]
        csi_norm = _normalize_csi(csi_raw)
        pg_csi_set.add(csi_norm)

        v12_fi = v12_by_csi.get(csi_norm, {})
        codigo = v12_fi.get("codigo") or ""
        color  = row.get("color_tipo") or v12_fi.get("color_tipo") or ""

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
        }
        fichas.append(ficha)

    # Add JSON-only fichas (in v1.2 but not in PG)
    json_only = 0
    for csi_norm, fi in v12_by_csi.items():
        if csi_norm not in pg_csi_set:
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
            }
            fichas.append(ficha)
            json_only += 1

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
                print(f"  FIXED: {csi_fix} → {vals['codigo']} ({note})")

    # Sort by CSI
    fichas.sort(key=lambda f: f.get("csi", ""))

    os.makedirs(_OUT_D, exist_ok=True)
    with open(_OUT,  "w", encoding="utf-8") as f:
        json.dump(fichas, f, ensure_ascii=False, indent=2)
    with open(_LIVE, "w", encoding="utf-8") as f:
        json.dump(fichas, f, ensure_ascii=False, indent=2)

    print(f"Written v1.3: {len(fichas)} fichas ({len(pg_rows)} from PG + {json_only} JSON-only)")
    print(f"  → {_OUT}")
    print(f"  → {_LIVE}")


if __name__ == "__main__":
    main()
