# ⚠️ REPO VIEJO — NO USAR

**Este directorio (`D:/GitHub/ConsuConstructEstimBot/ESTIMASTRUCT`) es un MIRROR DESACTUALIZADO.**

**Repo canónico / LIVE (el que carga el backend :8002):**
`D:/GitHub/ConsuConstructEstimBot/EstimBot/ConsuConstructEstimBot/ESTIMASTRUCT`

## Por qué existe esta nota (2026-10-09)

estimbot pusheó por error 2 commits de documentación a este mirror en vez
del repo canon. Mismo `origin` remoto pero historial divergente del canon
(ADR-018 Postgres-único vivía SOLO en el canon, no acá). Se resolvió con
`git merge origin/main` desde el canon — ambos quedaron sincronizados en
`origin/main`, pero el canon sigue siendo la fuente de trabajo.

## Regla

- **Nunca editar ni commitear desde aquí.** Cualquier cambio se hace en
  el repo canon arriba.
- Si un fix "no surte efecto": probablemente se editó este mirror por error.
- Confirmar siempre con `git rev-parse --show-toplevel` antes de escribir.
