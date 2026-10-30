import type {
  AdminAuditLogItem,
  AdminAutomationRunItem,
  AdminContentPortfolioDetail,
  AdminContentPortfolioItem,
  AdminContentReportDetail,
  AdminContentReportItem,
  AdminContentScreenerDetail,
  AdminContentScreenerItem,
  AdminContentWatchlistItem,
  AdminCostCallItem,
  AdminCostSummary,
  AdminJobDetail,
  AdminJobItem,
  AdminJobRetryResponse,
  AdminOverview,
  AdminQuotaPolicy,
  AdminQuotaPolicyResult,
  AdminQuotaPolicyUpdate,
  AdminResetQuotaResponse,
  AdminRevokeSessionsResponse,
  AdminSessionItem,
  AdminUserDetail,
  AdminUserListItem,
  AdminUserUpdate,
  Page,
} from '@/types/admin'
import { http } from './client'

export interface AdminUserQuery {
  page?: number
  page_size?: number
  q?: string
  status?: string
  role?: string
  quota_min?: number
  quota_max?: number
  last_login_from?: string
  last_login_to?: string
  sort?: string
  order?: string
}

export interface AdminAuditQuery {
  page?: number
  page_size?: number
  action?: string
  target_type?: string
  target_id?: string
  date_from?: string
  date_to?: string
}

export interface AdminCostCallQuery {
  page?: number
  page_size?: number
  task?: string
  status?: string
  q?: string
  date_from?: string
  date_to?: string
}

export interface AdminJobQuery {
  page?: number
  page_size?: number
  kind?: string
  status?: string
  trigger?: string
  q?: string
  date_from?: string
  date_to?: string
}

export interface AdminAutomationRunQuery {
  page?: number
  page_size?: number
  run_date?: string
  line?: string
  status?: string
  q?: string
}

export interface AdminContentQuery {
  page?: number
  page_size?: number
  q?: string
  symbol?: string
  strategy?: string
  date_from?: string
  date_to?: string
}

export const adminApi = {
  overview(range: 'today' | '7d') {
    return http.get<AdminOverview>('/admin/overview', { params: { range } })
  },

  users(params: AdminUserQuery) {
    return http.get<Page<AdminUserListItem>>('/admin/users', { params })
  },

  quotaPolicy() {
    return http.get<AdminQuotaPolicy>('/admin/quota-policy')
  },

  updateQuotaPolicy(payload: AdminQuotaPolicyUpdate) {
    return http.put<AdminQuotaPolicyResult>('/admin/quota-policy', payload)
  },

  user(id: string) {
    return http.get<AdminUserDetail>(`/admin/users/${encodeURIComponent(id)}`)
  },

  updateUser(id: string, payload: AdminUserUpdate) {
    return http.patch<AdminUserDetail>(
      `/admin/users/${encodeURIComponent(id)}`,
      payload,
    )
  },

  resetQuota(id: string) {
    return http.post<AdminResetQuotaResponse>(
      `/admin/users/${encodeURIComponent(id)}/reset-quota`,
    )
  },

  revokeSessions(id: string) {
    return http.post<AdminRevokeSessionsResponse>(
      `/admin/users/${encodeURIComponent(id)}/revoke-sessions`,
    )
  },

  sessions(id: string, params: { page?: number; page_size?: number }) {
    return http.get<Page<AdminSessionItem>>(
      `/admin/users/${encodeURIComponent(id)}/sessions`,
      { params },
    )
  },

  auditLogs(params: AdminAuditQuery) {
    return http.get<Page<AdminAuditLogItem>>('/admin/audit-logs', { params })
  },

  costSummary(days: number) {
    return http.get<AdminCostSummary>('/admin/costs/summary', { params: { days } })
  },

  costCalls(params: AdminCostCallQuery) {
    return http.get<Page<AdminCostCallItem>>('/admin/costs/calls', { params })
  },

  jobs(params: AdminJobQuery) {
    return http.get<Page<AdminJobItem>>('/admin/jobs', { params })
  },

  job(id: string) {
    return http.get<AdminJobDetail>(`/admin/jobs/${encodeURIComponent(id)}`)
  },

  retryJob(id: string) {
    return http.post<AdminJobRetryResponse>(
      `/admin/jobs/${encodeURIComponent(id)}/retry`,
    )
  },

  automationRuns(params: AdminAutomationRunQuery) {
    return http.get<Page<AdminAutomationRunItem>>('/admin/automation-runs', {
      params,
    })
  },

  contentReports(params: AdminContentQuery) {
    return http.get<Page<AdminContentReportItem>>('/admin/reports', { params })
  },

  contentReport(id: string) {
    return http.get<AdminContentReportDetail>(
      `/admin/reports/${encodeURIComponent(id)}`,
    )
  },

  contentScreenerRecords(params: AdminContentQuery) {
    return http.get<Page<AdminContentScreenerItem>>('/admin/screener-records', {
      params,
    })
  },

  contentScreenerRecord(id: string) {
    return http.get<AdminContentScreenerDetail>(
      `/admin/screener-records/${encodeURIComponent(id)}`,
    )
  },

  contentPortfolios(params: AdminContentQuery) {
    return http.get<Page<AdminContentPortfolioItem>>('/admin/portfolio-diagnoses', {
      params,
    })
  },

  contentPortfolio(id: string) {
    return http.get<AdminContentPortfolioDetail>(
      `/admin/portfolio-diagnoses/${encodeURIComponent(id)}`,
    )
  },

  contentWatchlist(params: AdminContentQuery) {
    return http.get<Page<AdminContentWatchlistItem>>('/admin/watchlist-items', {
      params,
    })
  },
}
