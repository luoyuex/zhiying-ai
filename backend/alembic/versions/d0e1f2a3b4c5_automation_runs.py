"""admin automation runs: per-user daily execution log

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-25 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: str | None = 'c9d0e1f2a3b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'automation_runs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column(
            'user_id',
            sa.Uuid(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('line', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column(
            'enqueued', sa.Integer(), server_default='0', nullable=False
        ),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint(
            'run_date', 'user_id', 'line', name='uq_automation_runs_day_user_line'
        ),
    )
    op.create_index(
        'ix_automation_runs_user_date', 'automation_runs', ['user_id', 'run_date']
    )
    op.create_index(
        'ix_automation_runs_date_status', 'automation_runs', ['run_date', 'status']
    )


def downgrade() -> None:
    op.drop_index('ix_automation_runs_date_status', table_name='automation_runs')
    op.drop_index('ix_automation_runs_user_date', table_name='automation_runs')
    op.drop_table('automation_runs')
