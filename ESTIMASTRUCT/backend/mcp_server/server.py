"""estimastruct-mcp — servidor MCP STDIO sobre la API de EstimaStruct.

Objetivo: que un usuario pueda hablarle a EstimaStruct desde cualquier cliente MCP
(Claude Code, Codex, Claude Desktop) sin levantar nada a mano ni aprenderse la API
REST. Se dispara por comando:

    python -m backend.mcp_server

Diseno
------
Las tools NO tocan la base de datos ni importan los routers: hablan HTTP contra la
API FastAPI existente. Eso mantiene una sola implementacion de la logica de negocio
y, sobre todo, hace que el mismo servidor MCP sirva apuntando a localhost hoy y a
la API en AWS cuando el SaaS este listo — solo cambia `ESTIMASTRUCT_API_BASE`.

Superficie v1: **nucleo presupuestal** (decision del Director 2026-07-26). Los
modulos de ingenieria (diseno estructural, acero, conexiones, sismo, bases) quedan
fuera a proposito: son ~45 endpoints con contratos mas inestables y saturarian la
lista de tools del cliente. El runner de scripts tambien queda fuera — expone
ejecucion de procesos y merece su propia decision.

Variables de entorno
--------------------
    ESTIMASTRUCT_API_BASE   default http://127.0.0.1:8002
    ESTIMASTRUCT_MCP_TIMEOUT default 60 (segundos)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("ESTIMASTRUCT_API_BASE", "http://127.0.0.1:8002").rstrip("/")
TIMEOUT = float(os.environ.get("ESTIMASTRUCT_MCP_TIMEOUT", "60"))

mcp = FastMCP("estimastruct")

# NOTA: todos los ids de EstimaStruct (obra, capitulo, partida) son UUID en texto,
# no enteros. Tiparlos como int hace que el cliente MCP mande un numero y la API
# devuelva 404 sin explicar por que.


# ---------------------------------------------------------------------------
# Cliente HTTP
# ---------------------------------------------------------------------------
async def _call(method: str, path: str, **kw: Any) -> Any:
    """Pega a la API de EstimaStruct y devuelve JSON, o un dict de error legible.

    Nunca lanza: un cliente MCP muestra mejor un error descriptivo que un stack
    trace, y el modelo del otro lado puede reaccionar al mensaje.
    """
    url = "{}{}".format(API_BASE, path)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(method, url, **kw)
    except httpx.ConnectError:
        return {
            "error": "No hay respuesta de la API de EstimaStruct en {}. "
                     "Levanta el backend (START_POSTGRES_UNICA.ps1) o ajusta "
                     "ESTIMASTRUCT_API_BASE.".format(API_BASE)
        }
    except httpx.TimeoutException:
        return {"error": "Timeout ({}s) llamando {} {}".format(TIMEOUT, method, path)}

    if resp.status_code >= 400:
        return {
            "error": "HTTP {} en {} {}".format(resp.status_code, method, path),
            "detail": resp.text[:500],
        }

    try:
        return resp.json()
    except ValueError:
        return {"ok": True, "raw": resp.text[:2000]}


# ---------------------------------------------------------------------------
# Obras
# ---------------------------------------------------------------------------
@mcp.tool()
async def listar_obras(incluir_templates: bool = False) -> Any:
    """Lista las obras (presupuestos) disponibles con su id, nombre y cliente.

    Punto de partida habitual: casi toda otra tool necesita un `pid` de obra.
    Por defecto omite las plantillas (`es_template`).
    """
    data = await _call("GET", "/presupuestos")
    if isinstance(data, dict) and data.get("error"):
        return data
    if not incluir_templates and isinstance(data, list):
        return [o for o in data if not o.get("es_template")]
    return data


@mcp.tool()
async def obtener_obra(pid: str) -> Any:
    """Devuelve la cabecera de una obra: nombre, cliente, totales, sobrecosto."""
    return await _call("GET", "/presupuestos/{}".format(pid))


@mcp.tool()
async def listar_capitulos(pid: str) -> Any:
    """Lista los capitulos de una obra. Cada capitulo agrupa partidas."""
    return await _call("GET", "/presupuestos/{}/capitulos".format(pid))


# ---------------------------------------------------------------------------
# Partidas
# ---------------------------------------------------------------------------
@mcp.tool()
async def listar_partidas(capitulo_id: str) -> Any:
    """Lista las partidas de un capitulo, con cantidad, unidad y precios."""
    return await _call("GET", "/capitulos/{}/partidas".format(capitulo_id))


@mcp.tool()
async def buscar_partida_por_csi(clave_csi: str) -> Any:
    """Busca partidas por clave CSI (ej. '03 21 11.1').

    Util para ir de un keynote de Revit a la partida presupuestal que le
    corresponde sin tener que recorrer capitulos.
    """
    return await _call("GET", "/partidas/by-csi/{}".format(clave_csi))


@mcp.tool()
async def actualizar_cantidad(partida_id: str, cantidad: float) -> Any:
    """Cambia la cantidad de una partida y recalcula sus totales.

    ESCRIBE en la base de datos de la obra. Confirmar con el usuario antes de
    usarla sobre una obra real.
    """
    return await _call(
        "PATCH", "/partidas/{}/cantidad".format(partida_id),
        json={"cantidad": cantidad},
    )


@mcp.tool()
async def obtener_insumos_partida(partida_id: str) -> Any:
    """Devuelve el desglose de insumos de una partida: materiales, mano de obra,
    equipo, con rendimiento y precio unitario."""
    return await _call("GET", "/partidas/{}/insumos".format(partida_id))


# ---------------------------------------------------------------------------
# Calculo
# ---------------------------------------------------------------------------
@mcp.tool()
async def calcular_obra(pid: str) -> Any:
    """Recalcula toda la obra: costos directos, sobrecosto y total.

    ESCRIBE los totales recalculados. Correr despues de cambiar cantidades o
    precios para que los reportes queden consistentes.
    """
    return await _call("POST", "/presupuestos/{}/calcular".format(pid))


@mcp.tool()
async def reporte_obra(pid: str) -> Any:
    """Reporte resumido de la obra: totales por capitulo y gran total."""
    return await _call("GET", "/presupuestos/{}/reporte".format(pid))


# ---------------------------------------------------------------------------
# Cronograma
# ---------------------------------------------------------------------------
@mcp.tool()
async def obtener_cronograma(pid: str) -> Any:
    """Cronograma de ejecucion (Gantt): actividades con duracion, fechas de
    inicio/fin, fase y cuadrilla asignada."""
    return await _call("GET", "/presupuestos/{}/cronograma".format(pid))


@mcp.tool()
async def ajustar_cuadrilla(pid: str, partida_id: str, n_esp: int, n_ay: int) -> Any:
    """Cambia la cuadrilla de una actividad (especialistas y ayudantes) y
    recalcula las fechas del cronograma.

    ESCRIBE. Mas gente en paralelo acorta la duracion de esa actividad y
    desplaza las que dependen de ella.
    """
    return await _call(
        "POST", "/presupuestos/{}/cronograma/personal".format(pid),
        json={"partida_id": partida_id, "n_esp": n_esp, "n_ay": n_ay},
    )


# ---------------------------------------------------------------------------
# Insumos de obra
# ---------------------------------------------------------------------------
@mcp.tool()
async def insumos_de_obra(pid: str) -> Any:
    """Insumos consolidados de toda la obra: que hay que comprar y cuanto.

    Devuelve el mismo contenido que el export de insumos, en JSON.
    """
    return await _call("GET", "/presupuestos/{}/export-insumos".format(pid),
                       headers={"Accept": "application/json"})


# ---------------------------------------------------------------------------
# RAG semantico (conocimiento propio de EstimaStruct)
# ---------------------------------------------------------------------------
@mcp.tool()
async def estima_rag_search(query: str, top_k: int = 5) -> Any:
    """Busca en el conocimiento propio de EstimaStruct: motor de calculo,
    fichas de costeo, arquitectura del sistema (no datos de una obra especifica).

    Hibrido keyword+semantico sobre rag.sqlite. Util para preguntas de "como
    funciona X" o "donde esta implementado Y", no para consultar una obra real
    (para eso usar las demas tools sobre /presupuestos).
    """
    return await _call("GET", "/rag/search", params={"q": query, "top_k": top_k})


def main() -> None:
    """Arranca el servidor MCP sobre STDIO."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
