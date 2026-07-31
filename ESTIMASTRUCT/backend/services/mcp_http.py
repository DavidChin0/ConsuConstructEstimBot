"""mcp_http.py — Cliente HTTP para el MCP server de Revit (main_pipe.py --http en :8001).

CANON 2026-07-30: revit-estimastruct-audit quedó deprecado. revit-mcp-stdio es
el Revit MCP oficial de ConsuConstruct (agentes + EstimaStruct + pipe STDIO).
Protocolo idéntico (MCP JSON-RPC real, mismo tool execute_revit_code, mismo
puerto 8001) — verificado en vivo contra Revit real antes del swap.

start() lanza main_pipe.py --http como subproceso.
call_tool() envía tool/call JSON-RPC al endpoint MCP HTTP.
"""
from __future__ import annotations

import os, sys, subprocess, asyncio, json, time, tempfile, httpx
from pathlib import Path
from typing import Optional

MCP_URL   = "http://127.0.0.1:8001/mcp/"
MCP_PROBE = "http://127.0.0.1:8001/"
MCP_DIR   = r"D:\GitHub\revit-mcp-stdio\revit-mcp-stdio.extension"
MCP_SCRIPT = os.path.join(MCP_DIR, "main_pipe.py")
PYTHON     = r"D:\LLM\python\python.exe"

# 2026-07-26 (segunda ronda): antes stdout/stderr del Popen iban a DEVNULL — si
# main_pipe.py reventaba al arrancar, el error se perdía y el botón "Levantar MCP"
# parecía no hacer nada. Ahora se capturan en este archivo y se leen de vuelta si
# el arranque falla, para mostrarle al Director el stderr real.
MCP_LOG = Path(tempfile.gettempdir()) / "estimastruct_mcp_stdout.log"

_mcp_proc: Optional[subprocess.Popen] = None
# Epoch del último start exitoso. None = desconocido (proceso levantado antes de
# este restart de FastAPI) o MCP detenido.
_start_time: Optional[float] = None
# Diagnóstico legible del último intento de arranque fallido (None si el último fue ok).
_last_start_error: Optional[str] = None


def is_mcp_running() -> bool:
    try:
        import httpx as _hx
        _hx.get(MCP_PROBE, timeout=1.5)
        return True
    except Exception:
        return False


def get_diagnostics() -> dict:
    """Info concreta para cuando el MCP no se detecta: rutas + si existen +
    URL sondeada + comando manual copiable + stderr real del último intento fallido."""
    return {
        "python": PYTHON,
        "python_exists": os.path.exists(PYTHON),
        "script": MCP_SCRIPT,
        "script_exists": os.path.exists(MCP_SCRIPT),
        "cwd": MCP_DIR,
        "cwd_exists": os.path.isdir(MCP_DIR),
        "probe_url": MCP_PROBE,
        "manual_cmd": f'"{PYTHON}" "{MCP_SCRIPT}" --http',
        "last_start_error": _last_start_error,
    }


def _read_log_tail(max_chars: int = 4000) -> str:
    try:
        text = MCP_LOG.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]
    except Exception:
        return ""


def start_mcp() -> dict:
    global _mcp_proc, _start_time, _last_start_error
    if is_mcp_running():
        # Proceso ya arriba (posiblemente de antes de este restart de FastAPI):
        # si no tenemos _start_time, queda None → el frontend muestra "desconocido".
        _last_start_error = None
        return {"ok": True, "status": "already_running"}

    diag = get_diagnostics()
    if not diag["python_exists"]:
        _last_start_error = f"Intérprete Python no existe: {PYTHON}"
        return {"ok": False, "error": _last_start_error, "diagnostics": diag}
    if not diag["script_exists"]:
        _last_start_error = f"main_pipe.py no existe: {MCP_SCRIPT}"
        return {"ok": False, "error": _last_start_error, "diagnostics": diag}

    try:
        log_f = open(MCP_LOG, "w", encoding="utf-8", errors="replace")
    except Exception as e:
        _last_start_error = f"No se pudo crear el log de arranque ({MCP_LOG}): {e}"
        return {"ok": False, "error": _last_start_error, "diagnostics": diag}

    try:
        proc = subprocess.Popen(
            [PYTHON, MCP_SCRIPT, "--http"],
            cwd=MCP_DIR,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        log_f.close()
        _last_start_error = f"Popen falló: {e}"
        return {"ok": False, "error": _last_start_error, "diagnostics": diag}

    _mcp_proc = proc  # visible para stop_mcp() desde ya

    # Da 3s a que levante el HTTP en :8001. IMPORTANTE: de acá en adelante usar la
    # variable LOCAL `proc`, no el global `_mcp_proc` — si el Director hace click
    # en "Detener MCP" mientras este poll sigue corriendo, stop_mcp() (otro
    # request, otro thread) pone `_mcp_proc = None`, y leer el global de nuevo acá
    # revienta con AttributeError 'NoneType' object has no attribute 'pid'
    # (bug real encontrado en vivo 2026-07-26 con un Start seguido de Stop rápido).
    for _ in range(6):
        time.sleep(0.5)
        if is_mcp_running():
            _start_time = time.time()
            _last_start_error = None
            return {"ok": True, "status": "started", "pid": proc.pid}

    # No respondió: capturar el estado real (¿murió? ¿qué escribió?) en vez de
    # devolver un mensaje genérico sin pistas.
    try:
        log_f.flush()
    except Exception:
        pass
    proc_alive = proc.poll() is None
    stderr_tail = _read_log_tail()
    _last_start_error = stderr_tail or "Sin salida capturada (revisa el comando manual abajo)."
    return {
        "ok": False,
        "error": "MCP no respondió en :8001 tras 3s" + (" (el proceso murió)" if not proc_alive else " (el proceso sigue vivo, puede tardar más)"),
        "pid": proc.pid,
        "process_alive": proc_alive,
        "stderr_tail": stderr_tail,
        "diagnostics": diag,
    }


def stop_mcp() -> dict:
    global _mcp_proc, _start_time
    stopped_pid = None
    if _mcp_proc and _mcp_proc.poll() is None:
        stopped_pid = _mcp_proc.pid
        _mcp_proc.terminate()
        try:
            _mcp_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _mcp_proc.kill()
        _mcp_proc = None
    _start_time = None
    return {"ok": True, "stopped_pid": stopped_pid}


async def call_tool(tool_name: str, arguments: dict, timeout: int = 60) -> dict:
    """POST a tools/call JSON-RPC message to MCP HTTP server."""
    msg = {
        "jsonrpc": "2.0",
        "id": "web-1",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(MCP_URL, json=msg, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Extract text content from MCP response
            result = data.get("result", data)
            content = result.get("content", []) if isinstance(result, dict) else []
            text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            return {
                "ok": True,
                "output": "\n".join(text_parts) if text_parts else json.dumps(result),
                "raw": data,
            }
    except httpx.ConnectError:
        return {"ok": False, "error": "MCP server not running. Presiona 'Levantar MCP'."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_revit_status() -> dict:
    return await call_tool("get_revit_status", {}, timeout=10)


async def ping_pipe() -> dict:
    """Health check profundo: round-trip real JSON-RPC contra el pipe de Revit.

    pipe_ok = True SOLO si call_tool respondió ok:true (no basta respuesta HTTP).
    """
    t0 = time.time()
    r = await get_revit_status()
    latency_ms = round((time.time() - t0) * 1000.0, 1)
    ok = bool(r.get("ok"))
    return {
        "pipe_ok": ok,
        "latency_ms": latency_ms,
        "detail": r.get("output") if ok else r.get("error"),
    }


async def execute_ironpython(code: str) -> dict:
    return await call_tool("execute_revit_code", {"code": code}, timeout=90)
