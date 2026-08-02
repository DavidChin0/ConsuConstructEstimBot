"""Build a project-agnostic element schema from a project_full_dump.json
(revit_full_dump_snippet.py output), so EstimaStruct can DRAW elements from
the database into a blank Revit template instead of shipping a pre-built
.rvt as the starting point.

Input:  D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\project_full_dump.json
Output: D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\generic_element_schema.json

Three sections:
  assemblies           — CREABLE POR SCRIPT. System families (Muros/Suelos/
                         Cubiertas/Techos) with their CompoundStructure layer
                         stack (function, material, material CSI, width_mm).
                         `WallType.Duplicate()` + `SetLayers()` rebuilds these
                         from zero via API — no .rfa needed, ever.
  elementos_puntuales  — NO CREABLE POR SCRIPT. Loadable-family types (doors,
                         windows, curtain panels, MEP fixtures). `place_family`
                         only works if the .rfa is already on disk and loaded
                         — there is no `create_family` tool (confirmed against
                         revit-mcp-stdio's tool_manifest.py, 2026-08-01: no
                         Family Editor exposure). These are a hard dependency
                         on an existing family library, not something the
                         pipe can author.
  familias_no_creables — dedup of elementos_puntuales by (categoria, familia),
                         with a count of how many tipos need that family. This
                         is the checklist: source these .rfa or nothing places.

Deliberately drops `compound_elements`/`objects` rows that aren't buildable
geometry: legend components, sun path, axes, sketches, and "Materiales" rows
that are material catalog entries misfiled as instances by the source dump
(category == Model but no family/geometry). See NOISE_CATEGORIES.
"""
import json, os, sys

IN_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\project_full_dump.json"
OUT_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\generic_element_schema.json"

NOISE_CATEGORIES = {
    "Materiales",
    "Componentes de leyenda",
    "Activos de materiales",
    "Camino de sol",
    "Eje",
    "<Boceto>",
    "Cámaras",
    "Planos",
}

# Categorias cuyo "tipo" es un System Family Type de Revit (Wall/Floor/Roof/
# Ceiling/Toposolid/PipeType/WireType/etc) — se recrean por API duplicando el
# tipo y seteando parametros, NUNCA requieren .rfa. Si aparecen en `objects`
# es porque tienen keynote a nivel de tipo pero cayeron sin capas en
# compound_elements (ej. "Muro básico" generico sin CSI propio, o Type
# families MEP sin geometria de familia). Confirmado 2026-08-01 contra
# tool_manifest.py: no existe create_family, pero estos NO la necesitan.
SYSTEM_TYPE_CATEGORIES = {
    "Muros",
    "Suelos",
    "Cubiertas",
    "Techos",
    "Sólido topográfico",
    "Sistemas de vigas estructurales",
    "Refuerzo de área estructural",
    "Tuberías",
    "Cables",
    "Paneles de muro cortina",  # "System Panel" es built-in, no .rfa
}


def _build_assemblies(compound_elements: list) -> list:
    out = []
    for c in compound_elements:
        layers = c.get("layers") or []
        if not layers:
            continue
        if not c.get("type_keynote"):
            continue  # no CSI = library generic (e.g. "Generic - 150mm Masonry"), not a real partida
        out.append({
            "csi": c.get("type_keynote"),
            "marca": c.get("type_marca"),
            "categoria": c.get("category_label"),
            "tipo_nombre": c.get("type_name"),
            "capas": [
                {
                    "funcion": l.get("function"),
                    "material": l.get("material_name"),
                    "material_csi": l.get("material_keynote"),
                    "espesor_mm": l.get("width_mm"),
                }
                for l in layers
            ],
        })
    return out


def _build_elementos_puntuales(objects: list) -> tuple:
    """Returns (elementos_puntuales, tipos_sistema). elementos_puntuales = loadable
    families (need .rfa). tipos_sistema = System Family Types that leaked in here
    because they had no CompoundStructure layers (Toposolid, Pipe/Wire Types,
    Structural Framing Systems...) — creatable by API type-duplicate, no .rfa,
    but no layer recipe available (kept separate from `assemblies` for that reason)."""
    out, sistema = [], []
    seen = set()
    for o in objects:
        if o.get("kind") != "type":
            continue
        if not o.get("keynote"):
            continue
        categoria = o.get("category")
        if categoria in NOISE_CATEGORIES:
            continue
        key = (categoria, o.get("family"), o.get("type"))
        if key in seen:
            continue
        seen.add(key)
        row = {
            "csi": o.get("keynote"),
            "marca": o.get("marca"),
            "type_mark": o.get("type_mark"),
            "categoria": categoria,
            "familia": o.get("family"),
            "tipo_nombre": o.get("type"),
        }
        if categoria in SYSTEM_TYPE_CATEGORIES:
            sistema.append(row)
        else:
            out.append(row)
    return out, sistema


def _build_familias_no_creables(elementos_puntuales: list) -> list:
    counts: dict = {}
    for e in elementos_puntuales:
        key = (e.get("categoria"), e.get("familia"))
        counts[key] = counts.get(key, 0) + 1
    out = [
        {"categoria": cat, "familia": fam, "tipos_requeridos": n}
        for (cat, fam), n in counts.items()
    ]
    out.sort(key=lambda r: (r["categoria"] or "", r["familia"] or ""))
    return out


def generate(in_path: str = IN_PATH, out_path: str = OUT_PATH) -> dict:
    with open(in_path, encoding="utf-8") as f:
        dump = json.load(f)

    assemblies = _build_assemblies(dump.get("compound_elements") or [])
    elementos_puntuales, tipos_sistema = _build_elementos_puntuales(dump.get("objects") or [])
    familias_no_creables = _build_familias_no_creables(elementos_puntuales)

    schema = {
        "_meta": {
            "source": in_path,
            "schema_version": "v3",
            "note": "project-agnostic — no element IDs, no XYZ geometry, no project-specific instance data",
        },
        "assemblies": assemblies,
        "tipos_sistema": tipos_sistema,
        "elementos_puntuales": elementos_puntuales,
        "familias_no_creables": familias_no_creables,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print("Written: {} assemblies | {} tipos_sistema (creables, sin capas) | {} elementos_puntuales / {} familias unicas (NO creables) -> {}".format(
        len(assemblies), len(tipos_sistema), len(elementos_puntuales), len(familias_no_creables), out_path))
    return schema


if __name__ == "__main__":
    in_path = sys.argv[1] if len(sys.argv) > 1 else IN_PATH
    out_path = sys.argv[2] if len(sys.argv) > 2 else OUT_PATH
    generate(in_path, out_path)
