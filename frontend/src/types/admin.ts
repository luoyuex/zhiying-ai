export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AdminUserCounts {
  reports: number
  reports_7d: number
  screener_records: number
  portfolio_diagnoses: number
  watchlist_items: number
}

export interface AdminAutomationSummary {
  screener_enabled: boolean
  analysis_enabled: boolean
  screener_run_hour: number
  screener_run_minute: number
  analysis_run_hour: number
  analysis_run_minute: number
  enabled_strategies: string[]
  updated_at: string | null
}

export interface AdminRecentReport {
  id: string
  symbol: string
  name: string
  rating: string
  confidence: number
  created_at: string
}

export interface AdminUserListItem {
  id: string
  email: string
  nickname: string
  role: string
  status: string
  daily_analysis_quota: number
  effective_quota: number
  quota_override_active: boolean
  today_used: number
  reports_7d: number
  created_at: string
  last_login_at: string | null
}

export interface AdminUserDetail {
  id: string
  email: string
  nickname: string
  role: string
  status: string
  email_verified_at: string | null
  daily_analysis_quota: number
  effective_quota: number
  quota_override_active: boolean
  today_used: number
  created_at: string
  updated_at: string
  last_login_at: string | null
  counts: AdminUserCounts
  automation: AdminAutomationSummary
  recent_reports: AdminRecentReport[]
}

export interface AdminUserUpdate {
  daily_analysis_quota?: number
  status?: 'active' | 'banned'
}

export interface AdminSessionItem {
  id: string
  ip: string | null
  user_agent: string | null
  created_at: string
  expires_at: string
  revoked_at: string | null
  active: boolean
}

export interface AdminResetQuotaResponse {
  ok: boolean
  message: string
  used_before: number
}

export interface AdminRevokeSessionsResponse {
  ok: boolean
  revoked: number
  message: string
}

export interface AdminTopQuotaUser {
  user_id: string
  email: string
  nickname: string
  used: number
  quota: number
}

export interface AdminRecentFailure {
  job_id: string
  kind: string
  user_email: string | null
  symbol: string | null
  strategy: string | null
  error_code: string | null
  error_message: string | null
  created_at: string
}

export interface AdminOverview {
  range: string
  since: string
  data_since: string | null
  new_users: number
  active_users: number
  jobs_total: number
  jobs_succeeded: number
  jobs_failed: number
  success_rate: number | null
  tokens_total: number
  cost_estimate: number
  worker_alive: boolean
  queue_depth: number
  running_jobs: number
  open_circuits: number
  proxy_total: number
  proxy_healthy: number
  quota_override_active: boolean
  top_quota_users: AdminTopQuotaUser[]
  recent_failures: AdminRecentFailure[]
}

export interface AdminAuditLogItem {
  id: number
  created_at: string
  admin_email: string | null
  action: string
  target_type: string | null
  target_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  result: string
  ip: string | null
  ua: string | null
  note: string | null
}
