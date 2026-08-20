---
status: draft
domain: estimastruct
note_type: tool_spec
version: "0.1"
created: "2026-08-03"
depends_on: [ADR-010, F0, F1, F3, F7]
goal: goal-20151
tags: [estimastruct, pdf-cad, ocr, takeoff, csi, mcp, roadmap]
---

# F7 — Superficie de tools PDF→CAD→estimación (MVP vectorial)

> **Origen:** goal-20151. ADR-010 y `roadmap_case_saas_001_scope_v2.md` §F7 ya
> definieron el **pipeline** y el **riesgo**. Lo que faltaba y define este doc es
> el **contrato concreto de tools** que un LLM cloud invoca para llevar un plano
> PDF vectorial hasta `partida.revit_q`. Estado: borrador, requiere OK del Director
> antes de construir (F7 depende de F0).

## 0. Constraints heredados (no negociables)

1. **MVP = PDF vectorial únicamente.** Escaneado/raster es fase aparte con su
   propio go/no-go (ADR-010, §F7). Ninguna tool de este set asume visión sobre
   raster como camino principal; la visión es *fallback* de desambiguación, no
   el extractor.
2. **El MCP público es read-only + cálculo dry-run** (ADR-010 punto 1). Ninguna
   de estas tools escribe `revit_q` de forma autónoma. La escritura vive detrás
   del gate de revisión humana (§3, tool 6) y **no se expone como tool pública**
   hasta que exista auth/multi-tenant (F1).
3. **Revisión humana obligatoria + marca visual** antes de aceptar cantidades
   (ADR-010 §trade-offs, §F7 entregable "no negociable"). Se reusa `color_tipo`
   en `partida` para marcar cantidades de origen PDF distinto de Revit.
4. **Reusa el flujo de takeoff existente.** El destino final es `partida.revit_q`
   + `factor_e` + `factor_f`. No se crea flujo nuevo de presupuesto.
5. **Deps ausentes hoy** (`backend/requirements.txt` verificado 2026-08-03: no
   tiene PyMuPDF/`pdfplumber`/`ezdxf`/`shapely`/`opencv`). F7 arranca declarando
   estas deps — no son "cerrar un gap", son features desde cero.

## 1. Modelo de datos intermedio (contrato entre tools)

Todas las tools de extracción hablan un objeto común, **no** escriben BD:

```jsonc
// GeometryDoc  (salida de la extracción, insumo de clasificación/cuantificación)
{
  "doc_id": "uuid-de-sesion",           // efímero, vive en cache/tmp, no en BD
  "source_pdf": "sha256-del-archivo",
  "page": 3,
  "units": "mm",                         // unidad interna tras aplicar escala
  "scale": { "value": 50.0, "basis": "titleblock|known_dim|declared", "confidence": 0.0 },
  "layers": ["A-WALL", "S-COLS", "..."],
  "entities": [
    { "eid": "e001", "kind": "raw_path|text|dim",
      "layer": "A-WALL", "geom": { "type": "polyline", "pts_px": [[x,y],...] },
      "text": null, "bbox_px": [x0,y0,x1,y1] }
  ]
}
```

`kind` semántico (`wall`/`slab`/`column`/`door`/`window`) **no** se asigna en la
extracción — lo asigna la tool de clasificación (§2, tool 3). Separar extracción
cruda de interpretación es lo que permite auditar dónde falla la precisión.

## 2. Tools — extracción y cómputo (read-only, aptas para MCP público v1)

| # | Tool | Input | Output | Side-effects | Backend |
|---|------|-------|--------|--------------|---------|
| 0 | `pdf_list_sheets` | `pdf_ref` | láminas: `{page, size, is_vector, titleblock_found}` + veredicto vectorial/raster por página | ninguno | PyMuPDF `doc[p].get_drawings()` cuenta vs `get_images()` |
| 1 | `pdf_extract_geometry` | `pdf_ref`, `page` | `GeometryDoc` con paths+capas+texto en px | ninguno (cache tmp) | PyMuPDF `get_drawings()` (paths vectoriales + color/capa), `get_text("dict")` (texto+bbox) |
| 2 | `pdf_detect_scale` | `GeometryDoc` \| `{page, hint}` | `scale{value,basis,confidence}` | ninguno | heurística: cota conocida (texto dim vs longitud px) → marco de título → escala declarada por usuario |
| 3 | `pdf_classify_entities` | `GeometryDoc`, `scale` | entidades con `kind` + `confidence`; ambiguas marcadas `needs_review` | ninguno | heurísticas (capa/grosor/cierre de polígono) primero; **LLM visión de F3 solo para las ambiguas** (recorte de página → clasificar) |
| 4 | `pdf_quantify` | entidades clasificadas, `scale` | cantidades por tipo: muro m²/ml, losa m², columna u, puerta/ventana u | ninguno | geometría 2D: longitud×altura-supuesta, área de polígono (`shapely`), conteo |
| 5 | `csi_map_entities` | cantidades por tipo, `presupuesto_id` | propuesta: `[{eid, kind, cantidad, unidad, clave_csi, type_mark, match_status, confidence}]` | ninguno | **reusa** `GET /partidas/by-csi/{clave_csi}?presupuesto_id=` + `estima_csi_search`. Matching exacto→normalizado→prefijo (ya existe backend) |

Notas de diseño §2:
- Tools 0-5 son **puro cálculo, cero escritura** → califican para la superficie
  MCP pública v1 (read-only + dry-run) sin violar ADR-010. Son el equivalente
  PDF de lo que `estima_get_*`/`estima_csi_search` ya son para presupuestos.
- La escala (tool 2) es el punto de mayor varianza. `confidence` debe propagarse:
  escala dudosa envenena toda cantidad aguas abajo. Si `confidence < umbral`, la
  cantidad nace `needs_review` forzado, sin excepción.
- El "LLM de visión" de la tool 3 es el único consumo de tokens de visión y
  **solo** sobre recortes de entidades ambiguas — no sobre la página entera. Esto
  acota costo (ADR-010: "costo variable nuevo") y mantiene el MVP vectorial.

## 3. Tool de escritura — detrás del gate (NO pública, NO autónoma)

| # | Tool | Input | Output | Side-effects |
|---|------|-------|--------|--------------|
| 6 | `pdf_takeoff_stage` | propuesta de `csi_map_entities`, `presupuesto_id` | crea un **staging set** revisable (no toca `partida`) | escribe tabla de staging efímera / `color_tipo`=origen-PDF marcado |
| 7 | `pdf_takeoff_commit` | `staging_id`, decisiones humanas fila-por-fila | aplica `revit_q` **solo de las filas aceptadas** | **muta `partida.revit_q`** → reusa la ruta de `import_quantities.py` (`ceil`→factores→recalcular) |

- **Tool 7 es el único punto que muta dinero.** No sale sin: (a) UI de revisión
  humana (ADR-010 entregable "no negociable"), (b) auth/tenant (F1), (c) marca
  visual permanente de cantidades origen-PDF. Hasta entonces corre solo con
  acceso directo del equipo técnico, igual que hoy corre la escritura de Fase 2
  del pipeline Revit (ver `memoria_revit_draw_from_db.py` `gap_mcp_publico`).
- `pdf_takeoff_commit` **no inventa ruta nueva**: entra por el mismo camino que
  el CSV de Revit (`revit_q` bruto → `cantidad = ceil(revit_q)·factor_e·factor_f`).
  El origen cambia, el flujo de takeoff no.

## 4. Gate de precisión (bloqueante para producción)

`pdf_quantify` debe emitir, además de cantidades, una **métrica contra takeoff
manual** sobre planos reales de ConsuConstruct (ADR-010 §F7: "sin esto no se sabe
si sirve"). Tool auxiliar:

| # | Tool | Input | Output |
|---|------|-------|--------|
| 8 | `pdf_takeoff_score` | cantidades PDF, cantidades manuales de referencia | error por tipo (%) + veredicto vs umbral acordado con Director |

Si el error supera el umbral, la feature **se congela** — un takeoff automático
poco confiable es peor que ninguno (induce confianza falsa). Este es criterio
go/no-go, no un warning.

## 5. Resumen de superficie

- **8 tools cómputo (0-5, 8)** → read-only, candidatas a MCP público v1.
- **2 tools escritura (6-7)** → internas, gated, nunca autónomas, dependen de F1.
- **0 flujos de presupuesto nuevos** → todo desemboca en `revit_q` existente.
- **Deps a declarar en F7:** PyMuPDF (extracción+raster), `shapely` (áreas/
  polígonos), opcional `ezdxf` solo si se decide puente a DXF real (no requerido
  para el MVP: la geometría se cuantifica en memoria, no necesita salir a CAD).

## 6. Pendiente de decisión del Director

1. Umbral de precisión aceptable para el go/no-go (§4) — sin número, F7 no puede
   cerrar.
2. ¿DXF intermedio (`ezdxf`) sí/no? El pipeline no lo necesita; solo suma valor si
   el cliente quiere el CAD reconstruido como entregable aparte.
3. ¿Altura de muro para m²? El PDF de planta no la trae — ¿se toma de un default
   por nivel, del marco de título, o se pregunta al usuario por tipo de muro?
