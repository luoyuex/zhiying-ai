"""user automation settings

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-23 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_automation_settings',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('screener_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('analysis_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('strategy_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_user_automation_settings_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_automation_settings')),
    )
    op.create_index(
        op.f('ix_user_automation_settings_user_id'),
        'user_automation_settings',
        ['user_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_automation_settings_user_id'), table_name='user_automation_settings')
    op.drop_table('user_automation_settings')
