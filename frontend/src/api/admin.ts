import type {
  AdminAuditLogItem,
  AdminOverview,
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

export const adminApi = {
  overview(range: 'today' | '7d') {
    return http.get<AdminOverview>('/admin/overview', { params: { range } })
  },

  users(params: AdminUserQuery) {
    return http.get<Page<AdminUserListItem>>('/admin/users', { params })
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
}
