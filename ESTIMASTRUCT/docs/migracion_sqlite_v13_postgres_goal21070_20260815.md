# Migración controlada SQLite v1.3 → Postgres `estimastruct` — diseño (goal-21070)

> **Estado: DISEÑO, NO EJECUTADO.** La migración real está gateada a un **segundo OK explícito de David** (goal-21071). Este documento es el entregable de goal-21070: verificación del split-brain + plan + runbook + ADR para revisión.
> Autor: rol estimastruct (Hooke). Fecha: 2026-08-15. Cadena: goal-21062 (promoción precios v1.3) → goal-21069 (ADR-014, Postgres canónico) → **goal-21070 (este diseño)** → goal-21071 (ejecución gateada).

---

## 1. Parte (1) — Verificación del split-brain: **CONFIRMADO** con evidencia dura

Ambas BD tienen la tabla `recurso` con **367 claves idénticas** (0 altas, 0 bajas entre las dos). La divergencia es **solo de precio** (`precio_unitario`), y es real.

| Recurso testigo | Postgres `estimastruct` | SQLite `estimacion.db` (v1.3) |
|---|---|---|
| MA-038 (Tubo PVC 3" SDR 41) | **195.00** · `ultima_actualizacion` 2026-04-21 | **480.00** · 2026-07-31 |
| máx. `ultima_actualizacion` global | **2026-07-07** (solo altas MA-374..377) | **2026-07-31** (batch v1.3) |

**Postgres nunca recibió el batch del 31-jul.** Su última actividad (07-jul) fueron 4 altas de material (MA-374..377), no las correcciones de precio. La SQLite `C:\EstimaStruct\data\estimacion.db` es la única que tiene los precios v1.3 reales.

### 1.1 Delta exacto: **40 recursos divergentes** (no 16)

El "16 recursos" de goal-21062 fue **solo el primer lote** (timestamp 05:31 del 31-jul). El trabajo de ese día continuó (05:33, 05:44, 14:37, 15:20, 15:37) hasta un total de **40 recursos con precio distinto**: 29 materiales (`MA-*`) + 11 mano de obra (`MO-*`). **La migración debe sincronizar los 40, no 16.**

La divergencia **no es monótona**: hay precios SQLite mayores (MA-038 195→480, MA-047 16→84, MO-009 500→850) y menores (MA-002 910→621, MA-010 1020→442.75, MA-011 70→26, MA-162 175→125). Por eso la regla de reconciliación es **"SQLite v1.3 es autoritativa, sobreescribe Postgres"** — NO "tomar el máximo" ni "solo subir precios".

Lista completa (Postgres → SQLite v1.3):

```
MA-001 230→245   MA-002 910→621   MA-004 20→28     MA-006 30→29
MA-010 1020→442.75  MA-011 70→26  MA-012 550.2→403 MA-018 21→17.75
MA-019 27→20     MA-022 190→144.5 MA-025 293→291   MA-033 100→175
MA-038 195→480   MA-047 16→84     MA-049 70→55     MA-052 2100→2625
MA-054 260→419   MA-055 360→470   MA-057 30→29     MA-059 500→770
MA-110 42→58     MA-126 33→26     MA-132 85→90     MA-162 175→125
MA-247 160→170   MA-250 20→21     MA-251 14→11.35  MA-327 9459.58→9469.58
MO-002 750→1300  MO-003 500→560   MO-005 750→950   MO-006 500→550
MO-007 800→1000  MO-008 700→950   MO-009 500→850   MO-011 450→500
MO-012 500→950   MO-013 700→1000  MO-014 700→1050  MO-015 750→950
```

---

## 2. Por qué el script existente NO sirve para esto

`backend/scripts_runner/migrate_sqlite_to_postgres.py` → `db_transfer.import_sqlite_snapshot_into_primary()` hace un **reemplazo total destructivo**:

```python
for table in reversed(Base.metadata.sorted_tables):
    dst.execute(table.delete())          # BORRA todas las filas de TODAS las tablas core
for table in Base.metadata.sorted_tables:
    dst.execute(table.insert(), rows_del_snapshot)   # re-inserta desde SQLite
```

Para reconciliar 40 precios esto sería **catastrófico**: borraría y re-insertaría `presupuesto`, `partida`, `config_presupuesto`, `diseno_elemento`, `conexion_*`, etc. desde el snapshot SQLite. **Cualquier dato creado mientras el runtime corrió sobre Postgres se perdería**, y `alembic_version` quedaría pisado por el de la snapshot. Es la herramienta equivocada: sirve para "clonar una snapshot entera a una BD vacía", no para "reconciliar un delta acotado sobre una BD viva".

**La migración de goal-21071 debe ser aditiva y acotada: solo `UPDATE public.recurso`, solo los 40 precios, transaccional, con guardas.**

---

## 3. Parte (2) — Diseño de la migración controlada

### 3.1 Principio de autoridad (post ADR-014)

- **SQLite `estimacion.db` v1.3 es autoritativa SOLO para el delta de precios de `recurso`.** Es la snapshot versionada del catálogo v1.3.
- **Postgres `estimastruct` es autoritativa para todo lo demás** (presupuestos, partidas, config, diseño estructural, conexiones) — son datos de runtime que viven solo ahí.
- La migración **no invierte** esa jerarquía: toma el delta de precios de la snapshot y lo aplica a Postgres. No copia presupuestos ni ninguna otra tabla.

### 3.2 Schema propio (aislamiento — requisito del goal)

- Staging en un **schema dedicado `estima_migration`** en la BD `estimastruct`, creado al inicio y **dropeado al final**. Nunca se escribe en `public` salvo el `UPDATE` final sobre `recurso`.
- Tabla de staging: `estima_migration.recurso_sqlite_v13 (clave text, precio_unitario numeric, ultima_actualizacion text)`, cargada desde la SQLite.
- **Regla 32 — RAG de EstimaStruct separado del de Brain:** la migración **no toca `rag.chunks`** (ni el de EstimaStruct ni el de Brain), ni `arch_chunks`, ni `csi_embeddings`, ni ninguna BD que no sea `estimastruct`. Alcance total = `public.recurso` (UPDATE) + `estima_migration.*` (efímero). Verificable: el script no abre ninguna otra conexión ni referencia ningún otro schema.

### 3.3 Runbook (para goal-21071, tras OK David)

**Paso 0 — Congelar y versionar la fuente.**
- Detener escrituras al catálogo (no correr promociones de precio mientras se migra).
- `PRAGMA wal_checkpoint(TRUNCATE)` sobre la SQLite y commitear `estimacion.db` v1.3 a git como snapshot de trazabilidad (ADR-014 la trata como export versionado, no como segunda fuente viva).

**Paso 1 — Backup de rollback.**
- `pg_dump --table=public.recurso estimastruct > backup/recurso_estimastruct_preμigracion_<ts>.sql` (solo la tabla que se toca; barato y suficiente para rollback puntual).

**Paso 2 — Staging aislado.**
```sql
CREATE SCHEMA IF NOT EXISTS estima_migration;
CREATE TABLE estima_migration.recurso_sqlite_v13 (
    clave text PRIMARY KEY,
    precio_unitario numeric,
    ultima_actualizacion text
);
-- cargar las 367 filas de la SQLite (COPY / executemany desde el script)
```

**Paso 3 — Guardas de aborto (verificar ANTES de escribir).**
```sql
-- (a) mismas claves ambos lados — 0 altas/bajas esperadas
SELECT count(*) FROM public.recurso r FULL JOIN estima_migration.recurso_sqlite_v13 s USING (clave)
  WHERE r.clave IS NULL OR s.clave IS NULL;              -- debe dar 0
-- (b) exactamente 40 precios divergentes
SELECT count(*) FROM public.recurso r JOIN estima_migration.recurso_sqlite_v13 s USING (clave)
  WHERE r.precio_unitario <> s.precio_unitario;          -- debe dar 40
```
Si (a) ≠ 0 o (b) ≠ 40 → **ABORTAR** (el estado cambió desde este diseño; re-verificar delta antes de continuar).

**Paso 4 — UPDATE transaccional.**
```sql
BEGIN;
UPDATE public.recurso r
   SET precio_unitario = s.precio_unitario,
       ultima_actualizacion = s.ultima_actualizacion
  FROM estima_migration.recurso_sqlite_v13 s
 WHERE r.clave = s.clave
   AND r.precio_unitario <> s.precio_unitario;
-- verificar GET DIAGNOSTICS row_count = 40 antes de COMMIT; si no, ROLLBACK
COMMIT;
```

**Paso 5 — Verificación post.**
```sql
-- 0 divergencias restantes
SELECT count(*) FROM public.recurso r JOIN estima_migration.recurso_sqlite_v13 s USING (clave)
  WHERE r.precio_unitario <> s.precio_unitario;          -- debe dar 0
-- spot-check
SELECT clave, precio_unitario FROM public.recurso WHERE clave IN ('MA-038','MO-009','MA-010');
-- esperado: MA-038=480, MO-009=850, MA-010=442.75
```

**Paso 6 — Limpieza.**
```sql
DROP SCHEMA estima_migration CASCADE;
```

**Rollback:** si algo sale mal, `psql estimastruct < backup/recurso_estimastruct_preμigracion_<ts>.sql` restaura `recurso` a su estado previo. El staging aislado + el backup puntual hacen el rollback trivial y sin efectos sobre el resto de la BD.

### 3.4 Consecuencia downstream (RIESGO REAL — gate aparte)

Cambiar 40 precios **invalida los totales cacheados** de los presupuestos que usan esos recursos (los `partida.total` y agregados se calcularon con precios de abril). Tras la migración habrá que **recalcular** esos presupuestos (`POST /calcular/{id}` / `estima_calcular`). Eso **modifica documentos de presupuesto reales → es categoría de riesgo real**, se hace por presupuesto y **requiere su propio OK** — no es parte automática de esta migración. goal-21071 debe listar los presupuestos afectados (los que tienen `insumo_partida` referenciando alguno de los 40 recursos) y recalcularlos bajo supervisión.

---

## 4. Gate

- **goal-21070 (este):** verificación + diseño + ADR. **Entregado. No ejecuta nada.**
- **goal-21071:** ejecución de la migración de precios (Pasos 0–6) **solo tras OK explícito de David**.
- **Recalculo de presupuestos afectados:** categoría riesgo real, OK aparte por presupuesto.

---

## ADR-015 (texto para architecture.md §7)

**ADR-015: Migración controlada de precios v1.3 SQLite → Postgres vía UPDATE acotado, no snapshot-replace (2026-08-15, goal-21070 — diseño gateado).**
- Decisión de diseño: la reconciliación del split-brain (ADR-014) se hace con un **`UPDATE` transaccional acotado a los 40 precios divergentes de `public.recurso`**, con staging en schema efímero `estima_migration`, guardas de aborto (mismas 367 claves + exactamente 40 divergencias) y backup puntual de rollback. **No** se usa `import_sqlite_snapshot_into_primary()` (reemplazo total destructivo que borraría presupuestos/partidas/diseño de Postgres).
- Alcance real: 40 recursos (29 `MA-*` + 11 `MO-*`), 0 altas/bajas. SQLite v1.3 autoritativa solo para el delta de precios; Postgres autoritativa para todo lo demás.
- Regla 32: no toca `rag.chunks`/`arch_chunks`/`csi_embeddings` ni ninguna BD fuera de `estimastruct`.
- Estado: **diseñado, no ejecutado.** Ejecución gateada a OK David (goal-21071). Recalculo de presupuestos afectados = gate aparte (riesgo real).
