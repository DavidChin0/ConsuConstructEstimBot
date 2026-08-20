# Migración Módulo Financiero → schema propio `financiero` (goal-21080)

Estado: **diseñada e implementada en código — NO aplicada contra Postgres**
(requiere OK David + prerrequisito, ver abajo).

## Qué cambió

1. **`backend/models.py`** — `FinancieroItem` y `FinancieroCalculo` ahora viven
   en el schema `financiero` en Postgres (`_FIN_SCHEMA = None if DB_IS_SQLITE
   else "financiero"`). En SQLite siguen en el schema default → `create_all` del
   backend dev queda intacto, cero regresión.
2. **`backend/alembic/versions/7f3e9c1a2b4d_financiero_schema.py`** — migración
   **escrita a mano** (no autogenerate): `CREATE SCHEMA financiero` + las 2
   tablas con su FK cross-schema a `public.presupuesto` (ON DELETE CASCADE),
   índices sobre `presupuesto_id` y los 2 CHECK. No-op fuera de Postgres.
3. **`backend/alembic/env.py`** — red de seguridad `include_object`: autogenerate
   ya **no puede** emitir `DROP` de tablas reflejadas que no están en `models.py`.

## Por qué NO se usó `alembic revision --autogenerate`

El schema `public` de la BD Postgres de EstimaStruct contiene objetos que NO
están en `models.py`:

- Tablas: `arch_chunks`, `assistant_sessions`, `assistant_messages`,
  `csi_codes`, `csi_embeddings`.
- Schema completo: `rag`.

`target_metadata = Base.metadata` sólo conoce lo que el ORM modela, así que
autogenerate los interpreta como "sobrantes" y genera `DROP TABLE` / `DROP
SCHEMA`. Correr eso **destruiría** esos datos. Por eso la migración es a mano y
env.py tiene el filtro defensivo.

## PRERREQUISITO antes de aplicar (bloqueante)

La tabla `public.presupuesto` debe existir en la BD Postgres — las 2 tablas
nuevas tienen FK → `presupuesto.id`. En el estado split-brain actual (Postgres
stale, core aún en SQLite; ver decisión final goal-21069/ADR-014) el core
`presupuesto/partida/...` todavía no está en Postgres. Por lo tanto:

> La migración SQLite→Postgres del **core** (goal-21070/21071, gated a OK David)
> debe correr ANTES que esta. Si `presupuesto` no existe, esta migración falla
> limpio en la creación de la FK — todo en una transacción, no deja a medias.

## Cómo aplicar (Postgres, cuando David lo autorice)

```
set ESTIMASTRUCT_DATABASE_URL=postgresql+psycopg://<user>:<pass>@127.0.0.1:5432/estimastruct
cd D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\backend
"D:\LLM\python\python.exe" -m alembic current          # verificar que está en baseline 606c3f3a7b6b
"D:\LLM\python\python.exe" -m alembic upgrade 7f3e9c1a2b4d
```

Verificar post-migración:

```sql
\dn financiero
\dt financiero.*
-- esperado: financiero.financiero_item, financiero.financiero_calculo
```

Rollback: `alembic downgrade 606c3f3a7b6b` (dropea las 2 tablas y el schema si
quedó vacío — `DROP SCHEMA ... RESTRICT`, nunca CASCADE).

## Validación hecha en el diseño (sin conectar a BD)

- `py_compile` OK de models.py, env.py y la migración.
- Metadata SQLAlchemy: SQLite → `schema=None`; Postgres → `schema=financiero`.
- DDL generada por el ORM (dialecto postgres) coincide 1:1 con la migración a
  mano (VARCHAR(36) / TEXT / NUMERIC / SMALLINT / los 2 CHECK / FK ON DELETE
  CASCADE).
