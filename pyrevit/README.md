# pyrevit/ — código pyRevit de EstimBot (árbol canon)

Consolidación goal-19685 (2026-07-30). Antes de esto el código pyRevit vivía en 3 sitios,
dos de ellos sin git. Ahora **todo el código de botones pyRevit vive acá**.

## Qué hay

| Ruta | Qué es |
|---|---|
| `pyrevit\EstimBot.extension\` | La extensión pyRevit **VIVA**, la que Revit carga. 8 pushbuttons. |
| `pyrevit\scripts\` | Paquete Python (`__init__.py`) con la lógica pesada que los botones importan. |
| `pyrevit\_legacy\ExportTools.extension\` | Extensión **MUERTA**, nunca estuvo en un search path de pyRevit. Archivada, no borrada. |
| `pyrevit\_legacy\scripts_sin_wiring\` | Scripts `PYR_*` / `PYREVIT_*` originales. Su lógica ya fue copiada dentro de los `script.py` de los botones. Ningún botón los importa. |

## Cómo lo encuentra pyRevit

pyRevit escanea por defecto `C:\Users\consu\AppData\Roaming\pyRevit\Extensions\`.
Ahí ya no hay una copia real de EstimBot: hay un **junction de directorio** que apunta acá:

```
C:\Users\consu\AppData\Roaming\pyRevit\Extensions\EstimBot.extension
   --> D:\GitHub\EstimBot\ConsuConstructEstimBot\pyrevit\EstimBot.extension
```

Se eligió junction en vez de agregar la ruta a `userextensions` en
`C:\Users\consu\AppData\Roaming\pyRevit\pyRevit_config.ini` porque **pyRevit reescribe
ese .ini solo** (se observó modificado por el propio pyRevit el 2026-07-30), y una entrada
agregada a mano puede perderse en cualquier rewrite. El junction no depende de la config.

Junction (no symlink) porque no requiere privilegios de administrador y funciona
cross-volume (C: -> D:).

## Wiring botón -> lógica

| Pushbutton | Depende de |
|---|---|
| `Export.panel\Export Steel Connections` | `sys.path` += `pyrevit\scripts` -> `import count_connections` |
| `Plumbing.panel\Generate Layout` | `sys.path` += `pyrevit` -> `from scripts.generate_layout_core import ...` |
| `Export.panel\Export Keynote Map` | imprime instrucción para correr `pyrevit\scripts\viewer_postprocess.py` |
| `Export.panel\Exportar Schedules` | autocontenido |
| `EstimaStruct.panel\Autotag Keynotes` | autocontenido |
| `Electrical.panel\Conduit by Ciruit` | autocontenido |
| `Utilities.panel\Borrar MEP Generado` | autocontenido |
| `Export.panel\Exportar Keynotes` | **stub deprecado** (CASE-MARKS-001, 2026-07-19) — solo muestra un alert |
| `EstimaStruct.panel\Autodim by Axis` | **stub deprecado** (CASE-MARKS-001, 2026-07-19) — solo muestra un alert |

## Código vs datos

Se movió **solo el código**. Las rutas de datos siguen apuntando a OneDrive a propósito
y NO deben versionarse:

- `D:\OneDrive\Bots\Estimbot\EXPORTS\` — CSVs y JSON que producen los botones
- `D:\OneDrive\Bots\Estimbot\logs\` — logs de `Generate Layout`
- `D:\OneDrive\Bots\Estimbot\revit_lib\tags\` — usado por el MCP `revit_sync_type_marks`

## Python

Cualquier script de este árbol corrido fuera de Revit usa `D:\LLM\python\python.exe`.
Dentro de Revit corre bajo IronPython 2.7 (por eso `reload()` sin import de `importlib`).
