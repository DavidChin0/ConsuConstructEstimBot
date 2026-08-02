# -*- coding: utf-8 -*-
"""
Revit "dibujar desde la base de datos" — memoria de PROCEDIMIENTO (2026-08-01).

goal-20150 (Postgres `consuconstruct`, brain.goals). Primer archivo de
`backend/cag/` — el directorio en sí NO existía antes de este archivo. Es el
directorio anunciado en `docs/architecture.md:290,382` (ADR-007/008/009,
CASE-SAAS-001) como "2. LLM Anthropic API + CAG en `backend/cag/`" — un ítem
de roadmap, no algo ya construido. Este módulo es el primer contenido real que
se escribe ahí.

────────────────────────────────────────────────────────────────────────────
POR QUÉ ESTE ARCHIVO **NO** USA EL CONTRATO `{meta, pasos[], constantes[],
resultado{}}` DE `backend/services/*_memoria.py`
────────────────────────────────────────────────────────────────────────────
Ese contrato (ADR-003, ver `docs/auditoria_formulas_mapa_estructura.md` y el
router `backend/routers/auditoria_formulas.py`) narra un MOTOR PURO de
CÁLCULO NUMÉRICO: cada `_paso()` es una fórmula con símbolo, sustitución
aritmética y LaTeX. Sirve para auditar dinero/ingeniería (pricing, cronograma,
acero, sismo, mampostería, prorrateo bancario...).

El flujo "dibujar desde la base de datos" no es una fórmula: es un
PROCEDIMIENTO de orquestación (scripts + tools MCP + un corte manual donde el
usuario dibuja en Revit). Forzarlo al molde `_paso()`/LaTeX habría sido
inventar una convención que no le corresponde — la regla dura del proyecto es
justo la contraria ("antes de crear un archivo, leer los comparables
existentes para no inventar convenciones"). Este módulo toma del patrón
`_memoria.py` lo que SÍ aplica — el tono narrado, las referencias a
archivo/línea real, los gotchas explícitos, el "no inventar, marcar TODO" — y
lo aplica a una lista de PASOS DE PROCEDIMIENTO en vez de una lista de
fórmulas.

────────────────────────────────────────────────────────────────────────────
FUENTES (única fuente de verdad del contenido — no se agregó nada que no
estuviera ahí)
────────────────────────────────────────────────────────────────────────────
1. D:\\GitHub\\brain-agentic\\vault\\projects\\automation\\CC002-estimastruct\\
   output\\2026-08-01_revit_draw_from_db_pipeline.md
   (copia canónica; histórico en
   D:\\GitHub\\brain-agentic\\vault\\logs\\automation\\CC002-estimastruct\\
   2026-08-01_revit_draw_from_db_pipeline.md)
   — describe el pipeline real ejecutado ese día: Fase 1 (7 pasos, template
   vacío) y Fase 2 / "Parte 2" (8 pasos, loop de verificación end-to-end).
2. Skill de Claude Code `estimastruct-revit-flow`
   (C:\\Users\\consu\\.claude\\skills\\estimastruct-revit-flow\\SKILL.md)
   — da el TONO esperado (lenguaje natural hacia el usuario, nunca "ejecutando
   python de X") y ya documenta el mismo flujo de punta a punta con foco en
   cara-al-cliente. Este módulo es su contraparte técnica-interna: mismo
   procedimiento, más detalle de script/línea/gotcha para que el AI Tooling
   Layer (o un ingeniero) pueda verificarlo contra el repo.

────────────────────────────────────────────────────────────────────────────
ANONIMIZACIÓN — decisión explícita, no inventada
────────────────────────────────────────────────────────────────────────────
La fuente #1 usa un proyecto Revit real de referencia. Esa doc lo marca
expresamente como PII ya excluido del pipeline RAG del SaaS EstimaStruct
(goal-20144, 2026-08-01) y advierte "no debe copiarse al pipeline rag.sqlite/
SaaS sin re-depurar nombres de cliente". Como este archivo vive en
`backend/cag/` — destinado a alimentar al AI Tooling Layer cloud (ADR-007), no
al vault interno — se omite el nombre del proyecto aquí también, por la misma
razón. Se refiere genéricamente a "proyecto de referencia real".

────────────────────────────────────────────────────────────────────────────
QUÉ HACE ESTE MÓDULO Y QUÉ NO
────────────────────────────────────────────────────────────────────────────
`procedimiento_revit_draw_from_db()` devuelve un dict read-only con el
procedimiento completo (fases, pasos, gotchas, semántica de color, tools MCP
disponibles vs. gap, y los TODOs pendientes de la sesión que lo generó). NO
ejecuta nada, NO importa `execute_revit_code` ni ningún script de
`scripts_runner/`, NO toca Postgres ni Revit. Es documentación estructurada,
para que el AI Tooling Layer la lea y siga el mismo procedimiento en vez de
adivinarlo desde el código crudo.

TODO (decisión pendiente del Director, no resuelta en la fuente): este
archivo hoy NO está wireado a ningún router/endpoint — a diferencia de los
`*_memoria.py` de `backend/services/`, que cuelgan de `GET/POST /auditoria/...`.
No hay todavía un mecanismo definido de cómo el AI Tooling Layer (ADR-007)
va a cargar el contenido de `backend/cag/` en tiempo de ejecución (¿lectura
directa de archivo al armar el system prompt? ¿un endpoint `/cag/...` nuevo,
análogo a `/auditoria/resumen`? ¿ingestión al RAG interno?). Ese diseño no
estaba definido en ninguna de las dos fuentes leídas — se deja como TODO
explícito en vez de inventarlo.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Metadata del procedimiento
# ─────────────────────────────────────────────────────────────────────────────
META = {
    "id": "revit_draw_from_db",
    "titulo": "Revit vacío -> dibujar desde el catálogo CSI -> presupuesto auditado",
    "objetivo": (
        "Reemplazar 'repartir un .rvt de EstimaStruct pre-armado' por "
        "'EstimaStruct genera los elementos desde su propia base de datos'. "
        "El resultado es un template Revit vacío con las familias y los "
        "ensambles de capas (muro/losa/techo/cielo falso) que el catálogo CSI "
        "de un proyecto necesita, más el ciclo posterior de exportar, "
        "auditar, colorear y entregar el presupuesto en PDF."
    ),
    "adr": "ADR-007/008/009 (CASE-SAAS-001) — AI Tooling Layer, CAG en backend/cag/",
    "estado_general": (
        "Ejecutado UNA vez de punta a punta contra un proyecto de referencia real "
        "el 2026-08-01. Fase 1 (pasos 1-7) corrió con 3 fallos puntuales sin "
        "diagnosticar. Fase 2 (pasos 8-15) corrió completa y confirmó el ciclo "
        "schedules -> import -> audit -> colores -> PDF ya en producción."
    ),
    "corte_fase": (
        "Entre el paso 7 (Fase 1) y el paso 8 (Fase 2) el corte es 100% manual: "
        "el usuario dibuja en Revit — coloca paredes con los tipos ya creados y "
        "familias con las cargadas — usando el mapa que se le entregó en el "
        "paso 7. Nada de eso se automatiza ni se automatizará vía "
        "`execute_revit_code` (sería editar geometría de diseño por script, no "
        "es el rol de este pipeline)."
    ),
    "gap_mcp_publico": (
        "ADR-010: el MCP público (`estimastruct-mcp`, cara al cliente/LLM cloud) "
        "hoy es SOLO lectura + cálculo dry-run. Fase 1 completa y la escritura "
        "de Fase 2 (import de cantidades, auditoría con push de color) corren "
        "hoy contra `revit-mcp-stdio` y Postgres con acceso directo del equipo "
        "técnico — no hay auth/multi-tenant todavía para exponerlo a un "
        "asistente cloud hablando con un cliente cualquiera."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# FASE 1 — template vacío con familias y ensambles listos (7 pasos)
# ─────────────────────────────────────────────────────────────────────────────
def _paso_proc(fase, n, titulo, que_hace_narrado, script_o_tool, estado,
               output, referencia, gotchas=None):
    """Un paso de PROCEDIMIENTO (no de fórmula). Análogo funcional al `_paso()`
    de los `*_memoria.py` de cálculo, pero para orquestación: en vez de
    {simbolo, formula, sustitucion, latex} describe {script_o_tool, estado,
    output, referencia}."""
    return {
        "fase": fase, "n": n, "titulo": titulo,
        "que_hace_narrado": que_hace_narrado,
        "script_o_tool": script_o_tool,
        "estado": estado,  # "canon" | "ad_hoc_pendiente_ok_director" | "bloqueado" | "no_corrido"
        "output": output,
        "referencia": referencia,
        "gotchas": gotchas or [],
    }


FASE_1_PASOS = [
    _paso_proc(
        1, 1, "Entender qué necesita este proyecto",
        "Preguntarle al usuario qué tipo de obra es (casa, apartamento, "
        "comercial) y buscar en el catálogo CSI qué partidas aplican — eso "
        "define QUÉ familias y ensambles hacen falta.",
        "tool MCP `estima_csi_search` (busca partidas por texto/CSI en el catálogo)",
        "canon",
        "Lista de partidas CSI aplicables al tipo de proyecto.",
        "SOP fuente, Fase 1 paso 1 / skill estimastruct-revit-flow",
    ),
    _paso_proc(
        1, 2, "Sacar la 'receta' de un proyecto de referencia",
        "Si hay un modelo Revit real similar ya modelado, se extrae su "
        "metadata completa (geometría de paredes, capas, materiales, "
        "keynotes) — es la fuente de la que se arma la receta genérica.",
        "backend/scripts_runner/revit_full_dump_snippet.py, corrido vía "
        "execute_revit_code sobre el pipe revit-mcp-stdio (Named Pipe, NO el "
        "bridge legacy :48884)",
        "canon",
        "project_full_dump.json — corrida real: 2344 instancias, 719 "
        "materiales, 101 compound_elements.",
        "Pipeline ejecutado, tabla paso 1",
        ["execute_revit_code ya envuelve el código en su propia Transaction "
         "— no anidar una propia."],
    ),
    _paso_proc(
        1, 3, "Separar lo genérico de lo específico del proyecto",
        "De la receta se separa (a) paredes/pisos/techos con sus capas de "
        "material — 100% reconstruible por código, sin depender de ningún "
        "archivo externo — de (b) familias sueltas (puertas, ventanas, "
        "sanitarios, luminarias) que sí necesitan un archivo .rfa real.",
        "backend/scripts_runner/build_generic_element_schema.py — NUEVO el "
        "2026-08-01, con OK explícito del Director. v3, produce `assemblies` / "
        "`tipos_sistema` / `elementos_puntuales` / `familias_no_creables` "
        "desde un project_full_dump.json.",
        "canon",
        "generic_element_schema.json — corrida real: 58 assemblies, 243 "
        "elementos puntuales, 88->77 familias reales tras corregir clasificación.",
        "Pipeline ejecutado, tabla paso 2 + sección 'Scripts canónicos tocados/creados hoy'",
    ),
    _paso_proc(
        1, 4, "Confirmar qué familias ya existen",
        "Se cruza la lista de familias necesarias contra la biblioteca real "
        "(la del usuario/empresa). Le dice al usuario: 'de las 77 familias "
        "que necesitás, 58 ya las tenemos, faltan 19 — acá está la lista.'",
        "Ad-hoc (no persistido como script) — cruce contra "
        "D:\\OneDrive\\RVT\\RVT\\2. My Families + librería Autodesk "
        "(C:\\ProgramData\\Autodesk\\RVT 2027\\Libraries\\English). Sin tool "
        "MCP dedicada todavía.",
        "ad_hoc_pendiente_ok_director",
        "familias_cross_check.json — corrida real: 58/77 encontradas.",
        "Pipeline ejecutado, tabla paso 3 + nota 'Pendiente de decisión'",
    ),
    _paso_proc(
        1, 5, "Armar el template vacío",
        "Se crea un archivo Revit nuevo (basado en un template estándar) y se "
        "cargan ahí todas las familias que sí se encontraron.",
        "Ad-hoc vía execute_revit_code: NewProjectDocument + LoadFamily (con "
        "IFamilyLoadOptions para que no aparezcan diálogos que traben el "
        "proceso). Candidato a persistir como script canon si se repite.",
        "ad_hoc_pendiente_ok_director",
        "estimastruct_blank_template.rvt — 74 familias cargadas (el template "
        "base ya trae algunas).",
        "Pipeline ejecutado, tabla paso 4",
    ),
    _paso_proc(
        1, 6, "Construir las paredes, pisos y techos reales",
        "Cada ensamble de la receta (ej. 'Steel Framing con Plycem, 100mm, "
        "código SF-01') se recrea en el template como un tipo de pared/piso/"
        "techo real, con sus capas exactas y el color de cada material — sin "
        "copiar ni un elemento del proyecto original.",
        "Ad-hoc vía execute_revit_code: WallType.Duplicate() + "
        "CompoundStructure.SetLayers() por cada assembly.",
        "ad_hoc_pendiente_ok_director",
        "55/58 assemblies creados con CSI+marca seteados. 3 fallaron: "
        "'CompoundStructure not valid' (2x un tipo de bloque+cerámica de baño, "
        "1x un tipo 'ENC-01').",
        "Pipeline ejecutado, tabla paso 5",
    ),
    _paso_proc(
        1, 7, "Entregar el mapa al usuario (CORTE de fase)",
        "Termina lo automático. Se entrega al usuario: (1) el archivo .rvt "
        "con todo cargado, (2) una lista clara de qué puerta va con qué "
        "familia, qué ventana con cuál otra (los elementos_puntuales con su "
        "CSI y marca). El usuario dibuja a mano desde acá: coloca paredes con "
        "los tipos ya creados, coloca puertas/ventanas con las familias ya "
        "cargadas, siguiendo la lista.",
        "N/A — entrega de artefactos, no ejecución.",
        "canon",
        ".rvt + checklist de elementos_puntuales entregados.",
        "skill estimastruct-revit-flow, Paso 7",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 — del modelo dibujado al presupuesto auditado (8 pasos,
# numerados 8-15 para continuar la numeración global de la Fase 1)
# ─────────────────────────────────────────────────────────────────────────────
FASE_2_PASOS = [
    _paso_proc(
        2, 8, "Levantar EstimaStruct",
        "Arranca cuando el usuario dice 'ya terminé de dibujar' (o "
        "'actualicé el modelo'). Se levanta el sistema para que pueda recibir "
        "los datos del modelo.",
        "START_POSTGRES_UNICA.ps1 (único entry point válido)",
        "canon",
        "backend :8002 + frontend :5000 arriba.",
        "Parte 2, tabla paso 1",
    ),
    _paso_proc(
        2, 9, "Exportar schedules desde Revit",
        "Se extraen del Revit del usuario las tablas de cantidades (cuántos "
        "m² de pared, cuántas puertas, cuántos metros de tubería) organizadas "
        "por CSI.",
        "El usuario clickea el botón real en el ribbon: EstimBot.tab -> "
        "Export.panel -> 'Exportar Schedules' (EstimBot.extension, activo, "
        "confirmado 2026-08-01). Ya incluye integración HTTP directa con el "
        "backend :8002 para importar el CSV sin salir de Revit. No hace "
        "falta correrlo por execute_revit_code.",
        "canon",
        "23 schedules exportados en la corrida real (2 sin columna keynote, "
        "normal, no llevan CSI).",
        "Parte 2, tabla paso 2",
        ["`PYR_S5_exportar_schedules.py` en `pyrevit/_legacy/scripts_sin_wiring/` "
         "es copia VIEJA superada — el botón real está en `EstimBot.extension` "
         "-> `EstimBot.tab\\Export.panel\\Exportar Schedules.pushbutton\\script.py` "
         "(386 líneas)."],
    ),
    _paso_proc(
        2, 10, "Meter esas cantidades al presupuesto",
        "Las cantidades que salieron de Revit se cargan a las partidas del "
        "presupuesto — cada partida sabe 'cuánto hay que comprar/hacer' de "
        "verdad, no un estimado.",
        "POST /revit-mcp/obras/{pid}/import-quantities (equivalente conceptual "
        "a `import_quantities`; hoy expuesto como endpoint, candidato a tool "
        "MCP pública directa)",
        "canon",
        "48 partidas actualizadas, 0 keynotes huérfanos en la corrida real.",
        "Parte 2, tabla paso 3",
    ),
    _paso_proc(
        2, 11, "Verificar revit_q en Postgres",
        "Chequeo de que la cantidad importada llegó bien a la columna "
        "`revit_q` de la partida.",
        "Verificación directa en Postgres (columna revit_q vs. cantidad)",
        "canon",
        "Confirmado: cantidad == revit_q en muestra de 15 partidas.",
        "Parte 2, tabla paso 4",
    ),
    _paso_proc(
        2, 12, "Revisar que todo esté bien identificado (auditoría CSI)",
        "Se compara cada elemento del modelo contra el catálogo de "
        "EstimaStruct. El resultado se explica al usuario en semáforo: verde "
        "= coincide con el catálogo, rojo = conflicto/mismatch, rosa = "
        "todavía no se dibujó/asignó.",
        "backend/scripts_runner/audit_keynotes.py sobre un "
        "revit_dump_snippet.py fresco (tool MCP `estima_csi_search` para "
        "comparar contra catálogo desde el AI Tooling Layer)",
        "canon",
        "779 GREEN / 170 RED de 949 filas en la corrida real.",
        "Parte 2, tabla paso 5",
    ),
    _paso_proc(
        2, 13, "Push de colores verde/rojo/rosa",
        "Se pinta cada elemento en el catálogo/Postgres según el resultado "
        "de la auditoría, para que el semáforo sea visible en la UI.",
        "backend/scripts_runner/sync_audit_colors.py",
        "canon",
        "328 partidas -> 187 verde, 0 rojo, 141 rosa en la corrida real. "
        "Semántica de color_tipo REDEFINIDA el 2026-08-01 (ver sección "
        "SEMANTICA_COLOR más abajo).",
        "Parte 2, tabla paso 6 + sección 'Semántica de color_tipo corregida'",
        ["`uvicorn --reload` mata el backend silencioso al editar scripts "
         "bajo backend/ mientras corre — relanzar con "
         "START_POSTGRES_UNICA.ps1 si pasa.",
         "No se hizo backup de fichas_v1.2*.json antes de correr esta vez "
         "(el propio script lo pide) — 8 fichas que antes eran 'manual "
         "preservado' se reclasificaron por el cambio de vocabulario de "
         "'rosa'; si tenían un rosa manual por otra razón, se perdió sin "
         "respaldo. Precedente igual en 2026-07-07."],
    ),
    _paso_proc(
        2, 14, "Export PDF cliente",
        "Se calcula el presupuesto final con las cantidades reales y se "
        "exporta el PDF para el cliente del usuario.",
        "GET /presupuestos/{pid}/export-pdf (tools MCP `estima_calcular`, "
        "`estima_get_presupuesto`, `estima_export_pdf`)",
        "canon",
        "PDF de 106KB, L.1,432,105.57 de costo directo en la corrida real.",
        "Parte 2, tabla paso 7",
    ),
    _paso_proc(
        2, 15, "Comparar cantidades PDF vs DB",
        "Verificación final: que el PDF entregado refleje lo que hay en la "
        "base de datos.",
        "Revisión visual — entregado al Director para revisión.",
        "canon",
        "Entregado al Director para revisión visual (no automatizado).",
        "Parte 2, tabla paso 8",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Semántica de color_tipo (redefinida 2026-08-01, Director) — se copia textual,
# no se reinterpreta.
# ─────────────────────────────────────────────────────────────────────────────
SEMANTICA_COLOR = {
    "verde": "asignado en Revit a una familia, coincide con catálogo (GREEN en audit).",
    "rojo": ("NUEVO valor 2026-08-01 — CSI aparece en Revit pero en "
             "conflicto/mismatch (0 GREEN para ese CSI). No requiere "
             "migración: color_tipo es Column(Text) plano en models.py, sin "
             "CheckConstraint real en Postgres."),
    "rosa": ("no asignado en Revit — pasa a ser vocabulario propio del audit "
             "(antes se preservaba como 'manual'; ver riesgo de pérdida sin "
             "backup arriba, paso 13)."),
    "amarillo": "manual (labor/otro) — el audit nunca lo toca. Sin cambio.",
    "azul": "manual/otra categorización del Director — el audit nunca lo toca. Sin cambio.",
    "scripts_actualizados": [
        "backend/scripts_runner/sync_audit_colors.py (lógica completa reescrita)",
        "backend/models.py:112 (comentario + default 'blanco' -> 'rosa')",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Gotchas transversales de revit-mcp-stdio / execute_revit_code, copiados
# textual de la fuente (no reinterpretados) porque aplican a TODA la Fase 1
# y a partes de la Fase 2.
# ─────────────────────────────────────────────────────────────────────────────
GOTCHAS_TRANSVERSALES = [
    "execute_revit_code ya envuelve el código en su propia Transaction — "
    "abrir una Transaction propia adentro tira 'Starting a new transaction "
    "is not permitted'. Nunca anidar.",
    "doc.Save() no se puede llamar dentro de execute_revit_code "
    "('Operation is not permitted when there is any open transaction phase "
    "started by API client') — usar la tool dedicada save_document aparte.",
    "IronPython 2.7 del lado del pipe rompe con tildes/ñ en literales de "
    "string transmitidos (UnicodeDecodeError) — transliterar a ASCII "
    "(unicodedata.normalize('NFKD', s).encode('ascii','ignore')) antes de "
    "embeber en el CODE que viaja por el pipe. CSI y códigos de marca ya son "
    "ASCII por diseño, no se ven afectados.",
    "ExternalEvent se cuelga con api_timeout si hay algo seleccionado en "
    "Revit (no es bug del pipe, confirmado en vivo) — antes de cualquier "
    "execute_revit_code pesado, confirmar que no hay selección activa.",
    "get_revit_status/ping/list_tools no requieren ExternalEvent "
    "(requires_api: False en tool_manifest.py) — sirven para diagnosticar "
    "sin competir por el mismo turno que execute_revit_code/reload_pyrevit "
    "(requires_api: True).",
    "Reload de pyRevit (Add-Ins -> pyRevit -> Reload) sube el conteo de "
    "tools de 52 a 54 — señal de que sí recargó código nuevo del lado de la "
    "extensión.",
    "uvicorn --reload mata el backend silencioso al editar scripts bajo "
    "backend/ mientras corre (confirma gotcha_uvicorn_reload_asyncio_subprocess) "
    "— relanzar con START_POSTGRES_UNICA.ps1.",
]


# ─────────────────────────────────────────────────────────────────────────────
# Tools MCP disponibles HOY para el AI Tooling Layer (cara al cliente,
# `estimastruct-mcp`) vs. el gap real (ADR-010) — copiado de la skill
# estimastruct-revit-flow, que ya lo documenta con esta misma honestidad.
# ─────────────────────────────────────────────────────────────────────────────
TOOLS_MCP_DISPONIBLES = {
    "estima_list_presupuestos": "Listar los proyectos del usuario",
    "estima_create_presupuesto": "Arrancar un presupuesto nuevo desde template",
    "estima_get_presupuesto": "Traer el detalle completo (capítulos, partidas)",
    "estima_get_partidas": "Traer las partidas de un capítulo",
    "estima_get_materiales": "Consultar el catálogo de materiales/precios",
    "estima_csi_search": "Buscar partidas por CSI o texto",
    "estima_calcular": "Recalcular el presupuesto",
    "estima_get_cronograma": "Traer el cronograma de obra",
    "estima_import_revit": "Importar datos desde Revit (cantidades)",
    "estima_export_pdf": "Exportar el PDF final",
}

GAP_MCP_PUBLICO_ADR010 = (
    "El MCP público hoy es SOLO lectura + cálculo dry-run. Todo lo de Fase 1 "
    "(crear template, cargar familias, dibujar assemblies) y parte de Fase 2 "
    "(auditoría con escritura, colores) hoy lo ejecuta el equipo técnico "
    "directo contra revit-mcp-stdio y Postgres — no hay auth/multi-tenant "
    "todavía para exponerlo a un asistente cloud hablando con un cliente "
    "cualquiera. Respuesta honesta si el usuario pregunta por qué no lo hace "
    "el chat solo: 'esa parte todavía la hacemos con acceso directo al "
    "proyecto, se está trabajando para que el asistente lo haga solo.'"
)


# ─────────────────────────────────────────────────────────────────────────────
# TODOs explícitos — huecos reales de la fuente, NO inventados/resueltos aquí.
# ─────────────────────────────────────────────────────────────────────────────
TODOS_PENDIENTES = [
    "Diagnosticar los 3 assemblies que fallaron con 'CompoundStructure not "
    "valid' en el paso 6 (2x un tipo de bloque+cerámica de baño, 1x 'ENC-01'). "
    "No resuelto en la fuente.",
    "Confirmar corrida limpia de revit_marks_master.py sobre el template "
    "nuevo (paso 6 de Fase 1, distinto del paso 13 de Fase 2) — quedó "
    "bloqueada por selección activa en Revit el 2026-08-01, sin confirmar "
    "reintento.",
    "Correr audit_keynotes.py sobre el template NUEVO de Fase 1 para cerrar "
    "ese loop (paso 7 original de Fase 1) — no corrido el 2026-08-01, "
    "próximo paso natural.",
    "Decidir si los scripts ad-hoc de los pasos 3, 4, 5 y 6 de Fase 1 "
    "(cross-check de familias, creación de template, recreación de "
    "assemblies) se promueven a backend/scripts_runner/. Requiere OK "
    "explícito del Director antes de crear el archivo (regla dura) — no "
    "decidido en la fuente.",
    "goal-20149 (reparar/confirmar el wiring del botón real de export "
    "schedules, sacarlo de _legacy/scripts_sin_wiring/) segu\u00eda abierto "
    "en Postgres a la fecha de la sesión que generó este contenido.",
    "Mecanismo de carga en runtime de este archivo hacia el AI Tooling Layer "
    "(ver docstring del módulo) — no definido en ninguna fuente leída, "
    "queda como decisión de arquitectura pendiente del Director.",
]


def procedimiento_revit_draw_from_db(meta_extra: dict | None = None) -> dict:
    """Devuelve el procedimiento completo (Fase 1 + Fase 2) como dict
    estructurado, para que el AI Tooling Layer (o cualquier lector humano) lo
    siga sin adivinar desde el código crudo. Solo lectura — no ejecuta nada.
    """
    meta = dict(META)
    if meta_extra:
        meta.update(meta_extra)
    return {
        "meta": meta,
        "pasos": FASE_1_PASOS + FASE_2_PASOS,
        "semantica_color": SEMANTICA_COLOR,
        "gotchas_transversales": GOTCHAS_TRANSVERSALES,
        "tools_mcp_disponibles": TOOLS_MCP_DISPONIBLES,
        "gap_mcp_publico_adr010": GAP_MCP_PUBLICO_ADR010,
        "todos_pendientes": TODOS_PENDIENTES,
        "fuentes": [
            "D:\\GitHub\\brain-agentic\\vault\\projects\\automation\\CC002-estimastruct\\"
            "output\\2026-08-01_revit_draw_from_db_pipeline.md",
            "C:\\Users\\consu\\.claude\\skills\\estimastruct-revit-flow\\SKILL.md",
        ],
    }
