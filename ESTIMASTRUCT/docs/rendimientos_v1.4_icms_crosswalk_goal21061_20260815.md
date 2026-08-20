# Rendimientos v1.4 — Crosswalk de clasificación ICMS ↔ catálogo EstimaStruct (goal-21061)

**Fecha:** 2026-08-15
**Rol:** estimastruct (Brain) — alias 'Hooke'
**Continuación directa de:** goal-19701 (`docs/analisis_icms_rendimientos_goal19701_20260802.md`)
**Fuentes ICMS verificadas:** `C:\Users\consu\.openclaw\workspace\artifacts\icms\ICMS_3rd_edition_final.pdf` (estándar RICS/ICMS Coalition, 3ª ed., nov-2021, 139 pp.) · `ICMS_explained_3rd_edition.pdf` (guía práctica RICS, ago-2022, 59 pp., Appendix 2 = códigos completos).

---

## 0. Hallazgo que condiciona todo el goal (verificado, no asumido)

El goal ordena "mapear los **rendimientos** correctos por actividad **usando los PDFs ICMS**". Se verificó el contenido literal de ambos PDFs antes de escribir una sola línea:

- Título del estándar: *"Global Consistency in **Presenting** Construction Life Cycle Costs and Carbon Emissions"*. ICMS es un marco de **clasificación/presentación** de costos (Project → Sub-project → Cost Category → Cost Group → Cost Sub-group → Element), no una base de productividad.
- Búsqueda de texto completo sobre **306,977 caracteres** de ambos PDFs (`man-hour`, `output rate`, `labour/labor constant`, `crew`, `productivity`, `hours per`, `person-hour`, `rendimiento`, `norm hour`): **0 coincidencias** de valores de rendimiento. La única aparición de "productivity" (1x) es en el contexto de *externalities* en life-cycle cost, no una tabla de rendimientos.

**Conclusión:** ICMS **no contiene ni un solo valor de rendimiento por actividad** (jornal/unidad, m·h/m², rendimiento de cuadrilla). Esto ya lo había documentado goal-19701 §1 ("cruce de dominios"); aquí queda confirmado con evidencia textual directa sobre los PDFs que el goal cita como fuente.

Por tanto "construir rendimientos_v1.4 **usando ICMS**" no puede significar *tomar valores de rendimiento de ICMS* (no existen). La única lectura técnicamente honesta y ejecutable es:

> **v1.4 = re-clasificar el catálogo de rendimientos actual de EstimaStruct contra la taxonomía de costos ICMS (categoría 2 "Construction costs"), extendiendo los 8 códigos indirectos de v1.3 a los grupos de costo directos.**

Los **valores** de rendimiento (`costo_mo`, `costo_ma`, `unitario_matriz` por partida) siguen siendo los de EstimaStruct — su fuente de verdad es el dato propio de la empresa (histórico de obra + norma nacional), no ICMS. Eso es exactamente lo que este crosswalk mapea: *dónde cae cada actividad en el árbol ICMS*, no *cuánto rinde*.

---

## 1. Qué ya existía (v1.3) y qué agrega v1.4

**v1.3 (goal-19701):** ancló solo la parte **indirecta** del árbol ICMS — 8 códigos de los grupos de costo 08 (Preliminaries), 09 (Risk allowances) y 10 (Taxes) de la categoría construcción, en `backend/calculo_financiero.py::CATALOGO_ICMS_REFERENCIA`. Esos son los indirectos de la cédula financiera auditable.

**v1.4 (este documento):** extiende la clasificación a los grupos de costo **directos** ICMS 2.01–2.07, 2.11–2.13, mapeándolos contra las 23 divisiones CSI/MasterFormat que EstimaStruct realmente usa como llave maestra por partida (`backend/csi_utils.py::_CHAPTER_BY_PREFIX` / `_CHAPTER_BY_KEYWORD`). Cierra el punto §6.5 de goal-19701 ("¿ampliar más allá de los 8 códigos indirectos al árbol completo?") — que ordenar el v1.4 responde afirmativamente.

---

## 2. Árbol ICMS de referencia — Categoría 2 "Construction costs" (Appendix 2, ICMS 3ª ed.)

Grupos de costo (nivel 3) de la categoría construcción, extraídos del PDF:

| Grupo ICMS | Cost group (nivel 3) | Naturaleza |
|---|---|---|
| 2.01 | Demolition, site preparation and formation | Directo |
| 2.02 | Substructure | Directo |
| 2.03 | Structure | Directo |
| 2.04 | Architectural works / Non-structural works | Directo |
| 2.05 | Services and equipment | Directo |
| 2.06 | Surface and underground drainage | Directo |
| 2.07 | External and ancillary works | Directo |
| 2.08 | Preliminaries / Constructors' site overheads | **Indirecto (v1.3)** |
| 2.09 | Risk allowances | **Indirecto (v1.3)** |
| 2.10 | Taxes and levies | **Indirecto (v1.3)** |
| 2.11 | Work and utilities off-site | Directo |
| 2.12 | Post-completion loose furniture, fittings, equipment | Directo |
| 2.13 | Construction/Renewal/Maintenance-related consultancy | Honorarios prof. |

(Los códigos `08.0xx`/`09.0xx`/`10.0xx` de `CATALOGO_ICMS_REFERENCIA` son el nivel 4 sub-group de los grupos 2.08/2.09/2.10.)

---

## 3. Crosswalk v1.4 — División CSI EstimaStruct → Grupo de costo ICMS

Mapeo por **actividad/capítulo** (nivel al que ICMS clasifica y al que EstimaStruct agrupa por CSI). Una división CSI puede repartirse en más de un grupo ICMS; se indica el grupo primario.

| CSI div | Capítulo EstimaStruct (MasterFormat) | Grupo(s) ICMS | Nota de mapeo |
|---|---|---|---|
| 01 | General Requirements | 2.08 | Preliminares → overheads de obra (ya en cédula indirecta 08.010) |
| 02 | Existing Conditions / Demolición | 2.01 | Demolición y preparación de sitio |
| 03 | Concrete | 2.02 + 2.03 | Cimentación (substructure) vs. marcos/losas sobre nivel (structure) — se separa por partida |
| 04 | Masonry | 2.04 | Mampostería = obra arquitectónica no estructural (salvo muro portante → 2.03) |
| 05 | Metals | 2.03 | Acero estructural / joist / deck → structure |
| 06 | Wood, Plastics & Composites | 2.03 / 2.04 | Estructural (2.03) vs. carpintería de acabado (2.04) |
| 07 | Thermal & Moisture Protection | 2.04 | Impermeabilización, cubiertas |
| 08 | Openings | 2.04 | Puertas, ventanas, vidrio |
| 09 | Finishes | 2.04 | Repello, pintura, pisos, cielo raso |
| 10 | Specialties | 2.04 | Señalización, accesorios |
| 11 | Equipment | 2.05 | Equipo fijo de obra |
| 12 | Furnishings | 2.12 | Mobiliario suelto post-terminación (2.12); empotrado → 2.04 |
| 21 | Fire Suppression | 2.05 | Servicios contra incendio |
| 22 | Plumbing | 2.05 + 2.06 | Plomería (2.05) + drenaje sanitario (2.06) |
| 23 | HVAC | 2.05 | Climatización |
| 25 | Integrated Automation | 2.05 | Automatización de edificio |
| 26 | Electrical | 2.05 | Instalación eléctrica e iluminación |
| 27 | Communications | 2.05 | Datos/telecom |
| 28 | Electronic Safety & Security | 2.05 | Seguridad electrónica |
| 31 | Earthwork | 2.01 + 2.02 | Movimiento de tierra: preparación de sitio (2.01) y excavación de cimentación (2.02) |
| 32 | Exterior Improvements | 2.07 | Obras exteriores y complementarias |
| 33 | Utilities | 2.06 + 2.11 | Servicios de sitio (2.06) y fuera de sitio (2.11) |

**No mapeado a partida directa (correcto que quede fuera del catálogo de rendimientos):**
- 2.09 Risk allowances y 2.10 Taxes → viven en la cédula indirecta (v1.3), no como rendimiento de actividad.
- 2.13 Consultoría/honorarios → no es partida de obra en EstimaStruct.

---

## 4. Ambigüedades reales del crosswalk (para revisión de ingeniería, no de negocio)

1. **CSI 03 Concrete se parte en 2.02 (substructure) vs 2.03 (structure)** — no es 1:1 por división; requiere decidir por partida si es cimentación o superestructura. La regla propuesta: `descripcion` contiene cimentación/zapata/pedestal/losa de fundación → 2.02; columna/viga/losa entrepiso/techo → 2.03.
2. **CSI 06 Wood** se parte igual (estructural 2.03 vs acabado 2.04).
3. **CSI 22 Plumbing** reparte agua/aparatos (2.05) vs drenaje (2.06).
4. **CSI 33 Utilities** reparte in-site (2.06) vs off-site (2.11).

Estas cuatro son las únicas divisiones que no caen limpio en un solo grupo ICMS; el resto es 1:1.

---

## 5. Lo que v1.4 NO hace — frontera de decisión del Director

Este documento es un **crosswalk de clasificación** (categoría 2, trabajo de repo, no toca datos de producción). Lo que sigue requiere OK explícito porque escribe en datos reales o es juicio de negocio — heredado de goal-19701 §6, sigue abierto:

1. **Poblar/ajustar los valores de rendimiento** (`costo_mo`/`costo_ma` por partida) en la BD viva `C:\EstimaStruct\data\estimacion.db` o en Postgres `estimastruct`. ICMS no da esos números; su fuente es el histórico de obra + norma nacional, y escribirlos es acción sobre producción → necesita OK.
2. **Cargar los % reales de indirectos** por obra en la cédula financiera (imprevistos 09.020, admin 08.010, seguros/fianzas 08.110, utilidad, escalamiento 09.030) — el paso que convierte el `sobrecosto` opaco en cédula demostrable (goal-19701 §6.3).
3. **Definir la fuente de verdad** del export v1.x (Postgres `estimastruct` vs SQLite `estimacion.db`) — ambigüedad abierta de goal-19701 §5.
4. **Persistir el crosswalk en código/BD** (p.ej. un `CATALOGO_ICMS_DIRECTOS` en `csi_utils.py` o una columna `categoria_icms` por partida) — es aditivo y de repo, pero conviene confirmar el diseño (columna por partida vs. tabla de mapeo CSI→ICMS) antes de tocar el esquema.

---

## 6. Veredicto

- **Verificar contenido ICMS:** hecho — 0 valores de rendimiento en 306K chars; ICMS clasifica, no rinde.
- **Mapear rendimientos por actividad contra el catálogo actual:** hecho como **crosswalk de clasificación** CSI↔ICMS (23 divisiones → grupos 2.01–2.13), la única lectura ejecutable de la orden.
- **Poblar valores de rendimiento / promover a producción:** **PENDIENTE — decisión del Director** (§5). No lo ejecuta el rol sin OK.
- **Claim honesto de v1.4:** *"catálogo de rendimientos EstimaStruct clasificado contra ICMS 3ª ed. (directos + indirectos)"* — NO *"rendimientos derivados de ICMS"* (imposible: ICMS no los tiene).
