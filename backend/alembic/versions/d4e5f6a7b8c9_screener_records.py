"""screener records

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-22 10:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'screener_records',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('strategy', sa.String(length=32), nullable=False),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('analyzed_count', sa.Integer(), nullable=False),
        sa.Column('recommendation_count', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_screener_records_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_screener_records')),
    )
    op.create_index(op.f('ix_screener_records_created_at'), 'screener_records', ['created_at'], unique=False)
    op.create_index(op.f('ix_screener_records_strategy'), 'screener_records', ['strategy'], unique=False)
    op.create_index(op.f('ix_screener_records_user_id'), 'screener_records', ['user_id'], unique=False)
    op.create_index(
        'ix_screener_records_user_strategy_created',
        'screener_records',
        ['user_id', 'strategy', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_screener_records_user_strategy_created', table_name='screener_records')
    op.drop_index(op.f('ix_screener_records_user_id'), table_name='screener_records')
    op.drop_index(op.f('ix_screener_records_strategy'), table_name='screener_records')
    op.drop_index(op.f('ix_screener_records_created_at'), table_name='screener_records')
    op.drop_table('screener_records')
