"""financiero: schema propio + financiero_item / financiero_calculo

Módulo Financiero (cédula de indirectos auditable) — goal-21080.

ESCRITA A MANO a propósito. NO usar `alembic revision --autogenerate` para
regenerarla: el schema public de la BD Postgres de EstimaStruct tiene tablas
(arch_chunks, assistant_sessions, assistant_messages, csi_codes,
csi_embeddings) y un schema `rag` que NO están en models.py; autogenerate los
vería como sobrantes y emitiría DROP por ellos. (env.py tiene además un filtro
`include_object` como red de seguridad, pero esta migración no depende de él.)

Decisión David: las 2 tablas del módulo viven en un SCHEMA NUEVO Y SEPARADO
`financiero`, no en public. Sólo aplica en Postgres — en SQLite el backend usa
create_all (AUTO_CREATE_SCHEMA) y los schemas nombrados no existen, así que la
migración es no-op fuera de Postgres.

PRERREQUISITO: la tabla public.presupuesto debe existir en la BD Postgres antes
de aplicar esta migración (las 2 tablas tienen FK → presupuesto.id con ON
DELETE CASCADE, cross-schema financiero→public). En el estado split-brain
actual (Postgres stale, core aún en SQLite) eso significa que la migración
SQLite→Postgres del core debe correr ANTES. Si presupuesto no existe, esta
migración falla limpio en la creación de la FK sin dejar a medias (todo en una
transacción).

Revision ID: 7f3e9c1a2b4d
Revises: 606c3f3a7b6b
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f3e9c1a2b4d"
down_revision: Union[str, Sequence[str], None] = "606c3f3a7b6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "financiero"

# Espejo de models.TIPOS_FINANCIERO_ITEM / BASES_CALCULO_FINANCIERO — si cambian
# en el modelo, actualizar aquí (los CHECK son parte del contrato de la tabla).
_TIPOS = ("IMPREVISTO", "SEGURO", "FIANZA", "ADMINISTRACION",
          "UTILIDAD", "IMPUESTO", "ESCALAMIENTO", "OTRO")
_BASES = ("COSTO_DIRECTO", "SUBTOTAL_ACUMULADO", "MONTO_FIJO")


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite (dev): el backend crea estas tablas vía Base.metadata.create_all
        # en el schema default. Este módulo no aplica fuera de Postgres.
        return

    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    tipos_sql = ", ".join(f"'{t}'" for t in _TIPOS)
    bases_sql = ", ".join(f"'{b}'" for b in _BASES)

    op.create_table(
        "financiero_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("presupuesto_id", sa.String(length=36), nullable=False),
        sa.Column("categoria_icms", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("base_calculo", sa.Text(), nullable=False),
        sa.Column("porcentaje", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("monto_fijo", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("obligatorio", sa.Boolean(), nullable=True),
        sa.Column("evidencia", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(f"tipo IN ({tipos_sql})", name="ck_financiero_item_tipo"),
        sa.CheckConstraint(f"base_calculo IN ({bases_sql})", name="ck_financiero_item_base"),
        # FK cross-schema financiero → public.presupuesto (search_path resuelve
        # `presupuesto` a public). ON DELETE CASCADE espeja el modelo.
        sa.ForeignKeyConstraint(["presupuesto_id"], ["presupuesto.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_financiero_item_presupuesto_id",
        "financiero_item",
        ["presupuesto_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "financiero_calculo",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("presupuesto_id", sa.String(length=36), nullable=False),
        sa.Column("costo_directo", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("iva_pct", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("items_json", sa.Text(), nullable=True),
        sa.Column("subtotal_antes_iva", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("iva_monto", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("total_general", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("generado_at", sa.DateTime(), nullable=True),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["presupuesto_id"], ["presupuesto.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_financiero_calculo_presupuesto_id",
        "financiero_calculo",
        ["presupuesto_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    op.drop_index("ix_financiero_calculo_presupuesto_id", table_name="financiero_calculo", schema=SCHEMA)
    op.drop_table("financiero_calculo", schema=SCHEMA)
    op.drop_index("ix_financiero_item_presupuesto_id", table_name="financiero_item", schema=SCHEMA)
    op.drop_table("financiero_item", schema=SCHEMA)
    # Sólo borra el schema si quedó vacío — nunca CASCADE (no arrastrar nada ajeno).
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} RESTRICT")
