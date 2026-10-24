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

export const reportsApi = {
  list(symbol?: string, limit = 6) {
    return http.get<ReportSummary[]>('/analysis/reports', {
      params: { symbol, limit },
    })
  },

  get(id: string) {
    return http.get<ReportDetail>(`/analysis/reports/${encodeURIComponent(id)}`)
  },
}
