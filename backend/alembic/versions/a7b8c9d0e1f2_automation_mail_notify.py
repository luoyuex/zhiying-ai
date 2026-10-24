"""user automation settings email notification columns

Revision ID: a7b8c9d0e1f2
Revises: 8b2c3d4e5f60
Create Date: 2026-10-24 16:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = '8b2c3d4e5f60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'user_automation_settings',
        sa.Column(
            'email_notify_enabled',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('notify_email', sa.String(length=254), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_automation_settings', 'notify_email')
    op.drop_column('user_automation_settings', 'email_notify_enabled')
