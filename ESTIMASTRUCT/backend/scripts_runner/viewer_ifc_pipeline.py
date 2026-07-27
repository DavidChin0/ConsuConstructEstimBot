"""viewer_ifc_pipeline.py — Pipeline completo Revit -> IFC -> GLB para el Viewer 3D.

Reemplaza el camino viejo Revit -> OBJ -> obj2gltf -> GLB (`viewer_postprocess.py`),
que perdia la identidad por elemento y colapsaba placements. Ver la cabecera de
`ifc_to_glb.py` para el detalle tecnico de por que OBJ no servia.

Que hace, de punta a punta:
  1. Pide al Revit MCP (:8001) que exporte el documento activo a IFC4 —
     tool `export_ifc`, el mismo que expone el MCP server.
  2. Convierte ese IFC a GLB con `ifc_to_glb`, emitiendo un nodo por elemento
     nombrado con el ElementId de Revit y con la metadata del full dump
     horneada en los `extras` de cada nodo.
  3. Deja el GLB en `D:\\OneDrive\\Bots\\Viewer\\projects\\<proyecto>\\model_viewer.glb`,
     que es exactamente lo que ya sirve el endpoint `/revit-mcp/viewer-glb`.

Requisitos: Revit abierto con el modelo, MCP arriba en :8001 (boton "Levantar MCP"
del panel), y el full dump generado (boton "Full Dump (viewer)") para que los
`extras` lleven keynote/categoria/nivel.

Uso:
    python -m backend.scripts_runner.viewer_ifc_pipeline [--project <nombre>]
                                                         [--skip-export]
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

from backend.scripts_runner.ifc_to_glb import (
    _FULL_DUMP_PATH,
    _VIEWER_ROOT,
    convert,
)
from backend.services import mcp_http

_IFC_EXPORTS_DIR = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\IFC_exports")


def _slug(name: str) -> str:
    """Normaliza el nombre de documento de Revit a un nombre de carpeta seguro."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
    return s or "modelo"


async def _export_ifc(ifc_path: Path) -> tuple[bool, str]:
    """Dispara el export IFC en Revit via el MCP. Devuelve (ok, detalle)."""
    if not mcp_http.is_mcp_running():
        return False, (
            "El MCP no responde en :8001. Levantalo con el boton "
            "'Levantar MCP' del panel Revit MCP antes de correr esto."
        )

    ifc_path.parent.mkdir(parents=True, exist_ok=True)
    res = await mcp_http.call_tool(
        "export_ifc",
        {
            "file_path": str(ifc_path),
            "ifc_version": "IFC4",
            "export_base_quantities": True,
        },
        timeout=600,  # modelos grandes tardan; el export IFC es lo lento del pipeline
    )
    if not res.get("ok"):
        return False, "El MCP rechazo export_ifc: {}".format(res.get("error") or res)

    if not ifc_path.is_file():
        return False, "export_ifc respondio OK pero no aparecio el archivo: {}".format(ifc_path)

    # mcp_http.call_tool devuelve el texto bajo la clave "output" (no "text").
    return True, res.get("output") or "IFC exportado"


async def _resolve_project_name() -> str | None:
    """Pregunta al MCP como se llama el documento abierto, para nombrar la carpeta."""
    if not mcp_http.is_mcp_running():
        return None
    res = await mcp_http.call_tool("get_revit_status", {}, timeout=30)
    if not res.get("ok"):
        return None
    m = re.search(r"Document:\s*(.+)", res.get("output") or "")
    return _slug(m.group(1).strip()) if m else None


def run(project: str | None = None, skip_export: bool = False) -> int:
    if not skip_export or project is None:
        detected = asyncio.run(_resolve_project_name())
        project = project or detected

    if not project:
        print("[ERR] No pude determinar el nombre del proyecto. Pasalo con --project.")
        return 1

    ifc_path = _IFC_EXPORTS_DIR / "{}.ifc".format(project)
    out_glb = _VIEWER_ROOT / project / "model_viewer.glb"

    print("Proyecto : {}".format(project))
    print("=" * 60)

    if skip_export:
        print("[1/2] Export IFC OMITIDO (--skip-export) — reusando {}".format(ifc_path))
        if not ifc_path.is_file():
            print("[ERR] No existe ese IFC. Corre sin --skip-export.")
            return 1
    else:
        print("[1/2] Exportando IFC desde Revit via MCP…")
        ok, detail = asyncio.run(_export_ifc(ifc_path))
        print("      {}".format(detail))
        if not ok:
            return 1

    print("[2/2] Convirtiendo IFC -> GLB con identidad por elemento…")
    if not convert(ifc_path, out_glb, _FULL_DUMP_PATH):
        return 1

    print("=" * 60)
    print("Listo. Recarga el Viewer 3D y pulsa 'Recargar datos'.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pipeline Revit -> IFC -> GLB para el Viewer 3D.")
    ap.add_argument("--project", help="Nombre de carpeta en el viewer root (default: documento activo de Revit)")
    ap.add_argument("--skip-export", action="store_true",
                    help="No re-exportar desde Revit; reusar el IFC que ya esta en disco")
    args = ap.parse_args(argv)
    return run(project=args.project, skip_export=args.skip_export)


if __name__ == "__main__":
    sys.exit(main())
