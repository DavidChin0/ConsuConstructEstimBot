# Promocion precios v1.3 -> BD viva -- verificacion goal-21062 (2026-08-15)

**Contexto:** David autorizo (2026-08-15 06:32 CST, goal-21062, decision sobre goal-19701):
1. Promover los 16 updates de precio del piloto v1.3 a produccion (`estimacion.db`) -- AUTORIZADO.
2. MA-038 PVC 3" SDR41 +146% -- AUTORIZADO, no bloquear.
4. Export desde SQLite (no Postgres) -- suficiente, no forzar Postgres.

## Justificacion MA-038 (+146%) -- ACLARACION David 2026-08-15 06:49 CST (goal-21063)

`MA-038` (Tubo de PVC 3" SDR 41): `L.195 -> L.480` (**+146.2%**), ya aplicado en `estimacion.db` el 2026-07-31 (batch unico, ver tabla abajo -- BD viva = 480, Match OK).

**David confirma explicitamente:** el +146% **NO es un error de captura ni un outlier a descartar**. Refleja un **incremento real de mercado en materiales durante 2026** -- el PVC recibio un golpe fuerte de precios este ano. El porcentaje **fue verificado por David** contra el precio real (Larach y Cia, PVC SDR41 3"x20pies). Se registra como precio de produccion valido y correcto, no como caso a revisar.

Esto **cierra** la marca "delta grande, REVISAR / verificar antes de aplicar en vivo" que arrastraba `audit_precios_v13_20260731.md`: ya no es una advertencia pendiente, es un dato de mercado 2026 verificado por el Director. No se requiere ninguna escritura adicional a `estimacion.db` -- el valor 480 ya esta vivo; este bloque es el registro/changelog de la justificacion pedido por goal-21063.

## Hallazgo: la promocion YA estaba aplicada

Verificacion read-only sobre `C:\EstimaStruct\data\estimacion.db` (tabla `recurso`, WAL=0, checkpointed):
los **16 claves estan en su precio "Despues" objetivo**, todos con `ultima_actualizacion = 2026-07-31T05:31:52.452701` (batch unico). No fue necesaria ninguna escritura: la promocion se ejecuto el 2026-07-31, no el 2026-08-15. El header del audit (`audit_precios_v13_20260731.md`) decia "BD viva sin tocar" -- stale, corregido en este mismo turno.

| Clave | Antes | Objetivo | BD viva | Match |
|---|---|---|---|---|
| MA-001 | 230 | 245 | 245 | OK |
| MA-012 | 550.20 | 403 | 403 | OK |
| MA-018 | 21 | 17.75 | 17.75 | OK |
| MA-019 | 27 | 20 | 20 | OK |
| MA-022 | 190 | 144.50 | 144.50 | OK |
| MA-033 | 100 | 175 | 175 | OK |
| MA-038 | 195 | 480 | **480** | OK (autorizado dec.2) |
| MA-052 | 2100 | 2625 | 2625 | OK |
| MA-054 | 260 | 419 | 419 | OK |
| MA-055 | 360 | 470 | 470 | OK |
| MA-059 | 500 | 770 | 770 | OK |
| MA-110 | 42 | 58 | 58 | OK |
| MA-126 | 33 | 26 | 26 | OK |
| MA-247 | 160 | 170 | 170 | OK |
| MA-250 | 20 | 21 | 21 | OK |
| MA-251 | 14 | 11.35 | 11.35 | OK |

Ronda 2 (MA-162=125, MA-163=28) tambien aplicada, `ultima_actualizacion = 2026-07-31T05:44:43`.

## Divergencia abierta: split-brain SQLite vs Postgres

`estimacion.db` (SQLite) tiene los 16 nuevos. **Postgres `estimastruct` NO** -- los 16 siguen en precio VIEJO, `ultima_actualizacion = 2026-04-21` (verificado con psycopg contra `127.0.0.1:5432/estimastruct`, tabla `recurso`).

`architecture.md` declara Postgres primario desde 2026-07-20; `config.py` default es SQLite. El backend :8002 estaba caido durante esta verificacion, asi que no se pudo observar cual DB sirve en runtime -- depende del launcher:
- `START_UNICA.ps1` sin `ESTIMASTRUCT_DATABASE_URL` -> SQLite (refleja los precios nuevos).
- `START_POSTGRES_UNICA.ps1` -> Postgres (NO refleja; presupuestos vivos quedarian con precios de abril).

**No se toco Postgres:** David autorizo "no forzar Postgres" (decision 4) y una escritura a `estimastruct.recurso` es categoria-1 sin autorizacion explicita para esa BD. Queda como decision pendiente de David: definir la fuente de verdad de presupuestos vivos y, si es Postgres, autorizar sincronizar los 16 (+2 de ronda 2) alla.

## Estado goal-21062

La accion literal autorizada (promover 16 -> `estimacion.db`) esta **verificada como ya cumplida**. Lo unico abierto es la divergencia Postgres, que David excluyo explicitamente del alcance. Recomendacion: cerrar goal-21062 con esta evidencia y abrir/decidir por separado la sincronizacion Postgres si ese es el primario real.
