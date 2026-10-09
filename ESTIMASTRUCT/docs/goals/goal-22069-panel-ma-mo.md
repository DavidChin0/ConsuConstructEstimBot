# Goal 22069 — Panel "Gasto por semana" (MA+MO) en portal

> **Estado:** ✅ **APROBADO + COMMITEADO + DEPLOYADO** | `f5fb8c9` en `main`  
> **Deploy:** Vercel deployment `6848231001` en Producción (2026-10-04 23:26 UTC)  
> **Reviewer VERDICT:** APPROVE acotado (cierra commit; paridad declarada condicionada a dato partida 13)

## 4 archivos del panel (scope aislado)

| Archivo | Tipo | sha256 |
|---|---|---|
| `src/lib/gasto-semanal.ts` | nuevo | `c6877b8d95e39e91b03edfb0e2c9e03d6177428c14ef60e5c8a37238b7d62953` |
| `src/app/portal/admin/obra/[id]/_components/gasto-semanal-panel.tsx` | nuevo | `a7030dd5a74282f6628559f84079cf601358fc704c14fb94f3b20445baf8b8c1` |
| `src/app/portal/admin/obra/[id]/_components/gantt-editor.tsx` | mod | `de8c0dd46a0ce26fb2908bc3367a7aa6d15cbf8c520edb8c56a5ae593a06aeec` |
| `src/app/portal/admin/obra/[id]/gantt/page.tsx` | mod | `3e50b24655280ab368a599a9e553282914fb5222a01d895d55260f57eefa6e66` |

## Algoritmo (espejo del motor Python)

`gasto-semanal.ts` replica exactamente el motor `backend/cronograma.py`:
- **Días laborables lun-sáb**, domingo no se trabaja (TS: `d.getDay() !== 0` ↔ Python: `weekday() != 6`)
- **Frac** = `dias_semana / duracion_dias` (proporcional al días en la semana)
- **MA** = `obra_material.cantidad_unit × partida_valor.cantidad × frac × obra_material.costo_unit`
- **MO** = `partida_valor.costo_mo × partida_valor.cantidad × frac`
- `schema_translate_map`: materiales agrupan por `clave|unidad` (fallback `descripcion|unidad`)
- **Costo directo**, sin sobrecosto (igual que EstimaStruct)

## Paridad numérica — CC132 (obra real)

> **Nota canónica (David 2026-10-09):** PostgreSQL `estimastruct` (127.0.0.1:5432) es la BD canónica de EstimaStruct. La SQLite versionada es runtime/mirror. La paridad fue validada sobre el backup `estimacion.db.BACKUP_20260917_195830_postgres_unica_fuente` como snapshot puntual; si Postgres está actualizado, repetir.

**Datos reales (snapshot SQLite v1.3 → backup Postgres unica fuente):** 98 partidas, 314 materiales, 57 actividades con fecha.

| Métrica | TS cliente | Python equivalente | Dif |
|---|---|---|---|
| 17 semanas → 14 con cantidad canon | — | — | — |
| **MA** | 476,843.48 | 476,843.42 | 0.06 (redondeo) |
| **MO** | 357,636.73 | 357,636.43 | 0.30 (redondeo) |
| **Max diferencia semanal** | 0.29 | — | redondeo `r2` |

**Root cause S4 (cerrada):** 1 sola partida (CSI `03 31 01.3`, concreto) difería en cantidad:
- Portal: **34.0 mL** → corregido a **33.48 mL** (canónico EstimaStruct)
- Total partida: 54,515.35 → **53,681.59** (`33.48 × 1603.3927`)
- Ratio 34/33.48 = 1.0155 → explica el ~1.5% observado en 5 materiales de concreto

## Fechas CC132

- Motor Python `FECHA_DEFAULT = date(2026, 6, 15)` (lunes) → cronograma parte del lunes 2026-06-15.
- `_suma_dias_laborales` salta domingos → idéntico al TS `diasPorSemana`.
- **57/57 fechas coinciden** perfectamente (snapshot hash idéntico).

## Corrección aplicada a partida 13

```sql
-- PATCH (por id, solo cantidad)
UPDATE public.partida_valor
  SET cantidad = 33.48
WHERE id = 'e15efe51-6676-46da-89fd-b9c08fb19d98';
```
- **Antes:** cantidad 34.0, total 54,515.35
- **Después:** cantidad 33.48, total 53,681.59
- Row previa y read-back con SHA256 verificables.
- **Rollback:** `cantidad=34.0, total=54515.35` (documentado en informe).

## Bloqueo de datos (no del código)

**Desfase `obra.total`:** 833.76 (1,097,110.22 vs 1,096,276.46).
- El panel MA+MO **no usa** `partida_valor.total` → no se ve afectado.
- `obra.total` sigue en 1,097,110.22 (valor del contrato con cantidad 34.0).
- **Decisión pendiente de David:** si `obra.total` debe bajar a 1,096,276.46 (cambio comercial) → UPDATE con OK + review reviewer.

## Condiciones del commit (cumplidas)

1. ✅ Commit solo de los 4 archivos (sin `git add -A`).
2. ✅ Alcance ampliado aceptado (`gantt-editor.tsx`: arrastrar filas, `autoCadena`, enlaces materiales/CSV).
3. ⏸️ **Deploy bloqueado** hasta tener `pg_constraint`/`pg_indexes` posterior al script UNIQUE. HTTP 200 del upsert = evidencia indirecta.

## Archivos de evidencia (scratch)

- `22069_paso3_evidencia_ma_mo.md` — paquete completo de paridad (sha256 informe `58a8aea0...`)
- `goal22069_ma_mo_panel_only.diff` — unified diff aislado a 4 archivos (`git apply --reverse --check` → EXIT 0)
- `22069_parity_input.json` / `22069_parity_ts_output.json` / `22069_parity_py_output.json` / `22069_parity_py.py` / `22069_parity_runner.js` — inputs y outputs de la paridad
