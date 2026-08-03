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
  POST /revit-mcp/obras/{pid}/audit-pipeline
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
# IronPython snippets (have CODE = r'''...''' / VAR = r'''...''' pattern)
# ──────────────────────────────────────────────
# ADR-012 (2026-08-02): dump/dump-full/marks_master viven consolidados en
# revit-mcp-stdio (D:\GitHub\revit-mcp-stdio\revit_mcp\pipe\estimastruct_tools.py)
# como DUMP_AUDIT_CODE/DUMP_FULL_CODE/SET_MARKS_CODE — ya no en scripts_runner/.
_ESTIMASTRUCT_TOOLS_PATH = Path(r"D:\GitHub\revit-mcp-stdio\revit_mcp\pipe\estimastruct_tools.py")

_IRONPYTHON_SCRIPTS = {
    "dump":          (_ESTIMASTRUCT_TOOLS_PATH, "DUMP_AUDIT_CODE"),
    "dump-full":     (_ESTIMASTRUCT_TOOLS_PATH, "DUMP_FULL_CODE"),
    "marks_master":  (_ESTIMASTRUCT_TOOLS_PATH, "SET_MARKS_CODE"),
    "keynote_path":  (_SCRIPTS_DIR / "revit_get_keynote_path.py", "CODE"),
    "marks_legacy":  (_SCRIPTS_DIR / "revit_set_marks_snippet.py", "CODE"),
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
        "label":  "Viewer Post-process (OBJ, legacy)",
        "desc":   "LEGACY — convierte OBJ exports a GLB. El export OBJ de Revit fusiona geometría y pierde el ElementId, así que el GLB queda sin identidad por elemento. Usar 'Viewer IFC → GLB' en su lugar.",
        "args":   [],
    },
    "viewer-ifc-glb": {
        "module": "backend.scripts_runner.viewer_ifc_pipeline",
        "label":  "Viewer IFC → GLB",
        "desc":   "Exporta el modelo abierto a IFC4 vía MCP y lo convierte a GLB con un nodo por elemento (nombre = ElementId) y keynote/categoría/nivel horneados en los extras. Reemplaza el pipeline OBJ. Requiere Revit abierto + MCP online.",
        "args":   [],
    },
}


def _read_ironpython_code(path: Path, var_name: str = "CODE") -> str:
    src = path.read_text(encoding="utf-8")
    # Ancla ^ + MULTILINE: sin esto, un docstring que documente el patron de
    # extraccion (ej. `CODE = r'''(.*?)'''` como texto de ejemplo) se auto-matchea
    # antes que el bloque real, porque no esta al inicio de linea (bug real
    # encontrado 2026-08-02 en revit_get_keynote_path.py via goal-20191).
    m = re.search(r"^" + var_name + r" = r'''(.*?)'''", src, re.DOTALL | re.MULTILINE)
    if not m:
        raise ValueError(f"No {var_name} block found in {path}")
    return m.group(1)


# ──────────────────────────────────────────────
# PIPECLIENT ACTIONS  (ADR-012 / goal-20178, expuesto por goal-20188)
# ──────────────────────────────────────────────
# dump/dump-full/marks_master viven como funciones en revit-mcp-stdio
# (estimastruct_tools.py) sobre PipeClient (Named Pipe) — el transporte verificado
# en vivo 2026-08-02 (140 objects / 349 keynotes / 102 compound, 4.3s). A diferencia
# de /inject/{name}, que corre el mismo CODE pero por el MCP HTTP :8001 frágil
# (execute_ironpython) y exige "Levantar MCP", estas NO necesitan el MCP levantado:
# solo Revit abierto con el modelo activo + revit-mcp-stdio instalado (dependencia
# de instalación, ADR-001). El connect_timeout lo fija cada función (60/120s).
_REVIT_MCP_STDIO_REPO = _ESTIMASTRUCT_TOOLS_PATH.parents[2]   # D:\GitHub\revit-mcp-stdio

# keys que se sirven por PipeClient en vez de /inject (ver list_scripts / frontend)
_PIPE_KEYS = {"dump", "dump-full", "marks_master"}


def _pipe_funcs() -> dict:
    """Importa las funciones PipeClient de revit-mcp-stdio (mismo patrón sys.path
    que scripts_router._trigger_revit_dump). Import perezoso: no cargar el repo al
    importar el router, solo al primer uso real de una acción pipe."""
    if str(_REVIT_MCP_STDIO_REPO) not in sys.path:
        sys.path.insert(0, str(_REVIT_MCP_STDIO_REPO))
    from revit_mcp.pipe.estimastruct_tools import (
        dump_audit_json, dump_full_json, set_marks_master,
    )
    return {
        "dump":         dump_audit_json,
        "dump-full":    dump_full_json,
        "marks_master": set_marks_master,
    }


def _pipe_normalize(resp: dict) -> dict:
    """Normaliza el dict crudo del pipe ({v,id,ok,result|error}) al shape {ok,output}
    que ya renderiza rmcpRunScript en el frontend — así la card pipe usa el mismo
    camino de log que /inject sin ramas nuevas. Nunca pierde info: cae a json.dumps."""
    if not isinstance(resp, dict):
        return {"ok": False, "output": str(resp)}
    ok = bool(resp.get("ok", False))
    result = resp.get("result", {})
    text = None
    if isinstance(result, dict):
        for k in ("output", "stdout", "message", "text"):
            if result.get(k):
                text = result[k]
                break
        if text is None and isinstance(result.get("content"), list):
            parts = [c.get("text", "") for c in result["content"]
                     if isinstance(c, dict) and c.get("text")]
            text = "\n".join(parts) if parts else None
    err = resp.get("error")
    if text is None and err and not ok:
        text = err.get("message") if isinstance(err, dict) else str(err)
    if text is None:
        text = json.dumps(result or resp, ensure_ascii=False)
    out = {"ok": ok, "output": text}
    if not ok and err:
        out["error"] = err.get("message") if isinstance(err, dict) else str(err)
    return out


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
        {"key": k, "file": v[0].name, "type": "ironpython",
         "label": {
             "dump":         "Dump Modelo (audit)",
             "dump-full":    "Full Dump (viewer)",
             "marks_master": "Set Marks Master",
             "keynote_path": "Obtener Ruta TXT",
             "marks_legacy": "Set Marks (Legacy)",
         }.get(k, k),
         "desc": {
             "dump":         "Vuelca keynotes, compuestos y schedules al JSON de auditoría (rápido). Vía PipeClient — no requiere Levantar MCP, solo Revit abierto.",
             "dump-full":    "Dump completo: project_info, levels, grids, views, sheets, rooms, all_instances, materials_full + secciones del dump de auditoría. Fuente de verdad para el Viewer 3D. Vía PipeClient — no requiere Levantar MCP.",
             "marks_master": "Asigna TypeMark/Mark a materiales, tipos, floors y doors/windows desde csi_to_codigo.json. Vía PipeClient — no requiere Levantar MCP.",
             "keynote_path": "Retorna la ruta del archivo .txt de keynotes cargado en el proyecto activo.",
             "marks_legacy": "⚠️ Deprecado — usa DB.Transaction. NO inyectar via execute_revit_code.",
         }.get(k, ""),
         "deprecated": k == "marks_legacy",
         # goal-20188: dump/dump-full/marks_master se sirven por PipeClient (/pipe/{key},
         # transporte verificado 2026-08-02) en vez de /inject (MCP HTTP :8001). El
         # frontend usa este flag para rutear la card y NO exigir MCP online.
         "transport": "pipe" if k in _PIPE_KEYS else "mcp",
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
        code = _read_ironpython_code(*_IRONPYTHON_SCRIPTS[name])
    except Exception as e:
        raise HTTPException(500, str(e))
    result = await mcp_http.execute_ironpython(code)
    return result


# ──────────────────────────────────────────────
# PIPECLIENT INJECTION  (goal-20188 — acción de usuario, transporte verificado)
# ──────────────────────────────────────────────
@router.post("/pipe/{name}")
async def run_pipe_action(name: str):
    """Corre dump/dump-full/marks_master vía PipeClient (Named Pipe), el transporte
    verificado en vivo 2026-08-02 (goal-20178). A diferencia de /inject/{name} (MCP
    HTTP :8001), NO requiere 'Levantar MCP' — solo Revit abierto con el modelo activo.
    Bloqueante (socket I/O), así que va a un thread (asyncio.to_thread) para no
    tapar el event loop de uvicorn — mismo motivo que _run_cmd_blocking."""
    funcs = _pipe_funcs()
    fn = funcs.get(name)
    if fn is None:
        raise HTTPException(404, f"Acción pipe '{name}' no existe. Válidas: {list(funcs.keys())}")
    try:
        resp = await asyncio.to_thread(fn)
    except Exception as e:
        return {
            "ok": False,
            "error": f"PipeClient falló ({type(e).__name__}): {e}",
            "output": f"PipeClient falló ({type(e).__name__}): {e}. ¿Revit abierto con el modelo activo y revit-mcp-stdio instalado?",
        }
    return _pipe_normalize(resp)


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


@router.post("/obras/{pid}/audit-pipeline")
async def audit_pipeline(pid: str):
    # goal-20192: vivia en _PYTHON_SCRIPTS como script "generico" (sin args),
    # pero run_audit_pipeline.py necesita obra_id para su ultimo paso
    # (sync_audit_colors) -- /python/{script} no pasa params dinamicos. Movido
    # a ruta obra-scoped, mismo patron que generate-keynotes/import-quantities.
    return await _run_python_module(
        "backend.scripts_runner.run_audit_pipeline",
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
