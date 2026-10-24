"""p6: rating change columns, position change logs, price alerts

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-24 23:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'analysis_reports',
        sa.Column('rating_change', sa.String(length=8), nullable=True),
    )
    op.add_column(
        'analysis_reports',
        sa.Column('prev_rating', sa.String(length=8), nullable=True),
    )

    op.create_table(
        'position_change_logs',
        sa.Column(
            'id',
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'user_id',
            sa.Uuid(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('symbol', sa.String(length=6), nullable=False),
        sa.Column('old_cost_price', sa.Numeric(12, 3), nullable=True),
        sa.Column('new_cost_price', sa.Numeric(12, 3), nullable=True),
        sa.Column('old_quantity', sa.Integer(), nullable=True),
        sa.Column('new_quantity', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_position_change_logs_user_symbol_created',
        'position_change_logs',
        ['user_id', 'symbol', 'created_at'],
    )

    op.create_table(
        'price_alerts',
        sa.Column(
            'id',
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'user_id',
            sa.Uuid(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('symbol', sa.String(length=6), nullable=False),
        sa.Column('name', sa.String(length=64), server_default='', nullable=False),
        sa.Column('direction', sa.String(length=8), nullable=False),
        sa.Column('target_price', sa.Numeric(12, 3), nullable=False),
        sa.Column(
            'status', sa.String(length=12), server_default='active', nullable=False
        ),
        sa.Column('triggered_price', sa.Numeric(12, 3), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_price_alerts_user_status', 'price_alerts', ['user_id', 'status']
    )
    op.create_index('ix_price_alerts_symbol_status', 'price_alerts', ['symbol', 'status'])


def downgrade() -> None:
    op.drop_index('ix_price_alerts_symbol_status', table_name='price_alerts')
    op.drop_index('ix_price_alerts_user_status', table_name='price_alerts')
    op.drop_table('price_alerts')
    op.drop_index(
        'ix_position_change_logs_user_symbol_created', table_name='position_change_logs'
    )
    op.drop_table('position_change_logs')
    op.drop_column('analysis_reports', 'prev_rating')
    op.drop_column('analysis_reports', 'rating_change')
