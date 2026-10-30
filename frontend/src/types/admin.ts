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

export interface AdminQuotaPolicy {
  default_daily_quota: number
  override_active: boolean
  override_value: number
}

export interface AdminQuotaPolicyUpdate {
  default_daily_quota: number
  apply_to_existing?: boolean
}

export interface AdminQuotaPolicyResult extends AdminQuotaPolicy {
  updated_users: number
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
  unpriced_calls: number
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

export interface AdminCostUser {
  user_id: string | null
  email: string
  calls: number
  tokens: number
  cost: number
}

export interface AdminCostTask {
  task: string
  calls: number
  tokens: number
  cost: number
}

export interface AdminCostDaily {
  date: string
  calls: number
  failures: number
  tokens: number
  cost: number
}

export interface AdminCostSummary {
  days: number
  since: string
  calls: number
  failures: number
  success_rate: number | null
  tokens: number
  cost: number
  unpriced_calls: number
  data_since: string | null
  daily: AdminCostDaily[]
  top_users: AdminCostUser[]
  top_tasks: AdminCostTask[]
}

export interface AdminCostCallItem {
  id: number
  created_at: string
  user_id: string | null
  user_email: string | null
  job_id: string | null
  task: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  duration_ms: number
  status: string
  error_code: string | null
  finish_reason: string | null
  cost: number | null
}

export interface AdminJobItem {
  id: string
  kind: string
  user_id: string
  user_email: string | null
  symbol: string | null
  strategy: string | null
  status: string
  phase: string
  trigger: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  token_total: number
  error_code: string | null
  error_message: string | null
  report_id: string | null
  record_id: string | null
}

export interface AdminJobDetail extends AdminJobItem {
  meta: Record<string, unknown> | null
}

export interface AdminJobRetryResponse {
  ok: boolean
  job_id: string
  status: string
  message: string
}

export interface AdminAutomationRunItem {
  id: number
  run_date: string
  user_id: string
  user_email: string | null
  line: string
  status: string
  enqueued: number
  reason: string | null
  created_at: string
}

export interface AdminContentReportItem {
  id: string
  user_id: string
  user_email: string | null
  symbol: string
  name: string
  rating: string
  confidence: number
  rating_change: string | null
  prev_rating: string | null
  decision_source: string
  created_at: string
}

export interface AdminContentReportDetail extends AdminContentReportItem {
  // 管理员只读页按需渲染，结构随报告版本变化
  report: Record<string, any>
}

export interface AdminContentScreenerPick {
  rank: number
  symbol: string
  name: string
}

export interface AdminContentScreenerItem {
  id: string
  user_id: string
  user_email: string | null
  strategy: string
  analyzed_count: number
  recommendation_count: number
  model: string
  picks: AdminContentScreenerPick[]
  created_at: string
}

export interface AdminContentScreenerDetail extends AdminContentScreenerItem {
  filters: Record<string, any>
  result: Record<string, any>
}

export interface AdminContentPortfolioItem {
  id: string
  user_id: string
  user_email: string | null
  health_score: number
  position_count: number
  summary: string
  created_at: string
}

export interface AdminContentPortfolioDetail extends AdminContentPortfolioItem {
  model: string
  report: Record<string, any>
}

export interface AdminContentWatchlistItem {
  id: string
  user_id: string
  user_email: string | null
  symbol: string
  name: string
  note: string
  cost_price: number | null
  quantity: number | null
  created_at: string
}
