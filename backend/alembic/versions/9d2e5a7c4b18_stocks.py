"""stocks

Revision ID: 9d2e5a7c4b18
Revises: b7c141587d1f
Create Date: 2026-10-21 15:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9d2e5a7c4b18'
down_revision: str | None = 'b7c141587d1f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'stocks',
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('exchange', sa.String(length=2), nullable=False),
        sa.Column('pinyin', sa.String(length=64), nullable=False),
        sa.Column('abbr', sa.String(length=16), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('code', name=op.f('pk_stocks')),
    )
    op.create_index(op.f('ix_stocks_abbr'), 'stocks', ['abbr'], unique=False)
    op.create_index(op.f('ix_stocks_pinyin'), 'stocks', ['pinyin'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_stocks_pinyin'), table_name='stocks')
    op.drop_index(op.f('ix_stocks_abbr'), table_name='stocks')
    op.drop_table('stocks')
