# legacy_scripts — Registro de código reemplazado

## Regla

Todo código que se **REEMPLACE** en este repo (bloques, funciones o archivos completos que se
quiten o se sustituyan por una versión nueva) se copia primero aquí, a
`legacy_scripts/<YYYYMMDD>_<nombre-original>`, ANTES de borrarlo/sobrescribirlo en su ubicación
real. Después se registra una entrada en este archivo (abajo) con:

- **Qué era** — descripción corta de qué hacía el código movido.
- **Fecha** — YYYYMMDD del reemplazo.
- **Por qué se reemplazó** — motivo (bug, refactor, feature que lo vuelve obsoleto, etc.).
- **Qué lo reemplaza ahora** — ruta/archivo/función nueva, y quién/qué sesión lo hizo.

Esto NO es un archivo de backups de BD (para eso está `C:\EstimaStruct\backups\`, ver
`docs/mapa_sql_inyeccion_bd.md`) — es específicamente para **código fuente** (`.py`, `.js`,
`.html`, `.ps1`, etc.) que se reemplaza durante el desarrollo, para poder recuperar el
comportamiento anterior sin tener que bucear en el historial de git (útil sobre todo en sesiones
donde el working tree tiene cambios sin commitear de otras tareas en paralelo, y no se quiere
depender de `git log`/`git show` para reconstruir una versión vieja).

Si una tarea resulta **100% aditiva** (solo agrega código nuevo, no quita ni sustituye nada
existente), no hay nada que mover aquí — pero la carpeta y este archivo deben existir igual, con
una entrada que lo aclare (como la de abajo), para que la próxima sesión que sí reemplace algo
tenga el patrón ya establecido y lo siga.

---

## Registro

### 2026-07-16 — Convención inicial (sin código movido — feature aditiva)

- **Qué era:** N/A — esta entrada no mueve ningún archivo. Es la creación del patrón
  `legacy_scripts/` en sí, como parte de la tarea "botón de copia de BD (export/import ZIP) +
  mapa SQL + patrón legacy_scripts" en EstimaStruct.
- **Fecha:** 2026-07-16.
- **Por qué:** la tarea pedía instaurar este patrón para reemplazos futuros. La implementación de
  esa misma tarea (`backend/routers/db_backup.py`, `backend/db.py::dispose_engine()`,
  `backend/main.py` (registro de router), `frontend/js/db-backup.js`, botones e input nuevo en
  `ESTIMASTRUCT/templates/index.html`, `docs/mapa_sql_inyeccion_bd.md`) fue **100% aditiva** — no
  se borró ni se sobrescribió ninguna función, bloque o archivo existente. No había nada que
  mover a `legacy_scripts/`.
- **Qué lo reemplaza ahora:** N/A (nada fue reemplazado). Ver arriba la lista de archivos
  nuevos/tocados de forma aditiva.

<!--
Plantilla para la próxima entrada (copiar y completar):

### YYYYMMDD — <nombre corto del reemplazo>

- **Qué era:** <descripción de lo que hacía el código movido a legacy_scripts/YYYYMMDD_<nombre>>
- **Fecha:** YYYYMMDD
- **Por qué se reemplazó:** <motivo>
- **Qué lo reemplaza ahora:** <archivo/función nueva + referencia a la tarea/sesión>
-->
