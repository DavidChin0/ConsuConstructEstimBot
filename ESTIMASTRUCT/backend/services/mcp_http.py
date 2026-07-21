"""mcp_http.py — Cliente HTTP para el MCP server de Revit (main_pipe.py --http en :8001).

start() lanza main_pipe.py --http como subproceso.
call_tool() envía tool/call JSON-RPC al endpoint MCP HTTP.
"""
from __future__ import annotations

import os, sys, subprocess, asyncio, json, time, httpx
from typing import Optional

MCP_URL   = "http://127.0.0.1:8001/mcp/"
MCP_PROBE = "http://127.0.0.1:8001/"
MCP_DIR   = r"D:\GitHub\revit-estimastruct-audit\mcp_server"
MCP_SCRIPT = os.path.join(MCP_DIR, "main_pipe.py")
PYTHON     = r"D:\LLM\python\python.exe"

_mcp_proc: Optional[subprocess.Popen] = None
# Epoch del último start exitoso. None = desconocido (proceso levantado antes de
# este restart de FastAPI) o MCP detenido.
_start_time: Optional[float] = None


def is_mcp_running() -> bool:
    try:
        import httpx as _hx
        _hx.get(MCP_PROBE, timeout=1.5)
        return True
    except Exception:
        return False


def start_mcp() -> dict:
    global _mcp_proc, _start_time
    if is_mcp_running():
        # Proceso ya arriba (posiblemente de antes de este restart de FastAPI):
        # si no tenemos _start_time, queda None → el frontend muestra "desconocido".
        return {"ok": True, "status": "already_running"}
    if not os.path.exists(MCP_SCRIPT):
        return {"ok": False, "error": f"main_pipe.py not found: {MCP_SCRIPT}"}
    _mcp_proc = subprocess.Popen(
        [PYTHON, MCP_SCRIPT, "--http"],
        cwd=MCP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give it 3s to start
    for _ in range(6):
        time.sleep(0.5)
        if is_mcp_running():
            _start_time = time.time()
            return {"ok": True, "status": "started", "pid": _mcp_proc.pid}
    return {"ok": False, "error": "MCP started but HTTP not responding on :8001", "pid": _mcp_proc.pid}


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
