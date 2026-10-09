# Auditoría front / Gantt / export de materiales / puente Supabase (2026-10-09)

Alcance: lo que hay en este repo. El front del Portal y el esquema Supabase NO están aquí.
Nada de esto se probó en navegador ni contra Supabase real (sólo compilación + prueba en SQLite en memoria).

## 1. Front: consistencia de propiedades y reactividad
- Sólo `index.html` (front page) usa el stack compartido: `css/style.css`, `core.js`, `app.js`, i18n `data-es/data-en` (+ `-placeholder`, `-title`), versionado `?v={{ asset_version }}`.
- `features.html`, `karla_budget.html`, `matrices.html`, `matriz_detail.html`, `monitoring.html`, `viewer.html`: CSS inline propio, sin `style.css`, sin i18n, sin `core.js` (0 `data-es`). Cada uno redefine sus colores (`:root` propio) → no heredan tema ni idioma de la front page.
- Estado: `state` global en `app.js`; el modal Gantt guarda su propio estado (`_ganttData/_ganttZoom/_ganttFiltro`) y se vuelve a pintar tras cada POST (mover/personal), sin eventos compartidos.
- Pendiente recomendado (no hecho): extraer tokens de tema + i18n a un `shared.css/shared.js` e incluirlo en las 6 plantillas.

## 2. Gantt (modal de cronograma)
- Movimiento: filas arrastrables (`dragstart/dragover/drop`) → `POST /cronograma/mover` → recalcula cadena. Ya existía; sin prueba en navegador.
- Redimensionado: antes sólo la columna izquierda (`#gantt-resizer`). Ahora el modal entero es redimensionable (`resize: both`, mín. 720×420, máx. 99vw×98vh).
- **Nuevo** vista "Materiales / semana": `GET /presupuestos/{pid}/cronograma/materiales`. Cantidad de cada MATERIAL = rendimiento × cantidad de la partida, repartida uniformemente en los días L-S de la actividad y agrupada por semana (S1 = semana del inicio de obra, igual que la grilla del XLSX). Se refresca sola cuando cambian orden o cuadrillas (firma del cronograma). El "ajuste" de materiales por semana se hace moviendo actividades o cambiando cuadrillas Esp/Ay; no hay edición manual de celdas.
- El motor de duraciones lee el catálogo **v1.2** (`CATALOGO_V12_PATH`), no el v1.3 canónico (ADR-018). Pendiente de decisión.

## 3. Export Excel
- **Bug corregido** en `/export-insumos`, hoja `global`, sección "Cantidad de insumos": la columna calculaba `rendimiento_promedio × Total Agrupado` (rendimiento × *costo*), no una cantidad. Ahora es Σ(rendimiento × cantidad de la partida), redondeada hacia arriba, y es la misma fórmula que usa la hoja de materiales por semana.
- `/export-cronograma` ahora incluye la hoja `materiales_semana` (Clave, Descripción, Unidad, Total obra, S1..Sn). Total de la fila = suma de semanas.

## 4. Supabase: Gantt back vs front
Hallazgos en `portal_publish.py`:
1. `sync_precios_supabase` **no tenía `@router.post`**: el botón "Sync precios" devolvía 404. Corregido (`POST /presupuestos/{pid}/sync-precios-supabase`).
2. Publicar llamaba al motor **sin orden manual** → el portal divergía del Gantt si el usuario reordenaba. Ahora usa `routers/cronograma._calcular` (misma ruta que el front: overrides + orden manual).
3. El Gantt local incluye partidas con `cantidad > 0`; `partida_valor` sólo `total > 0`. Las actividades sin fila en `partida_valor` no se publican al cronograma del portal (diferencia real de conjuntos).
4. Republicar borra `cronograma` y `partida_valor` (reset de avance/activa).

### Propuesta de puente (a decidir)
- Contrato único: el JSON de `GET /presupuestos/{pid}/cronograma` (+ `/materiales`) es la fuente; el portal consume lo mismo, no recalcula.
- Publicar = upsert (no delete) por `(obra_id, estimastruct_partida_id)` para conservar `avance_pct`/`activa`; incluir `fecha_fin`, `orden_manual` y una tabla `cronograma_material(obra_id, partida_id|clave, semana, cantidad)`. Requiere migración Supabase (no verificable desde aquí).
- Reactividad: Supabase Realtime en `cronograma` para que el front del portal refleje cambios; EstimaStruct publica tras cada `mover/personal` (debounce) o con botón.
- Igualar el conjunto de actividades (punto 3) con un único filtro.
