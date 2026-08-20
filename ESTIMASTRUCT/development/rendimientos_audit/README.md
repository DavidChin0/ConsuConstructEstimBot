# rendimientos_audit — Auditoría online de rendimientos (goal-21170, P0)

Pipeline reproducible que audita **rendimientos** (nunca precios) desde fuentes
online verificables, los cruza con el catálogo EstimaStruct y registra cada valor
en la tabla comparativa `rendimiento_audit` de la SQLite canónica
(`D:\EstimaStruct\data\estimacion.db`) mediante una migración idempotente.

Contrato completo: `docs/goals/rendimientos_online_audit.md`.

## Estado (2026-08-21, cierre)

| Fuente | Actividades | Rendimientos | Capítulos CSI |
|--------|-------------|--------------|---------------|
| FHIS (Manual de Rendimientos 2003-11) | 94 | 181 | 02, 03, 04, 05, 07, 08, 09, 22, 26, 31, 32 |
| Suárez Salazar | 0 | 0 | NO_VERIFICADO |
| CYPE Honduras | 0 | 0 | NO_VERIFICADO |

Precios intactos: invariante SHA256 `ef3552d0...3382` (5 tablas, 8938 filas)
idéntico antes/después (ver `data/precios_snapshot_*.json`).

## Pipeline (orden de ejecución)

```
snapshot_precios.py                 # paso 1: hash invariante de precios
parse_fhis_fichas.py                # paso 2-3: parseo PDF FHIS -> fichas_fhis_parseadas.csv/json + staging .db
crawl_cype.py / analyze_cype_*.py   # intentos CYPE (SPA -> NO_VERIFICADO)
extract_suarez_miguelgarcia.py      # intento Suárez (rechazado, ver bitácora)
crosswalk_fichas_catalogo.py        # paso 4: cruce fichas FHIS <-> catálogo
populate_fhis_audit.py              # paso 5: INSERT OR IGNORE en rendimiento_audit
generate_output.py                  # salida final CSV/MD rendimientos_auditados
cleanup_suarez_no_verificado.py     # corrección: retira filas suárez no verificadas
snapshot_precios.py                 # re-verificación: invariante sin cambios
final_check.py / check_*.py         # validaciones de cierre
```

Todos los scripts corren con `D:\LLM\python\python.exe`.

## Corrección sobre la sesión anterior

La sesión inicial insertó 10 filas SUAREZ_SALAZAR extraídas de
`http://miguelgarcia.xyz/rendimientos/` (web personal que republica tablas del
libro). Esas filas **no** cumplen el contrato (fuente no autorizada, sin
página/tabla del libro) y fueron **retiradas** de la tabla canónica
(`cleanup_suarez_no_verificado.py`). Rollback: `data/suarez_rows_retiradas.json`.
El material fuente del intento se conserva en `data/downloads/` como evidencia.

## Tests

```
D:\LLM\python\python.exe -m pytest pipeline/tests -q
```

Cubren: parser FHIS (fixtures pequeños), parser de filas Suárez y
migración/idempotencia (UNIQUE + INSERT OR IGNORE sobre BD temporal).

## Archivos clave

- `data/rendimientos_auditados.csv` / `.md` — salida final obligatoria (solo rendimientos, sin precios)
- `data/bitacora_fuentes_no_encontradas.md` — bitácora de fuentes no auditadas + cobertura
- `data/precios_snapshot_latest.json` — invariante de precios
- `data/fichas_fhis_parseadas.csv/json` — extracción FHIS completa
- `data/downloads/` — evidencia de fuentes (PDFs FHIS, HTMLs CYPE, HTML/PDF Suárez)

> El PDF del libro de Suárez (43 MB, escaneado) NO se versiona en git
> (material con copyright; se registran URL y SHA256 en la bitácora y la BD).