"""watchlist sort order

Revision ID: a3b4c5d6e7f8
Revises: e1f2a3b4c5d6
Create Date: 2026-10-28 11:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3b4c5d6e7f8'
down_revision: str | None = 'e1f2a3b4c5d6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'watchlist_items',
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
    )
    # 回填：沿用改造前的展示顺序（同一用户按加入时间倒序）
    op.execute(
        """
        UPDATE watchlist_items AS w
        SET sort_order = ranked.rn
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY user_id ORDER BY created_at DESC, symbol
            ) - 1 AS rn
            FROM watchlist_items
        ) AS ranked
        WHERE w.id = ranked.id
        """
    )
    op.create_index(
        'ix_watchlist_items_user_sort',
        'watchlist_items',
        ['user_id', 'sort_order'],
    )


def downgrade() -> None:
    op.drop_index('ix_watchlist_items_user_sort', table_name='watchlist_items')
    op.drop_column('watchlist_items', 'sort_order')
