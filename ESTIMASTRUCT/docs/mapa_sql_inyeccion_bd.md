# Mapa SQL + Inyección de BD — EstimaStruct

> **Fecha:** 2026-07-16 · **Alcance:** `backend/config.py`, `backend/db.py`, `backend/models.py`,
> `backend/routers/db_backup.py` (feature nueva: export/import ZIP).
> Schema real extraído con `.schema` sobre una **copia** de la BD viva hecha vía
> `sqlite3.Connection.backup()` (nunca se leyó `.schema` con otra conexión directa sobre el
> archivo en uso). Ver sección (e) para el porqué.

---

## (a) Schema real — tablas, columnas clave, FKs/cascadas

BD: SQLite, un solo archivo (`estimacion.db`). 13 tablas de aplicación (ORM, `backend/models.py`)
+ `alembic_version` (control de migraciones) + `sqlite_stat1` (interna de SQLite, estadísticas de
índices — no es de negocio, se recrea sola con `ANALYZE`).

Tablas núcleo, en el orden real de dependencia (padre → hijo, `ON DELETE`):

```
presupuesto                                          (raíz — nada depende de nada, PK id)
├─ config_presupuesto     (1:1, FK presupuesto_id → CASCADE)
├─ capitulo               (1:N, FK presupuesto_id → CASCADE)
│  └─ partida             (1:N, FK capitulo_id → CASCADE)
│     └─ insumo_partida   (1:N, FK partida_id → CASCADE; FK recurso_id → SET NULL)
├─ diseno_elemento        (1:N, FK presupuesto_id → CASCADE)
│  └─ caso_diseno         (1:N, FK diseno_elemento_id → CASCADE)
│     └─ resultado_diseno (1:1, FK caso_id → CASCADE
│                           + FK partida_concreto_id/partida_acero_id/partida_encofrado_id → SET NULL)
├─ contexto_sismico       (1:1, FK presupuesto_id → CASCADE, unique)
├─ conexion_acero         (1:N, FK presupuesto_id → CASCADE; FK partida_id → SET NULL)
│  └─ conexion_caso       (1:N, FK conexion_id → CASCADE)
│     └─ conexion_resultado (1:1, FK caso_id → CASCADE)
└─ cronograma_override    (1:N, FK presupuesto_id → CASCADE; FK partida_id → CASCADE, unique)

recurso                    (independiente — catálogo de insumos, referenciado por insumo_partida)
```

Conteos reales al 2026-07-16 (BD viva, vía copia backup API):

| Tabla | Filas |
|---|---|
| presupuesto | 6 |
| capitulo | 88 |
| partida | 1133 |
| insumo_partida | 7340 |
| recurso | 367 |
| diseno_elemento | 58 |
| caso_diseno | 4 |
| resultado_diseno | 4 |
| contexto_sismico | 1 |
| conexion_acero / conexion_caso / conexion_resultado | 0 (módulo sin datos aún) |
| cronograma_override | 0 |

`alembic_version.version_num` actual: `606c3f3a7b6b`.

Notas de columnas (lo no obvio):
- `partida.clave_csi` es el identificador CSI ("03 31 00.1"); NO es PK, puede repetirse entre obras.
- `partida.color_tipo` (amarillo/verde/azul/rosa/blanco) es metadata de auditoría visual del Excel origen.
- `diseno_elemento.material_tipo` (`CONCRETO`|`ACERO`) decide si el motor de cálculo usa el flujo
  ACI (concreto) o LRFD §D-H (acero) — mismo par de tablas `caso_diseno`/`resultado_diseno` para ambos.
- `recurso.tipo` tiene CHECK constraint: `MATERIAL|MANO_OBRA|HERRAMIENTA|EQUIPO|FLETE|SUBCONTRATO|DISEÑO`.
- `cronograma_override.cuadrillas` está DEPRECADO (columna legacy); el campo vigente es el par
  `n_esp`/`n_ay` (especialistas/ayudantes en paralelo).

El `CREATE TABLE` completo de las 13 tablas (`.schema` literal) queda documentado en el propio
código fuente `backend/models.py` (SQLAlchemy declarativo — es la fuente de verdad; este doc es
un resumen de lectura rápida, no lo dupliques a mano si el modelo cambia).

---

## (b) Cómo abre la BD el backend

- **Ruta canónica:** `backend/config.py` → `CONFIG.DB_PATH`, default `C:\EstimaStruct\data\estimacion.db`,
  override por variable de entorno `ESTIMA_DB_PATH` (así es como el harness de verificación levanta
  una segunda instancia en otro puerto apuntando a una copia temporal, sin tocar la BD viva).
- **Conexión:** `backend/db.py` — `create_engine("sqlite:///" + DB_PATH, connect_args={"check_same_thread": False})`.
  Un solo `engine` module-level, `SessionLocal = sessionmaker(bind=engine)`. Los routers casi todos
  usan `get_db()` (dependency generator); un puñado usa `SessionLocal` directo (`scripts_runner/*`,
  `routers/scripts.py`, `routers/diagnostics.py`). Solo `backend/main.py` importa `engine` en sí
  (para `Base.metadata.create_all(bind=engine)` en el lifespan).
- **PRAGMAs aplicados en cada conexión nueva** (evento SQLAlchemy `"connect"`, `backend/db.py:_set_sqlite_pragmas`):
  - `foreign_keys=ON` — activa los `ON DELETE CASCADE`/`SET NULL` reales del modelo (si esto
    estuviera OFF, borrar un `presupuesto` dejaría huérfanos en cascada silenciosos).
  - `journal_mode=WAL` — modo Write-Ahead Log: las escrituras van a un archivo `-wal` aparte y se
    "checkpointean" (fusionan) al `.db` principal periódicamente; permite lecturas concurrentes
    mientras se escribe, y es el motivo por el que la BD vive FUERA de OneDrive (WAL + sync de
    OneDrive = corrupción).
  - `synchronous=NORMAL` — balance seguridad/performance razonable bajo WAL.
  - `mmap_size=268435456` (256 MB) y `cache_size=-16000` (16 MB) — tuning de lectura, no afectan
    la lógica de inyección.

---

## (c) Requisitos para inyectar una BD externa

Cualquier `.db` que se quiera cargar como reemplazo de `estimacion.db` (vía el import ZIP de este
feature, o manualmente) debe cumplir, en este orden de verificación:

1. **Ser un ZIP válido** (si se usa el flujo de import ZIP) que contenga al menos un archivo `.db`.
2. **Header SQLite real**: los primeros 16 bytes del archivo deben ser exactamente
   `SQLite format 3\x00` (literal, incluye el byte nulo final). Cualquier otra cosa (HTML de error,
   archivo truncado, texto plano) se rechaza aquí, antes de tocar nada.
3. **Contener las tablas núcleo reales** — no una lista hardcodeada, sino las que salen de
   `Base.metadata.tables` en `backend/models.py` en el momento de ejecutar el import (así el
   router `db_backup.py` se mantiene en sync automáticamente si el modelo crece). Hoy son las 13
   tablas de la sección (a) — si falta alguna, se rechaza con el detalle de cuáles.
4. **`PRAGMA quick_check` debe devolver `ok`** — chequeo de integridad rápido de SQLite (páginas,
   índices, estructura B-tree). No es tan exhaustivo como `PRAGMA integrity_check` pero es
   suficiente para descartar un archivo corrupto/truncado sin pagar el costo completo en una BD
   de varios MB.

Si CUALQUIERA de estos 4 pasos falla, el endpoint `POST /db/import-zip` responde `400` con el
detalle y **la BD viva no se toca** — todas las validaciones corren sobre archivos temporales
(`tempfile.mkdtemp`), nunca sobre `CONFIG.DB_PATH` directamente, hasta que TODO pasó.

No se valida (fuera de alcance de este feature): que los datos sean semánticamente correctos, que
`alembic_version` coincida con la revisión que espera el código actual, ni que los UUID de FK
referencien filas existentes dentro del propio archivo importado (eso ya lo garantiza el propio
SQLite si el archivo pasó `quick_check` y fue generado por esta misma app u otra copia de ella).

---

## (d) Los 2 caminos para inyectar una BD

### Camino 1 — Import ZIP (este feature, recomendado)

`POST /db/import-zip?confirm=true` (multipart, campo `file`) — botón "📥 Importar BD (ZIP)" en la
zona **Bases de Datos** (modo desarrollador) del frontend.

Flujo interno (`backend/routers/db_backup.py`):
1. Todas las validaciones de la sección (c), sobre archivos temporales.
2. `counts_before` — cuenta filas de las tablas núcleo en la BD viva actual (para el reporte).
3. `PRAGMA wal_checkpoint(TRUNCATE)` sobre la BD viva — vacía el `-wal` actual a la BD principal.
4. Backup de la BD viva (ya checkpointeada) a `C:\EstimaStruct\backups\estimacion_pre_import_<ts>.db`,
   vía `sqlite3.Connection.backup()` (no file-copy).
5. `engine.dispose()` — libera el pool de conexiones de SQLAlchemy sobre el archivo viejo. El
   objeto `engine` NO se recrea (misma identidad de objeto en memoria) — así los módulos que ya
   hicieron `from backend.db import engine` (`main.py`) o usan `SessionLocal` (la mayoría de
   routers vía `get_db()`, y `scripts_runner/*`) siguen funcionando sin tocar sus imports.
6. Se borran los sidecars `-wal`/`-shm` huérfanos junto al archivo canónico (ver sección (e)).
7. Se copia el `.db` validado del ZIP sobre `CONFIG.DB_PATH` (reemplazo del archivo canónico).
8. `engine.dispose()` de nuevo — fuerza que el siguiente `SessionLocal()` abra una conexión NUEVA,
   que ve el archivo reemplazado. El hook de PRAGMAs (`"connect"`) se re-aplica solo.
9. `SELECT 1` de sanidad a través del mismo camino que usan los routers (`SessionLocal`/`get_db`).
10. `counts_after` + respuesta con el resumen (backup guardado, counts antes/después, alembic).

Este camino es el único que deja un backup automático del estado previo y corre las 4
validaciones de la sección (c) antes de tocar nada.

### Camino 2 — Reemplazo manual del archivo (server apagado)

Para cuando no se puede pasar por la API (ej. recuperación de desastre, servidor no arranca):

1. **Detener el servidor backend** (`uvicorn ... backend.main:app`) por completo — no basta con
   que esté "sin tráfico"; mientras el proceso vive, el pool de SQLAlchemy puede tener el archivo
   abierto y el reemplazo puede fallar (`PermissionError` en Windows) o dejar un estado mixto.
2. Sobre la BD que se va a reemplazar (la actual, antes de tocarla): hacer checkpoint manual:
   `sqlite3 estimacion.db "PRAGMA wal_checkpoint(TRUNCATE);"` — fusiona `-wal` al `.db` principal
   y lo deja en un solo archivo consistente antes de moverlo/respaldarlo.
3. Copiar el `.db` de reemplazo sobre `C:\EstimaStruct\data\estimacion.db` (con el server parado,
   un `copy`/`Copy-Item` normal ya es seguro — no hay proceso escribiendo).
4. Borrar cualquier `-wal`/`-shm` viejo que haya quedado junto al archivo (del estado previo).
5. Arrancar el servidor de nuevo (`START_UNICA.ps1` o equivalente).

Este camino NO deja backup automático — hay que hacerlo a mano antes del paso 3 (o usar el botón
"Exportar copia BD (ZIP)" mientras el server viejo aún corre, antes de apagarlo).

---

## (e) Advertencias

- **Nunca copiar el `.db` vivo a mano (file-copy crudo) con el servidor corriendo.** En modo WAL,
  el archivo principal puede NO tener todos los cambios recientes — esos viven en el `-wal` hasta
  que se checkpointea. Una copia cruda del `.db` en ese momento puede quedar **inconsistente**
  (le faltan transacciones confirmadas) o, peor, referencialmente rota si el copiado ocurre a
  mitad de una escritura. La API de backup online de SQLite (`sqlite3.Connection.backup()`, la que
  usa este feature) sí es segura en caliente: opera a nivel de páginas dentro del propio motor,
  incorpora el contenido del WAL, y no requiere parar nada.
- **Qué son `-wal` y `-shm`:** sidecars del modo WAL, viven junto al `.db` con el mismo nombre +
  sufijo (`estimacion.db-wal`, `estimacion.db-shm`). El `-wal` es el log de escrituras aún no
  fusionadas al archivo principal; el `-shm` es memoria compartida de coordinación entre procesos
  lectores/escritores (índice del WAL). **No se pueden mover ni copiar por separado del `.db`
  principal** — si te llevas solo `estimacion.db` sin su `-wal` en modo WAL activo, puedes perder
  las últimas transacciones. Por eso el import (camino 1) y el manual (camino 2) siempre
  checkpointean primero (`wal_checkpoint(TRUNCATE)`) para dejar todo fusionado en el archivo
  principal antes de mover/reemplazar nada, y limpian los sidecars huérfanos después de reemplazar
  el archivo canónico (para que no queden apuntando a un archivo que ya no es el que originaron).
- **`C:\EstimaStruct\backups\` no es lo mismo que `C:\EstimaStruct\data\`** — el primero son
  snapshots point-in-time (creados automáticamente antes de cada import, o manualmente vía export
  ZIP); el segundo es la ruta canónica que lee `CONFIG.DB_PATH`. Nunca apuntar `ESTIMA_DB_PATH` a
  un archivo dentro de `backups\` en producción — es solo un histórico de recuperación.
- **`ESTIMA_DB_PATH` es la única forma segura de probar un import** sin arriesgar la BD viva:
  levantar una segunda instancia de uvicorn en otro puerto con esa variable apuntando a una copia
  (hecha con `sqlite3.Connection.backup()`, nunca file-copy) en un directorio temporal.
