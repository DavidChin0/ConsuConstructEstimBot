"""reajuste de materiales por obra (config_presupuesto)

[2026-10-02 David] Obra Camilo: MO de v1.3 correcta, materiales subieron y el
contrato no se renegocia. Se agrega un % de reajuste aplicado SOLO a insumos
MATERIAL + un valor objetivo (contrato) para recalcular el % automáticamente.
ADITIVA: 2 columnas nullable/default 0; ninguna obra cambia de valor.

ESCRITA A MANO (ver nota en 7f3e9c1a2b4d: no usar --autogenerate).

Revision ID: a8d41c2e7b90
Revises: 7f3e9c1a2b4d
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a8d41c2e7b90"
down_revision: Union[str, Sequence[str], None] = "7f3e9c1a2b4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("config_presupuesto",
                  sa.Column("reajuste_materiales", sa.Numeric(9, 4), nullable=True, server_default="0"))
    op.add_column("config_presupuesto",
                  sa.Column("valor_objetivo", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("config_presupuesto", "valor_objetivo")
    op.drop_column("config_presupuesto", "reajuste_materiales")
