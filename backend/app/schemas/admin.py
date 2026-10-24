"""后台管理接口模型。"""

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class AdminUserCounts(BaseModel):
    reports: int = 0
    reports_7d: int = 0
    screener_records: int = 0
    portfolio_diagnoses: int = 0
    watchlist_items: int = 0


class AdminAutomationSummary(BaseModel):
    screener_enabled: bool = False
    analysis_enabled: bool = False
    screener_run_hour: int = 17
    screener_run_minute: int = 35
    analysis_run_hour: int = 17
    analysis_run_minute: int = 35
    enabled_strategies: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AdminRecentReport(BaseModel):
    id: UUID
    symbol: str
    name: str
    rating: str
    confidence: int
    created_at: datetime


class AdminUserListItem(BaseModel):
    id: UUID
    email: EmailStr
    nickname: str
    role: str
    status: str
    daily_analysis_quota: int
    effective_quota: int
    quota_override_active: bool
    today_used: int = 0
    reports_7d: int = 0
    created_at: datetime
    last_login_at: datetime | None = None


class AdminUserDetail(BaseModel):
    id: UUID
    email: EmailStr
    nickname: str
    role: str
    status: str
    email_verified_at: datetime | None = None
    daily_analysis_quota: int
    effective_quota: int
    quota_override_active: bool
    today_used: int = 0
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    counts: AdminUserCounts
    automation: AdminAutomationSummary
    recent_reports: list[AdminRecentReport] = Field(default_factory=list)


class AdminUserUpdate(BaseModel):
    daily_analysis_quota: int | None = Field(default=None, ge=0, le=100)
    status: Literal["active", "banned"] | None = None


class AdminSessionItem(BaseModel):
    id: UUID
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    active: bool


class AdminResetQuotaResponse(BaseModel):
    ok: bool = True
    message: str
    used_before: int = 0


class AdminRevokeSessionsResponse(BaseModel):
    ok: bool = True
    revoked: int = 0
    message: str


class AdminTopQuotaUser(BaseModel):
    user_id: UUID
    email: EmailStr
    nickname: str
    used: int
    quota: int


class AdminRecentFailure(BaseModel):
    job_id: str
    kind: str
    user_email: str | None = None
    symbol: str | None = None
    strategy: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class AdminOverview(BaseModel):
    range: str
    since: datetime
    data_since: datetime | None = None
    new_users: int = 0
    active_users: int = 0
    jobs_total: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    success_rate: float | None = None
    tokens_total: int = 0
    cost_estimate: float = 0
    worker_alive: bool = False
    queue_depth: int = 0
    running_jobs: int = 0
    open_circuits: int = 0
    proxy_total: int = 0
    proxy_healthy: int = 0
    quota_override_active: bool = False
    top_quota_users: list[AdminTopQuotaUser] = Field(default_factory=list)
    recent_failures: list[AdminRecentFailure] = Field(default_factory=list)


class AdminAuditLogItem(BaseModel):
    id: int
    created_at: datetime
    admin_email: str | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    result: str
    ip: str | None = None
    ua: str | None = None
    note: str | None = None
