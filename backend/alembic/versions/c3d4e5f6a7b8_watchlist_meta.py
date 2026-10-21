"""watchlist metadata

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-21 22:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('watchlist_items', sa.Column('note', sa.String(length=120), nullable=False, server_default=''))
    op.add_column('watchlist_items', sa.Column('cost_price', sa.Numeric(12, 3), nullable=True))
    op.add_column('watchlist_items', sa.Column('quantity', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('watchlist_items', 'quantity')
    op.drop_column('watchlist_items', 'cost_price')
    op.drop_column('watchlist_items', 'note')
