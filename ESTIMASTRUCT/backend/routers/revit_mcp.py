"""Revit MCP Controls — FastAPI router.

Endpoints:
  GET  /revit-mcp/status            — MCP + Revit connection status
  POST /revit-mcp/start             — Levantar MCP HTTP (main_pipe.py --http)
  POST /revit-mcp/stop              — Detener MCP
  GET  /revit-mcp/scripts           — Lista de scripts disponibles
  GET  /revit-mcp/schedules         — Lista de schedule CSVs en S5_schedules
  POST /revit-mcp/inject/{name}     — Inyectar snippet IronPython via MCP
  POST /revit-mcp/python/{script}   — Ejecutar script Python offline
  POST /revit-mcp/obras/{pid}/import-quantities
  POST /revit-mcp/obras/{pid}/validate-units
  POST /revit-mcp/obras/{pid}/generate-keynotes
"""
from __future__ import annotations

import asyncio, glob, json, os, re, subprocess, sys, time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services import mcp_http
from backend.config import CONFIG

router = APIRouter(prefix="/revit-mcp", tags=["revit-mcp"])

_REPO         = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR  = _REPO / "backend" / "scripts_runner"
_S5_DIR       = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules")
_S1_DIR       = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\S1_keynotes")
PYTHON        = r"D:\LLM\python\python.exe"

# ──────────────────────────────────────────────
# IronPython snippets (have CODE = r'''...''' pattern)
# ──────────────────────────────────────────────
_IRONPYTHON_SCRIPTS = {
    "dump":          "revit_dump_snippet.py",
    "dump-full":     "revit_full_dump_snippet.py",
    "marks_master":  "revit_marks_master.py",
    "keynote_path":  "revit_get_keynote_path.py",
    "marks_legacy":  "revit_set_marks_snippet.py",
}

# ──────────────────────────────────────────────
# Python offline scripts metadata
# ──────────────────────────────────────────────
_PYTHON_SCRIPTS = {
    "generate-fichas": {
        "module": "backend.scripts_runner.generate_fichas_v13",
        "label":  "Generar Fichas v1.3",
        "desc":   "Regenera fichas_v1.3.json desde PG + JSON v1.2. Aplica fixes canónicos (cercha, MCV-01).",
        "args":   [],
    },
    "generate-keynotes-catalog": {
        "module": "backend.scripts_runner.generate_keynotes_catalog",
        "label":  "Keynotes Catálogo",
        "desc":   "Genera RevitKeynotes_CATALOG_v1.3_<Fecha>.txt con los 375 CSI del catálogo.",
        "args":   [],
    },
    "audit-pipeline": {
        "module": "backend.scripts_runner.run_audit_pipeline",
        "label":  "Pipeline Auditoría",
        "desc":   "audit_keynotes → generate_audit_xlsx → sync_audit_colors. Requiere model_audit_raw.json fresco.",
        "args":   [],
    },
    "suggest-keynotes": {
        "module": "backend.scripts_runner.suggest_keynotes",
        "label":  "Sugerir Keynotes",
        "desc":   "Sugiere CSI para elementos RED sin keynote. Produce CSV para revisión Director.",
        "args":   [],
    },
    "generate-csi-to-codigo": {
        "module": "backend.scripts_runner.generate_csi_to_codigo",
        "label":  "Generar CSI→Código",
        "desc":   "Regenera csi_to_codigo.json desde fichas_v1.2.live.json. Prereq para Set Marks.",
        "args":   [],
    },
    "add-scripts-tab": {
        "file":   str(_REPO / "..") + r"\..\..\..\GitHub\revit-estimastruct-audit\audit\add_scripts_tab_to_canon.py",
        "label":  "Actualizar CANON XLSX",
        "desc":   "Actualiza la hoja 'Scripts & Skills' en Auditoria_MCP_Master_CANON.xlsx.",
        "args":   [],
        "cwd":    r"D:\GitHub\revit-estimastruct-audit\audit",
    },
    "viewer-postprocess": {
        "module": "backend.scripts_runner.viewer_postprocess",
        "label":  "Viewer Post-process",
        "desc":   "Convierte OBJ exports a GLB y escribe scene_index.json enriquecido con datos del Full Dump (levels, rooms, materials_full, project_info).",
        "args":   [],
    },
}


def _read_ironpython_code(script_filename: str) -> str:
    path = _SCRIPTS_DIR / script_filename
    src = path.read_text(encoding="utf-8")
    m = re.search(r"CODE = r'''(.*?)'''", src, re.DOTALL)
    if not m:
        raise ValueError(f"No CODE block found in {script_filename}")
    return m.group(1)


def _run_cmd_blocking(cmd: list[str], cwd: str) -> dict:
    """Corre el comando de forma síncrona (subprocess.run clásico).

    NO usar asyncio.create_subprocess_exec aquí: uvicorn con --reload en Windows
    fuerza asyncio.SelectorEventLoop (ver uvicorn/loops/asyncio.py, use_subprocess=True
    cuando hay reloader), y SelectorEventLoop NO implementa creación de subprocesos en
    Windows → asyncio.create_subprocess_exec revienta con NotImplementedError en TODO
    boton "Ejecutar" de scripts Python (confirmado 2026-07-26 vía backend/logs/errors.jsonl).
    subprocess.run corre en un thread del pool (asyncio.to_thread) y no depende del
    loop del proceso, así que funciona sin importar qué event loop use uvicorn.
    """
    try:
        proc = subprocess.run(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=120,
        )
        text = proc.stdout.decode("utf-8", errors="replace")
        return {"ok": proc.returncode == 0, "output": text, "returncode": proc.returncode}
    except subprocess.TimeoutExpired as e:
        text = (e.output or b"").decode("utf-8", errors="replace")
        return {"ok": False, "output": text, "error": "Timeout (120s) ejecutando el script."}


async def _run_python_module(module: str, extra_args: list[str] = None) -> dict:
    cmd = [PYTHON, "-m", module] + (extra_args or [])
    return await asyncio.to_thread(_run_cmd_blocking, cmd, str(_REPO))


async def _run_python_file(filepath: str, cwd: str = None, extra_args: list = None) -> dict:
    cmd = [PYTHON, filepath] + (extra_args or [])
    return await asyncio.to_thread(_run_cmd_blocking, cmd, cwd or str(_REPO))


# ──────────────────────────────────────────────
# STATUS
# ──────────────────────────────────────────────
@router.get("/status")
async def get_status():
    mcp_up = mcp_http.is_mcp_running()
    revit_status = None
    if mcp_up:
        r = await mcp_http.get_revit_status()
        revit_status = r.get("output") if r.get("ok") else r.get("error")
    return {
        "mcp_running": mcp_up,
        "mcp_url": mcp_http.MCP_URL,
        "revit_status": revit_status,
        # Rutas/comando manual/último error de arranque — siempre incluido (barato:
        # solo os.path.exists), el frontend decide cuándo mostrarlo (Pedido Director
        # 2026-07-26: "si el MCP no es detectado, tiene que decir dónde está").
        "diagnostics": mcp_http.get_diagnostics(),
    }


@router.get("/health")
async def get_health():
    """Health check profundo: uptime del proceso MCP + latencia real del pipe Revit."""
    mcp_up = mcp_http.is_mcp_running()
    if not mcp_up:
        return {"mcp_running": False, "uptime_seconds": None, "pipe_ok": False, "latency_ms": None}
    ping = await mcp_http.ping_pipe()
    st = mcp_http._start_time
    uptime = (time.time() - st) if st else None
    return {
        "mcp_running": True,
        "uptime_seconds": uptime,
        "pipe_ok": ping["pipe_ok"],
        "latency_ms": ping["latency_ms"],
        "detail": ping.get("detail"),
    }


# ──────────────────────────────────────────────
# MCP LIFECYCLE
# ──────────────────────────────────────────────
@router.post("/start")
def start_mcp():
    return mcp_http.start_mcp()


@router.post("/stop")
def stop_mcp():
    return mcp_http.stop_mcp()


# ──────────────────────────────────────────────
# SCRIPTS CATALOG
# ──────────────────────────────────────────────
@router.get("/scripts")
def list_scripts():
    ironpy = [
        {"key": k, "file": v, "type": "ironpython",
         "label": {
             "dump":         "Dump Modelo (audit)",
             "dump-full":    "Full Dump (viewer)",
             "marks_master": "Set Marks Master",
             "keynote_path": "Obtener Ruta TXT",
             "marks_legacy": "Set Marks (Legacy)",
         }.get(k, k),
         "desc": {
             "dump":         "Vuelca keynotes, compuestos y schedules al JSON de auditoría (rápido).",
             "dump-full":    "Dump completo: project_info, levels, grids, views, sheets, rooms, all_instances, materials_full + secciones del dump de auditoría. Fuente de verdad para el Viewer 3D.",
             "marks_master": "Asigna TypeMark/Mark a materiales, tipos, floors y doors/windows desde csi_to_codigo.json.",
             "keynote_path": "Retorna la ruta del archivo .txt de keynotes cargado en el proyecto activo.",
             "marks_legacy": "⚠️ Deprecado — usa DB.Transaction. NO inyectar via execute_revit_code.",
         }.get(k, ""),
         "deprecated": k == "marks_legacy",
        }
        for k, v in _IRONPYTHON_SCRIPTS.items()
    ]
    python = [
        {"key": k, "type": "python", **{kk: vv for kk, vv in v.items() if kk not in ("module", "file", "cwd", "args")}}
        for k, v in _PYTHON_SCRIPTS.items()
    ]
    return {"ironpython": ironpy, "python": python}


# ──────────────────────────────────────────────
# IRONPYTHON INJECTION
# ──────────────────────────────────────────────
class InjectRequest(BaseModel):
    extra_args: Optional[dict] = None


@router.post("/inject/{name}")
async def inject_script(name: str, body: InjectRequest = None):
    if name not in _IRONPYTHON_SCRIPTS:
        raise HTTPException(404, f"Script '{name}' not found. Valid: {list(_IRONPYTHON_SCRIPTS.keys())}")
    if name == "marks_legacy":
        raise HTTPException(400, "revit_set_marks_snippet usa DB.Transaction — NO inyectar via execute_revit_code. Usar revit_marks_master.")
    try:
        code = _read_ironpython_code(_IRONPYTHON_SCRIPTS[name])
    except Exception as e:
        raise HTTPException(500, str(e))
    result = await mcp_http.execute_ironpython(code)
    return result


# ──────────────────────────────────────────────
# PYTHON SCRIPTS
# ──────────────────────────────────────────────
class ValidateUnitsRequest(BaseModel):
    csv_path: str


@router.post("/python/validate-units")
async def validate_units_sin_obra(body: ValidateUnitsRequest):
    """Ruta específica registrada ANTES de /python/{script}: 'validate-units' no vive
    en _PYTHON_SCRIPTS (solo aplica vía /obras/{pid}/validate-units), así que sin esta
    ruta el JS caía en el catch-all y devolvía 404 'not in catalog' cuando no hay obra
    activa seleccionada (validate_units.py no usa el pid de todas formas)."""
    return await _run_python_module("backend.scripts_runner.validate_units", [body.csv_path])


@router.post("/python/{script}")
async def run_python_script(script: str):
    if script not in _PYTHON_SCRIPTS:
        raise HTTPException(404, f"Script '{script}' not in catalog")
    meta = _PYTHON_SCRIPTS[script]
    if "module" in meta:
        return await _run_python_module(meta["module"], meta.get("args", []))
    elif "file" in meta:
        fp = os.path.abspath(meta["file"])
        return await _run_python_file(fp, cwd=meta.get("cwd"), extra_args=meta.get("args", []))
    raise HTTPException(500, "No module or file defined for script")


# ──────────────────────────────────────────────
# SCHEDULES
# ──────────────────────────────────────────────
@router.get("/schedules")
def list_schedules():
    files = sorted(_S5_DIR.glob("schedules_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "size": f.stat().st_size,
             "mtime": f.stat().st_mtime} for f in files[:20]]


# ──────────────────────────────────────────────
# OBRA-SPECIFIC SCRIPTS
# ──────────────────────────────────────────────
class ImportQtyRequest(BaseModel):
    csv_path: str


@router.post("/obras/{pid}/import-quantities")
async def import_quantities(pid: str, body: ImportQtyRequest):
    return await _run_python_module(
        "backend.scripts_runner.import_quantities",
        [pid, body.csv_path]
    )


@router.post("/obras/{pid}/validate-units")
async def validate_units(pid: str, body: ImportQtyRequest):
    return await _run_python_module(
        "backend.scripts_runner.validate_units",
        [body.csv_path]
    )


@router.post("/obras/{pid}/generate-keynotes")
async def generate_keynotes(pid: str):
    return await _run_python_module(
        "backend.scripts_runner.generate_keynotes",
        [pid]
    )


# ──────────────────────────────────────────────
# MCP DIRECT CALL (for advanced use)
# ──────────────────────────────────────────────
class ToolCallRequest(BaseModel):
    tool: str
    arguments: dict = {}


@router.post("/call")
async def call_mcp_tool(body: ToolCallRequest):
    return await mcp_http.call_tool(body.tool, body.arguments)


# ──────────────────────────────────────────────
# FULL DUMP — viewer data source
# ──────────────────────────────────────────────
_FULL_DUMP_PATH = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\project_full_dump.json")
_VIEWER_ROOT    = Path(r"D:\OneDrive\Bots\Viewer\projects")


@router.get("/full-dump")
async def get_full_dump():
    """Return project_full_dump.json. Run inject/dump-full first to generate it."""
    if not _FULL_DUMP_PATH.exists():
        raise HTTPException(
            404,
            "project_full_dump.json not found — run 'Full Dump (viewer)' from Revit MCP panel first."
        )
    with open(_FULL_DUMP_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("/full-dump/meta")
async def get_full_dump_meta():
    """Lightweight metadata check (mtime + section sizes) without loading full JSON."""
    if not _FULL_DUMP_PATH.exists():
        return {"exists": False}
    stat = _FULL_DUMP_PATH.stat()
    try:
        with open(_FULL_DUMP_PATH, encoding="utf-8") as f:
            data = json.load(f)
        mats = data.get("materials_full", [])
        mats_with_tex = sum(1 for m in mats if m.get("texture_paths"))
        return {
            "exists": True,
            "dump_version": data.get("_meta", {}).get("dump_version", "unknown"),
            "size_mb": round(stat.st_size / 1_048_576, 2),
            "mtime": stat.st_mtime,
            "project_name": data.get("project_info", {}).get("name") or data.get("project_info", {}).get("file_name"),
            "levels":    len(data.get("levels", [])),
            "views":     len(data.get("views", [])),
            "rooms":     len(data.get("rooms", [])),
            "instances": len(data.get("all_instances", [])),
            "materials": len(mats),
            "materials_with_textures": mats_with_tex,
            "compounds": len(data.get("compound_elements", [])),
        }
    except Exception as e:
        return {"exists": True, "size_mb": round(stat.st_size / 1_048_576, 2), "error": str(e)}


@router.get("/viewer-projects")
def list_viewer_projects():
    """List available GLB projects in the viewer folder."""
    if not _VIEWER_ROOT.exists():
        return []
    projects = []
    for proj_dir in sorted(_VIEWER_ROOT.iterdir()):
        if not proj_dir.is_dir():
            continue
        glb_files = list(proj_dir.glob("*_viewer.glb"))
        scene_idx = proj_dir / "scene_index.json"
        projects.append({
            "name":        proj_dir.name,
            "path":        str(proj_dir),
            "has_glb":     bool(glb_files),
            "glb_name":    glb_files[0].name if glb_files else None,
            "has_scene_index": scene_idx.exists(),
        })
    return projects


from fastapi.responses import FileResponse


@router.get("/viewer-glb/{project}/{filename}")
async def serve_viewer_glb(project: str, filename: str):
    """Serve GLB file for the 3D viewer."""
    path = _VIEWER_ROOT / project / filename
    if not path.exists() or path.suffix not in (".glb", ".json"):
        raise HTTPException(404, f"File not found: {filename}")
    media = "model/gltf-binary" if path.suffix == ".glb" else "application/json"
    return FileResponse(str(path), media_type=media)
