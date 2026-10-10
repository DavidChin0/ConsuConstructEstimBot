"""config_presupuesto: cronograma_fecha_arranque (date, null) y cronograma_modo ('paralelo'|'serie').
Escrita a mano (sin autogenerate). NO aplicada: DDL pasa por Reviewer."""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "b3c7e51d9a02"
down_revision: Union[str, Sequence[str], None] = "a8d41c2e7b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("config_presupuesto", sa.Column("cronograma_fecha_arranque", sa.Date(), nullable=True))
    op.add_column("config_presupuesto", sa.Column("cronograma_modo", sa.String(10), nullable=True, server_default="paralelo"))


def downgrade() -> None:
    op.drop_column("config_presupuesto", "cronograma_modo")
    op.drop_column("config_presupuesto", "cronograma_fecha_arranque")
