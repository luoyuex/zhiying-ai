"""webhook notify, avatar and alert kind

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-25 11:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e1f2a3b4c5d6'
down_revision: str | None = 'd0e1f2a3b4c5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 通知渠道：定时汇总与价位提醒各自有 Webhook 开关，共用类型/地址/关键词
    op.add_column(
        'user_automation_settings',
        sa.Column(
            'webhook_notify_enabled',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column(
            'price_alert_webhook_enabled',
            sa.Boolean(),
            server_default=sa.text('true'),
            nullable=False,
        ),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column(
            'webhook_type',
            sa.String(length=16),
            server_default=sa.text("'dingtalk'"),
            nullable=False,
        ),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('webhook_url', sa.String(length=512), nullable=True),
    )
    op.add_column(
        'user_automation_settings',
        sa.Column('webhook_keyword', sa.String(length=64), nullable=True),
    )

    # 价位提醒类型：custom / entry / take_profit / stop_loss，可关联报告
    op.add_column(
        'price_alerts',
        sa.Column(
            'kind',
            sa.String(length=16),
            server_default=sa.text("'custom'"),
            nullable=False,
        ),
    )
    op.add_column(
        'price_alerts',
        sa.Column('report_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f('fk_price_alerts_report_id_analysis_reports'),
        'price_alerts',
        'analysis_reports',
        ['report_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_price_alerts_report_id'),
        'price_alerts',
        ['report_id'],
        unique=False,
    )

    # 头像：版本号用于 URL 缓存刷新，图片二进制单独存表
    op.add_column(
        'users',
        sa.Column(
            'avatar_version',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
    )
    op.create_table(
        'user_avatars',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('content_type', sa.String(length=32), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_user_avatars_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_user_avatars')),
    )


def downgrade() -> None:
    op.drop_table('user_avatars')
    op.drop_column('users', 'avatar_version')

    op.drop_index(op.f('ix_price_alerts_report_id'), table_name='price_alerts')
    op.drop_constraint(
        op.f('fk_price_alerts_report_id_analysis_reports'),
        'price_alerts',
        type_='foreignkey',
    )
    op.drop_column('price_alerts', 'report_id')
    op.drop_column('price_alerts', 'kind')

    op.drop_column('user_automation_settings', 'webhook_keyword')
    op.drop_column('user_automation_settings', 'webhook_url')
    op.drop_column('user_automation_settings', 'webhook_type')
    op.drop_column('user_automation_settings', 'price_alert_webhook_enabled')
    op.drop_column('user_automation_settings', 'webhook_notify_enabled')
