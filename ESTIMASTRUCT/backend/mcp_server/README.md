# estimastruct-mcp

Servidor MCP STDIO de EstimaStruct. Deja que cualquier cliente MCP (Claude Code,
Codex, Claude Desktop) opere presupuestos sin aprenderse la API REST.

## Arranque

```bash
python -m backend.mcp_server
```

Desde la raíz del repo (`ESTIMASTRUCT/`). No imprime nada: STDIO es el canal del
protocolo, no una consola — si ves texto suelto ahí, algo está escribiendo a
stdout y va a romper el handshake.

**Requiere el backend FastAPI arriba** (`START_POSTGRES_UNICA.ps1`). Las tools no
tocan Postgres: hablan HTTP contra la API, así hay una sola implementación de la
lógica de negocio.

## Variables de entorno

| Variable | Default | Para qué |
|---|---|---|
| `ESTIMASTRUCT_API_BASE` | `http://127.0.0.1:8002` | A qué API apuntar. **Este es el interruptor para AWS**: cuando el SaaS esté desplegado, se apunta a la URL pública y el mismo servidor MCP sirve sin cambiar código. |
| `ESTIMASTRUCT_MCP_TIMEOUT` | `60` | Segundos por request. |

## Cableado

### Claude Code

`.mcp.json` en la raíz del proyecto, o `claude mcp add`:

```json
{
  "mcpServers": {
    "estimastruct": {
      "command": "D:\\LLM\\python\\python.exe",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "D:\\GitHub\\EstimBot\\ConsuConstructEstimBot\\ESTIMASTRUCT",
      "env": { "ESTIMASTRUCT_API_BASE": "http://127.0.0.1:8002" }
    }
  }
}
```

### Claude Desktop

Mismo bloque dentro de `mcpServers` en `claude_desktop_config.json`
(`%APPDATA%\Claude\`).

## Tools (v1 — núcleo presupuestal)

| Tool | Efecto |
|---|---|
| `listar_obras` | lectura |
| `obtener_obra` | lectura |
| `listar_capitulos` | lectura |
| `listar_partidas` | lectura |
| `buscar_partida_por_csi` | lectura — de keynote de Revit a partida |
| `obtener_insumos_partida` | lectura |
| `reporte_obra` | lectura |
| `obtener_cronograma` | lectura |
| `insumos_de_obra` | lectura |
| `actualizar_cantidad` | **escribe** |
| `calcular_obra` | **escribe** (recalcula totales) |
| `ajustar_cuadrilla` | **escribe** (mueve fechas del cronograma) |

Tres tools escriben en obras reales. Los docstrings lo dicen para que el modelo
del otro lado pida confirmación, pero **el servidor no exige aprobación por sí
mismo** — eso lo pone el cliente MCP. Apuntar esto a una obra en producción sin
el gate de permisos del cliente es escribir sin red.

## Fuera de alcance a propósito

Los módulos de ingeniería (diseño estructural, acero, conexiones, sismo, bases)
son ~45 endpoints con contratos más inestables: saturarían la lista de tools y
habría que versionarlos aparte. El runner de scripts tampoco está: expone
ejecución de procesos del servidor y merece su propia decisión de seguridad.

## Gotchas

- **Los ids son UUID en texto, no enteros.** Obra, capítulo y partida. Tiparlos
  como `int` hace que el cliente mande un número y la API devuelva 404 sin
  explicar por qué.
- **FastMCP emite un bloque de contenido por ítem** cuando una tool devuelve una
  lista. Un cliente que lea solo `content[0]` ve el primer elemento y cree que la
  tool devolvió un objeto suelto.
