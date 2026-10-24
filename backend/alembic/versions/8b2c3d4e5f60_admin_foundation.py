"""admin foundation: llm_calls, ai_jobs, admin_audit_logs

Revision ID: 8b2c3d4e5f60
Revises: 7a1b2c3d4e5f
Create Date: 2026-10-24 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '8b2c3d4e5f60'
down_revision: str | None = '7a1b2c3d4e5f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'llm_calls',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('job_id', sa.String(length=32), nullable=True),
        sa.Column('task', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('completion_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('duration_ms', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_code', sa.String(length=32), nullable=True),
        sa.Column('finish_reason', sa.String(length=24), nullable=True),
        sa.Column('cost', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_llm_calls_user_id_users'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_llm_calls')),
    )
    op.create_index(
        op.f('ix_llm_calls_created_at'), 'llm_calls', ['created_at'], unique=False
    )
    op.create_index(
        'ix_llm_calls_user_created', 'llm_calls', ['user_id', 'created_at'], unique=False
    )
    op.create_index(
        'ix_llm_calls_task_created', 'llm_calls', ['task', 'created_at'], unique=False
    )
    op.create_index(
        'ix_llm_calls_job_id', 'llm_calls', ['job_id'], unique=False
    )

    op.create_table(
        'ai_jobs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('symbol', sa.String(length=12), nullable=True),
        sa.Column('strategy', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('phase', sa.String(length=64), server_default='', nullable=False),
        sa.Column(
            'trigger', sa.String(length=16), server_default='manual', nullable=False
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('token_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('report_id', sa.Uuid(), nullable=True),
        sa.Column('record_id', sa.Uuid(), nullable=True),
        sa.Column('error_code', sa.String(length=32), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'meta',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_ai_jobs_user_id_users'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_jobs')),
    )
    op.create_index(op.f('ix_ai_jobs_created_at'), 'ai_jobs', ['created_at'], unique=False)
    op.create_index(
        'ix_ai_jobs_user_created', 'ai_jobs', ['user_id', 'created_at'], unique=False
    )
    op.create_index(
        'ix_ai_jobs_kind_status_created',
        'ai_jobs',
        ['kind', 'status', 'created_at'],
        unique=False,
    )

    op.create_table(
        'admin_audit_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('admin_user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=True),
        sa.Column('target_id', sa.String(length=64), nullable=True),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result', sa.String(length=16), server_default='success', nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('ua', sa.Text(), nullable=True),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ['admin_user_id'],
            ['users.id'],
            name=op.f('fk_admin_audit_logs_admin_user_id_users'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit_logs')),
    )
    op.create_index(
        op.f('ix_admin_audit_logs_created_at'),
        'admin_audit_logs',
        ['created_at'],
        unique=False,
    )
    op.create_index(
        'ix_admin_audit_logs_target_created',
        'admin_audit_logs',
        ['target_type', 'target_id', 'created_at'],
        unique=False,
    )

    op.create_index(
        'ix_analysis_reports_user_created',
        'analysis_reports',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_screener_records_user_created',
        'screener_records',
        ['user_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_screener_records_user_created', table_name='screener_records')
    op.drop_index('ix_analysis_reports_user_created', table_name='analysis_reports')
    op.drop_index('ix_admin_audit_logs_target_created', table_name='admin_audit_logs')
    op.drop_index(op.f('ix_admin_audit_logs_created_at'), table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
    op.drop_index('ix_ai_jobs_kind_status_created', table_name='ai_jobs')
    op.drop_index('ix_ai_jobs_user_created', table_name='ai_jobs')
    op.drop_index(op.f('ix_ai_jobs_created_at'), table_name='ai_jobs')
    op.drop_table('ai_jobs')
    op.drop_index('ix_llm_calls_job_id', table_name='llm_calls')
    op.drop_index('ix_llm_calls_task_created', table_name='llm_calls')
    op.drop_index('ix_llm_calls_user_created', table_name='llm_calls')
    op.drop_index(op.f('ix_llm_calls_created_at'), table_name='llm_calls')
    op.drop_table('llm_calls')
