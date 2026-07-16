# EstimaStruct — Cambios 2026-06-16 (estabilización + perf + modularización)

Sesión Claude. Sistema NO es repo git → este archivo es el registro de cambios.
Verificación: BD con datos reales (5 presupuestos / 1035 partidas / 6759 insumos / 363 recursos).

## FASE 0 — Estabilización de BD (irreversible, verificada)
- **BD movida fuera de OneDrive**: ahora `C:\EstimaStruct\data\estimacion.db` (antes `backend\estimacion.db`, que OneDrive corrompía por sync).
- **`db.py`**: ruta absoluta vía `config.py`; event listener aplica `PRAGMA foreign_keys=ON` + `journal_mode=WAL` + `synchronous=NORMAL`; `get_db()` con rollback ante excepción.
- **34 filas huérfanas limpiadas** (FK estaba OFF) en transacción, borrando subárbol completo (25 diseno_elemento+casos/resultados, 2 conexion_acero+hijos, 1 contexto_sismico). Núcleo intacto.
- **`cronograma.py`** runner offline (`__main__`) repuntado a `CONFIG.DB_PATH`.
- Verificado: `integrity_check=ok`, conteos 5/77/1035/6759/363, app sirve `/presupuestos`=5.

## FASE 1 — Backend (verificado)
- **`services/pricing.py`** (NUEVO): fuente única de precios; reemplaza 4 copias en partidas/calculos/insumos/presupuestos. Gate regresión Δ=0.0000 (StoneRaise+CC132 tras `calcular`).
- **Índices FK** en `models.py` + BD viva: capitulo.presupuesto_id, partida.capitulo_id, insumo_partida.partida_id/recurso_id. EXPLAIN → `SEARCH USING INDEX`.
- **`config.py`** (NUEVO): 15 paths hardcodeados `D:\OneDrive\...` migrados (bases/scripts/updater/diseno_estructural/presupuestos/acero_ficha/generate_keynotes). Defaults == valores viejos. 27/27 módulos importan.
- **Validación Pydantic** en `recursos` PATCH (`UnidadIn`/`PrecioIn`).
- **Path traversal cerrado** en `updater.py` (`_safe_within` + saneo `version`).
- **`silent_notifier`**: `except: pass` → `logger.exception`.
- **N+1** en reasignar-capitulos: mapa id→cap (sin query por partida).

## FASE 2 — Frontend (parcial)
- **Hardening** (`app.js`): `api()` con AbortController+timeout 15s; init `getElementById(x)?.addEventListener` (un botón faltante ya no aborta el init).
- **Modularización** (multi-`<script>` clásico, scope global compartido — NO ES-modules): app.js **6817 → 1813 líneas (−73%)**. Nuevos archivos en `frontend/js/`:
  - `core.js` (95) — API/state/DIVISIONES_CSI/fmt/esc/api + bus pub/sub.
  - `calculo-estructural.js` (3263) — DISEÑO ACI + ETABS/CHOC-08 + ACERO AISC + CONEXIÓN §J.
  - `bases-drawer.js` (1253) — editor Bases de Datos.
  - `tabla-render.js` (427) — renderTable + handlers + findPartida.
  - Orden carga (ambos HTML): `core → app → calculo → bases-drawer → tabla-render`.
  - Verificación: `cat *.js | node --check` sin redeclaraciones/syntax (carga en scope compartido segura).

## Rendimiento (verificado)
- **`listar()`** usa agregado SQL (no carga 1035 partidas ORM solo para sumar). Gate: SQL == Python loop.
- **PRAGMA** `mmap_size=256MB` + `cache_size=16MB` en `db.py`.
- **`calcular`** skip-unchanged: evita reescribir ~6759 insumos sin cambio.

## Backups (para rollback)
- BD: `_LEGACY\backend\db_backups\estimacion.vacuum_20260616.db` (VACUUM, consistente); BD vieja en `backend\estimacion.db.pre_migration_20260616` (o `estimacion.db` si OneDrive la bloqueó).
- app.js: `app.js.bak_premod_20260616` (pre-core), `.bak_premod2` (pre-calculo), `.bak_premod3` (pre-bases), `.bak_premod4` (pre-tabla).
- HTML prod: `ESTIMASTRUCT\templates\_backups\index.html.bak_premod_20260616`.

## Pendiente / decisiones
- 🔴 **DATO — "Apartamento Valle de Angeles"**: `sobrecosto=0` en config con markup viejo embebido en PU. Un `calcular`/edición le borra ~118k. Definir: ¿sc real o PU stale? NO tocado.
- **Perf frontend** (event delegation + update parcial en vez de `loadObra` por celda): requiere test funcional en browser (este entorno bloquea Chrome MCP/computer-use). Diferido.
- **HTML divergencia**: `index_preview.html` (preview) atrás de `templates\index.html` (prod) → `/preview/promote` REGRESARÍA prod. Resincronizar preview con prod antes de volver a usar el flujo promote.
- Diferido baja prioridad: `memory.py` validación + conexión sqlite manual.
