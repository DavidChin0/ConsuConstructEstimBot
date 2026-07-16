# Alembic — flujo de migraciones

Baseline `606c3f3a7b6b` = estado actual de la BD viva (stamp, sin drift).

Flujo para cambios de esquema:
1. Editar `models.py`.
2. `python -m alembic revision --autogenerate -m "descripcion"` (desde `backend/`).
3. Revisar el script generado en `alembic/versions/` (autogenerate no es infalible).
4. `python -m alembic upgrade head` para aplicarlo a la BD viva.

Los `migrate_*.py` sueltos en `backend/` quedan como historial, no se tocan.
