# EstimaStruct SQLite v1.4

`estimacion.db` es el snapshot SQLite canónico y versionado de la release v1.4.

- `PRAGMA user_version = 14`.
- `rendimiento_audit`: 257 filas (181 FHIS, 76 CYPE_HN, 0 Suárez Salazar).
- Suárez Salazar permanece `NO_VERIFICADO` y no tiene filas publicadas.
- El backend operativo puede seguir usando `ESTIMA_DB_PATH`; los gates fijan esa
  variable a este snapshot para demostrar el wiring de la release.
- No editar el binario manualmente. Cualquier futura promoción debe volver a
  demostrar el hash semántico de precios antes/después.

La evidencia reproducible se genera con:

```powershell
& 'D:\LLM\python\python.exe' release\validate_v14_release.py
```
