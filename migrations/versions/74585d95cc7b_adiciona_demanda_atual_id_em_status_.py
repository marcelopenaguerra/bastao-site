"""adiciona demanda_atual_id em status_colaborador

Revision ID: 74585d95cc7b
Revises: df3a921b07c8
Create Date: 2026-07-08 21:59:38.361260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74585d95cc7b'
down_revision: Union[str, Sequence[str], None] = 'df3a921b07c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch mode: permite ALTER TABLE com constraint tanto em SQLite (dev/testes,
    # via copy-and-move) quanto em Postgres (produção, via ALTER direto).
    with op.batch_alter_table('status_colaborador') as batch_op:
        batch_op.add_column(sa.Column('demanda_atual_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_status_colaborador_demanda_atual_id', 'demandas', ['demanda_atual_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('status_colaborador') as batch_op:
        batch_op.drop_constraint('fk_status_colaborador_demanda_atual_id', type_='foreignkey')
        batch_op.drop_column('demanda_atual_id')
