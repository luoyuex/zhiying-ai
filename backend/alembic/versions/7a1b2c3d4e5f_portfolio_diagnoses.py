"""portfolio_diagnoses

Revision ID: 7a1b2c3d4e5f
Revises: f6a7b8c9d0e1
Create Date: 2026-10-23 10:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '7a1b2c3d4e5f'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'portfolio_diagnoses',
        sa.Column(
            'id',
            sa.Uuid(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('health_score', sa.Integer(), nullable=False),
        sa.Column('position_count', sa.Integer(), nullable=False),
        sa.Column('summary', sa.String(length=400), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_portfolio_diagnoses_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_portfolio_diagnoses')),
    )
    op.create_index(
        op.f('ix_portfolio_diagnoses_created_at'),
        'portfolio_diagnoses',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_portfolio_diagnoses_user_id'),
        'portfolio_diagnoses',
        ['user_id'],
        unique=False,
    )
    op.create_index(
        'ix_portfolio_diagnoses_user_created',
        'portfolio_diagnoses',
        ['user_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_portfolio_diagnoses_user_created', table_name='portfolio_diagnoses')
    op.drop_index(op.f('ix_portfolio_diagnoses_user_id'), table_name='portfolio_diagnoses')
    op.drop_index(op.f('ix_portfolio_diagnoses_created_at'), table_name='portfolio_diagnoses')
    op.drop_table('portfolio_diagnoses')
