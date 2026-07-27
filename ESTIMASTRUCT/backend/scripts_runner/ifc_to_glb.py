"""ifc_to_glb.py — Convierte un IFC de Revit a GLB conservando la identidad por elemento.

Por que existe
--------------
El pipeline viejo era: Revit -> OBJ (`DB.OBJExportOptions`) -> obj2gltf -> GLB
(ver `viewer_postprocess.py` y `PYREVIT_S10_export_viewer_glb.py`). El exportador
OBJ nativo de Revit **fusiona geometria por material/tipo**, asi que la identidad
por elemento se pierde antes de que cualquier metadata pueda engancharse: 2344
instancias entraban y salian ~304 mallas anonimas. Por eso `viewer.html` tenia que
cruzar el dump contra el GLB por match de STRING de nombre de tipo (3 estrategias
en cascada, ver `loadGlb()`), fragil y silenciosamente incompleto.

El IFC si conserva identidad. Revit escribe, por cada elemento:
  - `GlobalId`  -> id estable entre exportaciones
  - `Tag`       -> el ElementId crudo de Revit (ej. '2513884')
  - `Name`      -> 'Familia:Tipo:ElementId'

Este script tesela el IFC con ifcopenshell y emite **un nodo glTF por elemento**,
con `name` = ElementId y `extras` = metadata fusionada del full dump. Resultado:
  - El join deja de ser por string y pasa a ser por entero exacto.
  - La metadata viaja DENTRO del GLB (`extras`), asi que el viewer ya no depende
    de cruzar dos archivos exportados en dias distintos.
  - `USE_WORLD_COORDS` hornea el placement de cada instancia, que es justo lo que
    el export OBJ estaba perdiendo (189 de 304 mallas colapsaban sobre el origen).

Compatibilidad con el viewer actual
-----------------------------------
Los nodos se nombran con el ElementId pelado a proposito: `viewer.html` ya tiene
la "Strategy 2: mesh name = instance element ID -> instById", asi que este GLB
funciona SIN tocar el viewer. Los `extras` son un bonus para cuando se quiera
dejar de leer el dump.

Uso
---
    python -m backend.scripts_runner.ifc_to_glb <archivo.ifc> [--out salida.glb]
                                                [--dump project_full_dump.json]
                                                [--project <nombre>]

Sin `--out`, escribe en `D:\\OneDrive\\Bots\\Viewer\\projects\\<project>\\model_viewer.glb`
(el nombre que ya espera el endpoint `/revit-mcp/viewer-glb`).

Dependencias: ifcopenshell, pygltflib, numpy.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

try:
    import ifcopenshell
    import ifcopenshell.geom
except ImportError:
    sys.exit("Falta ifcopenshell. Instalar con: pip install ifcopenshell")

try:
    import pygltflib
except ImportError:
    sys.exit("Falta pygltflib. Instalar con: pip install pygltflib")


# -- Rutas canonicas (mismas que viewer_postprocess.py) ----------------------
_FULL_DUMP_PATH = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\project_full_dump.json")
_VIEWER_ROOT = Path(r"D:\OneDrive\Bots\Viewer\projects")

# Categorias IFC que NO aportan geometria util al viewer arquitectonico.
_SKIP_TYPES = {"IfcOpeningElement", "IfcSpace", "IfcAnnotation", "IfcGrid"}


# ---------------------------------------------------------------------------
# Dump
# ---------------------------------------------------------------------------
def _load_dump(path: Path) -> dict:
    """Carga el full dump. Devuelve {} si no existe — el GLB igual se genera."""
    if not path.is_file():
        print("  [WARN] full dump no encontrado: {} — los extras van sin keynote".format(path))
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _index_dump(dump: dict) -> tuple[dict, dict]:
    """Indexa el dump por ElementId (entero, como string).

    Devuelve (objects_por_id, instances_por_id). `objects` son TIPOS y ahi vive
    el keynote; `all_instances` son las instancias colocadas.
    """
    obj_by_id: dict[str, dict] = {}
    for obj in dump.get("objects") or []:
        if obj.get("id") is not None:
            obj_by_id[str(obj["id"])] = obj

    inst_by_id: dict[str, dict] = {}
    for inst in dump.get("all_instances") or []:
        if inst.get("id") is not None:
            inst_by_id[str(inst["id"])] = inst

    return obj_by_id, inst_by_id


def _build_extras(eid: str, product: Any, obj_by_id: dict, inst_by_id: dict) -> dict:
    """Arma el dict de `extras` de un nodo glTF cruzando IFC + dump por ElementId."""
    extras: dict[str, Any] = {
        "element_id": eid,
        "global_id": getattr(product, "GlobalId", None),
        "ifc_type": product.is_a(),
        "ifc_name": getattr(product, "Name", None),
    }

    inst = inst_by_id.get(eid)
    if inst:
        extras["category"] = inst.get("category")
        extras["level"] = inst.get("level")
        extras["family"] = inst.get("family")
        extras["type"] = inst.get("type")
        extras["type_mark"] = inst.get("type_mark")
        extras["marca"] = inst.get("marca")
        if inst.get("keynote"):
            extras["keynote"] = inst["keynote"]

        # El keynote suele vivir en el TIPO, no en la instancia.
        type_obj = obj_by_id.get(str(inst.get("type_id")))
        if type_obj:
            extras.setdefault("keynote", type_obj.get("keynote"))
            extras.setdefault("type_mark", type_obj.get("type_mark"))

    # El propio ElementId puede ser un tipo (no una instancia).
    obj = obj_by_id.get(eid)
    if obj:
        extras.setdefault("keynote", obj.get("keynote"))
        extras.setdefault("category", obj.get("category"))
        extras.setdefault("type_mark", obj.get("type_mark"))

    return {k: v for k, v in extras.items() if v is not None}


# ---------------------------------------------------------------------------
# Teselado IFC
# ---------------------------------------------------------------------------
def _element_id_of(product: Any) -> str | None:
    """ElementId de Revit. `Tag` es la fuente primaria; si falta, se saca del Name.

    Revit escribe Name como 'Familia:Tipo:ElementId', asi que el ultimo segmento
    numerico sirve de respaldo.
    """
    tag = getattr(product, "Tag", None)
    if tag and str(tag).strip().isdigit():
        return str(tag).strip()

    name = getattr(product, "Name", None)
    if name:
        last = str(name).rsplit(":", 1)[-1].strip()
        if last.isdigit():
            return last

    return None


def _tessellate(ifc_path: Path) -> list[dict]:
    """Tesela el IFC y devuelve una lista de dicts por elemento con geometria.

    USE_WORLD_COORDS=True hornea el placement de cada instancia en los vertices;
    sin eso la geometria sale en espacio local y las instancias colapsan (que es
    exactamente el bug que trajo el pipeline OBJ).
    """
    model = ifcopenshell.open(str(ifc_path))

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)

    # ifcopenshell 0.8.x: el kwarg es `num_threads` (en 0.7.x era `multiprocessing`).
    iterator = ifcopenshell.geom.iterator(settings, model, num_threads=4)
    if not iterator.initialize():
        return []

    out: list[dict] = []
    skipped_no_id = 0

    while True:
        shape = iterator.get()
        product = model.by_id(shape.id)

        if product.is_a() not in _SKIP_TYPES:
            eid = _element_id_of(product)
            if eid is None:
                skipped_no_id += 1
            else:
                geo = shape.geometry
                verts = np.asarray(geo.verts, dtype=np.float32).reshape(-1, 3)
                faces = np.asarray(geo.faces, dtype=np.uint32)

                if len(verts) and len(faces):
                    out.append({
                        "element_id": eid,
                        "product": product,
                        "verts": verts,
                        "faces": faces,
                    })

        if not iterator.next():
            break

    if skipped_no_id:
        print("  [WARN] {} elementos sin ElementId derivable — omitidos".format(skipped_no_id))

    return out


# ---------------------------------------------------------------------------
# Construccion del GLB
# ---------------------------------------------------------------------------
def _build_glb(elements: list[dict], obj_by_id: dict, inst_by_id: dict) -> pygltflib.GLTF2:
    """Construye un GLTF2 con un nodo por elemento.

    Un solo buffer con todos los vertices e indices concatenados; un accessor por
    atributo y por primitiva.
    """
    blob = bytearray()
    buffer_views: list[pygltflib.BufferView] = []
    accessors: list[pygltflib.Accessor] = []
    meshes: list[pygltflib.Mesh] = []
    nodes: list[pygltflib.Node] = []

    def _pad4() -> None:
        while len(blob) % 4:
            blob.append(0)

    for el in elements:
        verts: np.ndarray = el["verts"]
        faces: np.ndarray = el["faces"]

        # -- indices --
        _pad4()
        idx_offset = len(blob)
        idx_bytes = faces.astype(np.uint32).tobytes()
        blob.extend(idx_bytes)
        buffer_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=idx_offset, byteLength=len(idx_bytes),
            target=pygltflib.ELEMENT_ARRAY_BUFFER,
        ))
        accessors.append(pygltflib.Accessor(
            bufferView=len(buffer_views) - 1, componentType=pygltflib.UNSIGNED_INT,
            count=int(faces.size), type=pygltflib.SCALAR,
            max=[int(faces.max())], min=[int(faces.min())],
        ))
        idx_accessor = len(accessors) - 1

        # -- posiciones --
        _pad4()
        pos_offset = len(blob)
        pos_bytes = verts.astype(np.float32).tobytes()
        blob.extend(pos_bytes)
        buffer_views.append(pygltflib.BufferView(
            buffer=0, byteOffset=pos_offset, byteLength=len(pos_bytes),
            target=pygltflib.ARRAY_BUFFER,
        ))
        accessors.append(pygltflib.Accessor(
            bufferView=len(buffer_views) - 1, componentType=pygltflib.FLOAT,
            count=int(len(verts)), type=pygltflib.VEC3,
            max=verts.max(axis=0).tolist(), min=verts.min(axis=0).tolist(),
        ))
        pos_accessor = len(accessors) - 1

        meshes.append(pygltflib.Mesh(primitives=[pygltflib.Primitive(
            attributes=pygltflib.Attributes(POSITION=pos_accessor),
            indices=idx_accessor,
        )]))

        nodes.append(pygltflib.Node(
            mesh=len(meshes) - 1,
            name=el["element_id"],  # <- clave: el viewer matchea por esto
            extras=_build_extras(el["element_id"], el["product"], obj_by_id, inst_by_id),
        ))

    # IFC es Z-arriba y glTF es Y-arriba: rotacion -90 grados en X en la raiz.
    root = pygltflib.Node(
        name="__ifc_root",
        children=list(range(len(nodes))),
        matrix=[1, 0, 0, 0,
                0, 0, -1, 0,
                0, 1, 0, 0,
                0, 0, 0, 1],
    )
    nodes.append(root)

    gltf = pygltflib.GLTF2(
        scene=0,
        scenes=[pygltflib.Scene(nodes=[len(nodes) - 1])],
        nodes=nodes,
        meshes=meshes,
        accessors=accessors,
        bufferViews=buffer_views,
        buffers=[pygltflib.Buffer(byteLength=len(blob))],
    )
    gltf.set_binary_blob(bytes(blob))
    return gltf


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def convert(ifc_path: Path, out_path: Path, dump_path: Path) -> bool:
    print("IFC  : {}".format(ifc_path))
    print("Dump : {}".format(dump_path))
    print("Out  : {}".format(out_path))

    if not ifc_path.is_file():
        print("  [ERR] IFC no encontrado")
        return False

    dump = _load_dump(dump_path)
    obj_by_id, inst_by_id = _index_dump(dump)
    print("  dump indexado: {} tipos, {} instancias".format(len(obj_by_id), len(inst_by_id)))

    print("  teselando…")
    elements = _tessellate(ifc_path)
    if not elements:
        print("  [ERR] el IFC no produjo geometria")
        return False

    matched = sum(1 for e in elements if e["element_id"] in inst_by_id or e["element_id"] in obj_by_id)
    print("  elementos con geometria : {}".format(len(elements)))
    print("  matcheados contra dump  : {} ({:.0f}%)".format(
        matched, 100.0 * matched / len(elements) if elements else 0))

    gltf = _build_glb(elements, obj_by_id, inst_by_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gltf.save_binary(str(out_path))

    size_mb = out_path.stat().st_size / 1_048_576
    print("  OK -> {} ({:.2f} MB, {} nodos)".format(out_path.name, size_mb, len(elements)))
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convierte IFC de Revit a GLB con identidad por elemento.")
    ap.add_argument("ifc", help="Ruta al archivo .ifc")
    ap.add_argument("--out", help="Ruta del .glb de salida")
    ap.add_argument("--dump", default=str(_FULL_DUMP_PATH), help="Ruta al project_full_dump.json")
    ap.add_argument("--project", help="Nombre de proyecto en el viewer root (si no se pasa --out)")
    args = ap.parse_args(argv)

    ifc_path = Path(args.ifc)

    if args.out:
        out_path = Path(args.out)
    else:
        project = args.project or ifc_path.stem
        out_path = _VIEWER_ROOT / project / "model_viewer.glb"

    return 0 if convert(ifc_path, out_path, Path(args.dump)) else 1


if __name__ == "__main__":
    sys.exit(main())
