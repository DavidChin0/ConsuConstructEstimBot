"""add_rendimiento_audit_table_v14

Tabla comparativa de rendimientos auditados (FHIS, CYPE_HN, SUAREZ_SALAZAR).
v1.4 canon — no toca tablas de precios/partidas.

Revision ID: 01af8510cf23
Revises: 7f3e9c1a2b4d
Create Date: 2026-08-20 20:43:08.718950

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01af8510cf23'
down_revision: Union[str, Sequence[str], None] = '7f3e9c1a2b4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite (dev/canon): la tabla ya existe y fue creada por los scripts
        # de auditoría (populate_fhis_audit.py, populate_cype_audit.py) con el
        # esquema correcto. create_all en el backend también la crea.
        # No hacemos ALTER en SQLite (sintaxis limitada).
        return

    # PostgreSQL: crear la tabla con el esquema completo
    op.create_table(
        'rendimiento_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('partida_id', sa.String(length=36), nullable=True),
        sa.Column('partida_clave_csi', sa.Text(), nullable=False),
        sa.Column('partida_descripcion', sa.Text(), nullable=False),
        sa.Column('partida_unidad', sa.Text(), nullable=False),
        sa.Column('fuente', sa.Text(), nullable=False),
        sa.Column('fuente_edicion', sa.Text(), nullable=True),
        sa.Column('fuente_codigo', sa.Text(), nullable=True),
        sa.Column('fuente_url', sa.Text(), nullable=False),
        sa.Column('fuente_pagina', sa.Text(), nullable=True),
        sa.Column('fecha_consulta', sa.Text(), nullable=False),
        sa.Column('recurso_tipo', sa.Text(), nullable=False),
        sa.Column('recurso_descripcion', sa.Text(), nullable=False),
        sa.Column('coeficiente_nativo', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('unidad_nativa', sa.Text(), nullable=False),
        sa.Column('coeficiente_normalizado', sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column('formula_conversion', sa.Text(), nullable=True),
        sa.Column('tipo_match', sa.Text(), nullable=False),
        sa.Column('confianza', sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column('evidencia', sa.Text(), nullable=True),
        sa.Column('condiciones_alcance', sa.Text(), nullable=True),
        sa.Column('hash_insumo', sa.Text(), nullable=True),
        sa.Column('notas_discrepancia', sa.Text(), nullable=True),
        sa.CheckConstraint("fuente IN ('FHIS', 'CYPE_HN', 'SUAREZ_SALAZAR')", name='ck_rendimiento_audit_fuente'),
        sa.CheckConstraint("recurso_tipo IN ('MANO_OBRA', 'MAQUINARIA', 'EQUIPO')", name='ck_rendimiento_audit_recurso'),
        sa.CheckConstraint("tipo_match IN ('exacto', 'semantico', 'manual')", name='ck_rendimiento_audit_match'),
        sa.ForeignKeyConstraint(['partida_id'], ['partida.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rendimiento_audit_partida_id', 'rendimiento_audit', ['partida_id'], unique=False)


def downgrade() -> None:
    if not _is_postgres():
        return

    op.drop_index('ix_rendimiento_audit_partida_id', table_name='rendimiento_audit')
    op.drop_table('rendimiento_audit')