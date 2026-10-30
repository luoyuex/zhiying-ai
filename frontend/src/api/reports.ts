import { http } from './client'
import type { AIAnalysisResponse } from './ai'

export interface ReportSummary {
  id: string
  symbol: string
  name: string
  rating: string
  confidence: number
  model: string
  prompt_version: string
  decision_source: string
  rating_change: string | null
  prev_rating: string | null
  created_at: string
}

export interface ReportDetail {
  id: string
  created_at: string
  report: AIAnalysisResponse
}

export interface ReportStats {
  total: number
  stock_count: number
}

export const reportsApi = {
  list(symbol?: string, limit = 6, offset = 0, keyword?: string) {
    return http.get<ReportSummary[]>('/analysis/reports', {
      params: { symbol, limit, offset, keyword },
    })
  },

  stats(keyword?: string) {
    return http.get<ReportStats>('/analysis/reports/stats', {
      params: { keyword },
    })
  },

  get(id: string) {
    return http.get<ReportDetail>(`/analysis/reports/${encodeURIComponent(id)}`)
  },
}
