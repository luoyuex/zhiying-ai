"""user automation settings run time columns

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-23 10:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'user_automation_settings',
        sa.Column('screener_run_hour', sa.Integer(), server_default=sa.text('17'), nullable=False),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('screener_run_minute', sa.Integer(), server_default=sa.text('35'), nullable=False),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('analysis_run_hour', sa.Integer(), server_default=sa.text('17'), nullable=False),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('analysis_run_minute', sa.Integer(), server_default=sa.text('35'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_automation_settings', 'analysis_run_minute')
    op.drop_column('user_automation_settings', 'analysis_run_hour')
    op.drop_column('user_automation_settings', 'screener_run_minute')
    op.drop_column('user_automation_settings', 'screener_run_hour')
