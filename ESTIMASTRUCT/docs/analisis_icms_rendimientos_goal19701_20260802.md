# Análisis técnico auditable — ICMS en EstimaStruct (goal-19701)

**Fecha:** 2026-08-02
**Rol:** estimastruct (Brain)
**Estándar de referencia:** RICS International Cost Management Standard (ICMS), 3rd edition — Table B-1 / Table 2
**Alcance:** consolidar el trabajo ICMS ya existente, corregir el registro, y dejar preparada la aprobación del Director. **Este documento NO aprueba nada por sí solo** — la aprobación del "proven-effective cost budget" es decisión del Director (ver §6).

---

## 0. Corrección de registro (importante)

Una corrida previa de `estimastruct_worker` (2026-08-02 05:29) escaló al Director afirmando que *"ICMS NO existe en ningún knowledge base local"*. **Eso es incorrecto.** Esa corrida solo consultó `estima_rag_search` / `rag_search` (RAG semántico) y nunca revisó el código del repo EstimaStruct, que es donde vive el trabajo real.

Verificación 2026-08-02 (grep + lectura de código):
- El catálogo RICS ICMS 3rd ed. YA está codificado en `backend/calculo_financiero.py` (`CATALOGO_ICMS_REFERENCIA`, 8 códigos Group.SubGroup).
- El módulo financiero (cédula de indirectos auditable) YA fue construido y verificado el 2026-07-31 (`FinancieroItem` / `FinancieroCalculo`, `routers/financiero.py`, fusión en `frontend/js/auditoria-formulas.js`).
- El escaneo v1.3 (1145 partidas vs RICS ICMS 3rd ed.) YA fue hecho — es la justificación documentada del módulo financiero.

Conclusión: el goal está **mucho más avanzado** de lo que decía esa escalación. El bloqueo A de la corrida previa ("sin el libro ICMS no puedo mapear") queda **resuelto en la práctica** para el alcance relevante (indirectos de obra).

---

## 1. Aclaración conceptual: qué clasifica ICMS (y qué NO)

ICMS es un estándar de **presentación/clasificación de costos** (capital + ciclo de vida + carbono), organizado en niveles Project → Sub-project → Cost Category → Cost Group → Cost Sub-group → Element.

ICMS **no define rendimientos de mano de obra** (jor/unidad). Por eso el título del goal ("implementar ICMS en rendimientos") es, estrictamente, un cruce de dominios. La lectura correcta y la que se ejecutó:

- Los **rendimientos** de EstimaStruct viven por partida como `costo_mo` / `costo_ma` / `unitario_matriz` (contrato `pricing.py`: `costo_base = costo_mo + costo_ma + unitario_matriz`). Estos son costos **directos** y ya tienen su propia estructura auditable (CSI como llave maestra).
- El aporte real de ICMS a EstimaStruct es sobre los **costos indirectos** (preliminares, riesgo/contingencia, seguros/fianzas, impuestos), que es exactamente donde el escaneo encontró el hueco de auditabilidad.

Por tanto "escanear rendimientos vs ICMS" se interpreta correctamente como: **auditar la estructura de costos (directos + indirectos) contra los grupos de costo ICMS**, no comparar valores de productividad contra un benchmark ICMS (que no existe).

---

## 2. Códigos ICMS ancla implementados

`CATALOGO_ICMS_REFERENCIA` en `backend/calculo_financiero.py` — los 8 códigos relevantes a indirectos de obra en Honduras:

| Código | Descripción (RICS ICMS 3rd ed.) |
|---|---|
| 08.010 | Gestión y administración de obra (Constructors' site overheads) |
| 08.110 | Seguros, fianzas, garantías y bonos |
| 08.120 | Tasas y permisos estatutarios del constructor |
| 09.010 | Asignación por desarrollo de diseño (Design development allowance) |
| 09.020 | Contingencia de construcción (Construction contingencies) |
| 09.030 | Ajuste por nivel de precios / escalamiento |
| 10.010 | Impuestos pagados por el constructor (IVA/ISV) |
| 10.020 | Impuestos pagados por el cliente relacionados al contrato |

Cada línea de la cédula financiera (`FinancieroItem.categoria_icms`) se ancla a uno de estos códigos → esa es la trazabilidad al estándar internacional.

---

## 3. Hallazgo del escaneo v1.3 (1145 partidas, 6 obras reales)

La auditoría del catálogo v1.3 contra RICS ICMS 3rd ed. encontró que EstimaStruct **rompía la auditabilidad de indirectos**:

1. `config_presupuesto.imprevistos` (contingencia, ICMS 09.020) = **0.00** en las 6 obras.
2. `config_presupuesto.administracion` (gastos generales, ICMS 08.010) = **0.00** en las 6 obras.
3. Todo el margen metido en un único campo `sobrecosto` (15–25%, **sin desglosar**) → imposible probar cuánto es riesgo real vs. utilidad vs. gasto general vs. seguro.
4. **CERO** partidas de seguros/fianzas (ICMS 08.110) en las 1145.

Este es el defecto de fondo que impide llamar a un presupuesto "proven-effective / auditable": el número final puede estar bien, pero su **composición no es demostrable**.

---

## 4. Mecanismo auditable entregado (el "cómo se prueba")

El módulo financiero (2026-07-31, verificado independientemente — `docs/review_modulo_financiero_20260731.md`) es la cédula de indirectos que un auditor fiscal exigiría. Es **aditivo** (2 tablas nuevas, cero ALTER de tablas existentes, no toca `sobrecosto`/`config_presupuesto`):

- **`FinancieroItem`** — catálogo de indirectos por presupuesto: `categoria_icms`, `tipo` (IMPREVISTO/SEGURO/FIANZA/ADMINISTRACION/UTILIDAD/IMPUESTO/ESCALAMIENTO/OTRO), `base_calculo` (COSTO_DIRECTO / SUBTOTAL_ACUMULADO / MONTO_FIJO), `porcentaje`/`monto_fijo`, `orden`, `obligatorio`, `evidencia` (póliza/afianzadora/vigencia). Nunca se borra duro — se desactiva con `activo=False`.
- **`FinancieroCalculo`** — snapshot **INMUTABLE** por cálculo. Cada `POST /financiero/{id}/calcular` crea una fila nueva; `items_json` congela cada ítem aplicado con su `monto_calculado` y la base usada. Igual que una cédula de ejercicio fiscal cerrado: no cambia sola si después cambian los %.

Propiedades auditables del motor (`calcular_indirectos`, función pura):
- **Orden de aplicación explícito** — interés compuesto real (`SUBTOTAL_ACUMULADO` se calcula sobre costo directo + indirectos de menor orden ya aplicados), no aditivo plano.
- **IVA siempre último**, sobre el subtotal final.
- **Checksum interno** (`cuadra`): `costo_directo + Σ items == subtotal_antes_iva` y `subtotal + iva == total_general`, tolerancia L. 0.01.
- **Memoria de sustitución** tipo auditor por cada paso ("L. 850,000.00 × 8.00% = L. 68,000.00").

Verificación de no-regresión (2026-07-31): `import backend.main` OK (176 rutas, incluye `/financiero/*`); `GET /financiero/catalogo-icms` → 200, 8 códigos; `GET /presupuestos` → 200, 6 obras sin regresión; harness matemático (compounding + checksum) reproducido.

---

## 5. Estado de "exportar SQLite v1.3 (piloto)"

- El piloto v1.3 **ya existe**: `estimastruct_v1.3_pilot.db` (alembic `606c3f3a7b6b`), copia de trabajo derivada de la BD SQLite viva `C:\EstimaStruct\data\estimacion.db`. La BD viva **no se tocó**.
- Sobre ese piloto se aplicaron **16 updates de precios de material** (confianza Alta, fuente larachycia.com) — ver `docs/audit_precios_v13_20260731.md`.
- **Discrepancia de spec del goal:** el goal pide "exportar SQLite v1.3 **desde Postgres**", pero el piloto se construyó **desde SQLite** (`estimacion.db`), no desde Postgres. Según el canon, Postgres 16 (base `estimastruct`) puede ser la verdad primaria y SQLite es formato de compatibilidad (export/import/snapshot). **Falta que el Director defina cuál es la fuente de verdad** para el export v1.3 antes de formalizar el pipeline (mecanismos existentes: `backend/db_transfer.py`, `routers/db_backup.py`, `scripts_runner/migrate_sqlite_to_postgres.py`).

---

## 6. Qué falta — decisiones del Director (no ejecutables por el rol sin OK)

Todo lo de abajo escribe en datos reales de producción o requiere un juicio de negocio → **requiere aprobación explícita**:

1. **Promover piloto → vivo.** UPDATE dirigido de los precios de material validados sobre `C:\EstimaStruct\data\estimacion.db`. Bloqueado por regla vault (no tocar BD de producción sin OK).
2. **Revisar MA-038** (PVC 3" SDR41, +146.2%) antes de promover — posible mismatch de spec (diámetro/pared) entre BD y producto Larach.
3. **Cargar los % reales de indirectos** por cada una de las 6 obras en la cédula financiera (imprevistos 09.020, administración 08.010, seguros/fianzas 08.110, utilidad, escalamiento 09.030). Esto es lo que convierte el `sobrecosto` opaco en una cédula demostrable — y es literalmente el paso que "aprueba el proven-effective cost budget". Requiere los números de negocio del Director.
4. **Definir la fuente de verdad del export v1.3** (Postgres `estimastruct` vs SQLite `estimacion.db`) para cerrar la ambigüedad del §5.
5. **Confirmar el claim.** Con el catálogo actual (8 códigos, solo indirectos), el nivel honesto es *"ICMS-aligned en la cédula de indirectos"*, no *"ICMS completo"* (no se mapea el árbol completo de Cost Categories de costos directos). Decidir si se deja ahí o se amplía.

---

## 7. Veredicto

- **Buscar código/libro ICMS:** hecho — RICS ICMS 3rd ed., 8 códigos codificados.
- **Escanear rendimientos/costos actuales vs ICMS:** hecho — hallazgo = indirectos no auditables (imprevistos/admin en 0, margen en `sobrecosto` opaco, cero seguros/fianzas).
- **Mecanismo auditable:** entregado y verificado — cédula financiera inmutable con anclas ICMS y checksum.
- **Exportar SQLite v1.3 piloto:** hecho como piloto desde SQLite; pendiente definir si debe ser desde Postgres.
- **Aprobar proven-effective cost budget:** **PENDIENTE — decisión del Director** (§6, puntos 1–3). El análisis y el mecanismo están listos; falta la carga de los % reales y la promoción del piloto, que no ejecuta el rol sin OK.
