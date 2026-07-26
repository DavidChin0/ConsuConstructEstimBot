> [!CONTEXT]
> SOP canónico de integración EstimaStruct ↔ Revit MCP al 2026-07-19. Aterriza el flujo real de catálogo, keynotes, schedules, auditoría y write asistido.

> [!WARNING]
> **DEPRECADO 2026-07-21.** Estado actual vive en [`docs/architecture.md §8`](architecture.md).
> Cubre integración Revit MCP Broker — ver §8 Connections + §5.2 Flow Import Revit.
> Este archivo es registro histórico — no actualizar.

# SOP — EstimaStruct ↔ Revit MCP 2026-07-19

## 1. Propósito

Definir un solo flujo operativo para trabajar EstimaStruct con Revit MCP sin romper la semántica del sistema.

## 2. Regla madre

La autoridad semántica vive en EstimaStruct.

Eso significa:

- `CSI` manda
- catálogo EstimaStruct manda
- presupuesto EstimaStruct manda
- Revit MCP inspecciona, audita y ejecuta writes asistidos

## 3. Cuándo usar Revit MCP

Usar Revit MCP para:

- leer tipos, instancias y materiales
- leer o verificar keynotes
- sacar dumps de auditoría
- validar template/target
- aplicar writes controlados y verificables

No usar Revit MCP para:

- inventar partidas
- redefinir el catálogo
- decidir el costo
- sustituir la base de datos de EstimaStruct

## 4. Flujo canónico

### Paso 1 — Fijar catálogo en EstimaStruct

Antes de tocar Revit:

1. validar la ficha/matriz en EstimaStruct
2. validar `CSI`
3. validar descripción
4. validar insumos si el caso es costeo real

Archivos fuente:

- `development/Template2_Updated/`
- `backend/routers/bases.py`
- `backend/services/pricing.py`

### Paso 2 — Generar keynotes desde EstimaStruct

Acción:

- correr `generate_keynotes.py` o `POST /presupuestos/{pid}/scripts/keynotes`

Objetivo:

- que Revit lea el catálogo semántico emitido por EstimaStruct

### Paso 3 — Cargar / recargar keynotes en Revit

Acción humana o asistida:

- cargar el `keynotes.txt` correcto en Revit
- confirmar que el archivo activo es el recién generado

Gotcha real:

- el encoding importa
- el documento canónico de runtime y changelog ya dejaron trazado el caso UTF-8 sin BOM

### Paso 4 — Extraer modelo con Revit MCP

Acción:

- usar Revit MCP para leer el modelo real
- sacar dump o auditoría

Scripts reales:

- `backend/scripts_runner/revit_dump_snippet.py`
- `backend/scripts_runner/audit_keynotes.py`

### Paso 5 — Auditar contra EstimaStruct

Acción:

- comparar lo que existe en Revit contra el catálogo de EstimaStruct

Resultado esperado:

- `GREEN` = semántica alineada
- `RED` = falta catálogo, falta keynote, texto divergente o elemento ambiguo

### Paso 6 — Corregir en el orden correcto

Orden correcto:

1. corregir catálogo EstimaStruct si el problema es semántico
2. regenerar keynotes si cambió catálogo
3. corregir modelo Revit por MCP si el problema es asignación
4. reauditar

Nunca al revés.

## 5. Flujo de cantidades

Cuando el objetivo es costeo:

1. pyRevit exporta schedules
2. EstimaStruct importa cantidades
3. EstimaStruct recalcula presupuesto
4. Revit MCP solo verifica coherencia si hace falta

Endpoint:

- `POST /presupuestos/{pid}/scripts/import-quantities`

## 6. Flujo de materiales / template

Cuando el objetivo es normalizar template o materiales:

1. usar diccionario del template y outputs de auditoría
2. construir contrato de reemplazo fuera del modelo
3. ejecutar write MCP sobre subconjunto seguro
4. verificar en la misma corrida o con segunda lectura

Contrato ya existente en EstimaStruct:

- `backend/scripts_runner/build_material_replacement_contract.py`

Regla:

- primero `KEEP / REPLACE_SAFE / REVIEW_DIRECTOR`
- después write

## 7. Tipos de operación MCP permitidos

### Permitido

- lectura de status
- lectura de types/materiales/keynotes
- refresh de vista
- dump de auditoría
- write puntual y verificable sobre tipos/materiales/keynotes

### Prohibido sin gate explícito

- write masivo ciego
- reemplazo semántico sin contrato previo
- asumir que un falso positivo de bridge equivale a cambio persistido

## 8. Criterio de verificación

Todo write MCP serio debe cerrar con:

1. confirmación de selección exacta
2. write ejecutado
3. verificación en el mismo contexto o segunda lectura
4. nueva auditoría si cambió semántica visible

## 9. Artefactos de salida correctos

Los entregables canónicos del flujo deben caer en:

- repo EstimaStruct: `docs/` y `backend/scripts_runner/`
- vault `revit-mcp-audit`: referencias y outputs verificables
- carpeta externa de auditorías cuando aplique

## 10. Documentos ligados

- `docs/source_of_truth_estimastruct_20260719.md`
- `docs/manual_mega_operativo_estimastruct_20260719.md`
- `docs/postgres_runtime_estimastruct_20260719.md`
- `03 Automation Projects/revit-mcp-audit/index.md`

## 11. Regla final

Si una sesión futura toca Revit MCP dentro de EstimaStruct, este SOP manda antes que cualquier improvisación de chat o memoria parcial.
