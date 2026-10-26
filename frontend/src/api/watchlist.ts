import { http } from './client'
import type { AIJobStatus } from './ai'

export interface LatestAnalysis {
  report_id: string
  rating: string
  confidence: number
  decision_source: string
  position_action: string | null
  summary: string
  rating_change: string | null
  prev_rating: string | null
  created_at: string
}

export interface WatchlistEntry {
  symbol: string
  name: string
  price: number | null
  change_pct: number | null
  source: string
  fetched_at: string | null
  delayed: boolean
  added_at: string
  note: string
  cost_price: number | null
  quantity: number | null
  latest: LatestAnalysis | null
}

export interface WatchlistStatus {
  symbol: string
  in_watchlist: boolean
}

export interface WatchlistMetaPayload {
  note?: string
  cost_price?: number | null
  quantity?: number | null
}

export interface WatchlistBatchResult {
  symbol: string
  job_id: string | null
  status: string
  error_code: string | null
  error_message: string | null
}

/** 批量分析后每只股票的行内任务状态 */
export interface WatchlistJobState {
  status: AIJobStatus
  phase?: string
  message?: string
}

export interface PortfolioPositionAdvice {
  symbol: string
  name: string
  action: '加仓' | '建仓' | '持有' | '减仓' | '清仓' | '观望'
  reason: string
}

export interface PortfolioDiagnosis {
  id?: string | null
  health_score: number
  summary: string
  risk_notes: string[]
  allocation_advice: string
  positions: PortfolioPositionAdvice[]
  generated_at: string
  model: string
  quota_used: number
  quota_limit: number
  disclaimer: string
}

export interface PortfolioDiagnosisSummary {
  id: string
  health_score: number
  position_count: number
  summary: string
  created_at: string
}

export interface PortfolioDiagnosisDetail {
  id: string
  created_at: string
  report: PortfolioDiagnosis
}

/** 调仓记录：成本价 / 数量每次变更落一条 */
export interface PositionChangeEntry {
  id: string
  symbol: string
  old_cost_price: number | null
  new_cost_price: number | null
  old_quantity: number | null
  new_quantity: number | null
  created_at: string
}

export type PriceAlertKind = 'custom' | 'entry' | 'take_profit' | 'stop_loss'

export interface PriceAlert {
  id: string
  symbol: string
  name: string
  direction: 'above' | 'below'
  target_price: number
  kind: PriceAlertKind
  report_id: string | null
  status: 'active' | 'triggered' | 'cancelled'
  triggered_price: number | null
  triggered_at: string | null
  created_at: string
}

export const watchlistApi = {
  list() {
    return http.get<WatchlistEntry[]>('/watchlist')
  },

  status(symbol: string) {
    return http.get<WatchlistStatus>(`/watchlist/${encodeURIComponent(symbol)}`)
  },

  add(symbol: string) {
    return http.post<{ symbol: string; added: boolean }>('/watchlist', { symbol })
  },

  update(symbol: string, payload: WatchlistMetaPayload) {
    return http.patch<WatchlistStatus>(`/watchlist/${encodeURIComponent(symbol)}`, payload)
  },

  batchAnalysis(symbols: string[], force = false) {
    return http.post<WatchlistBatchResult[]>('/watchlist/batch-analysis', {
      symbols,
      force,
    })
  },

  /** 组合 AI 诊断：单次 LLM 调用，耗时可能较长 */
  portfolioAnalysis() {
    return http.post<PortfolioDiagnosis>('/watchlist/portfolio-analysis', null, {
      timeout: 200000,
    })
  },

  portfolioHistory(limit = 20) {
    return http.get<PortfolioDiagnosisSummary[]>('/watchlist/portfolio-analysis/history', {
      params: { limit },
    })
  },

  portfolioLatest() {
    return http.get<PortfolioDiagnosisDetail | null>('/watchlist/portfolio-analysis/latest')
  },

  portfolioHistoryDetail(id: string) {
    return http.get<PortfolioDiagnosisDetail>(
      `/watchlist/portfolio-analysis/history/${encodeURIComponent(id)}`,
    )
  },

  /** 调仓记录：按需加载，不随列表自动请求 */
  positionHistory(symbol: string, limit = 30) {
    return http.get<PositionChangeEntry[]>(
      `/watchlist/${encodeURIComponent(symbol)}/position-history`,
      { params: { limit } },
    )
  },

  alerts() {
    return http.get<PriceAlert[]>('/watchlist/alerts')
  },

  createAlert(symbol: string, direction: 'above' | 'below', targetPrice: number) {
    return http.post<PriceAlert>(`/watchlist/${encodeURIComponent(symbol)}/alerts`, {
      kind: 'custom',
      direction,
      target_price: targetPrice,
    })
  },

  createReportAlert(
    symbol: string,
    kind: Exclude<PriceAlertKind, 'custom'>,
    reportId: string,
  ) {
    return http.post<PriceAlert>(`/watchlist/${encodeURIComponent(symbol)}/alerts`, {
      kind,
      report_id: reportId,
    })
  },

  cancelAlert(alertId: string) {
    return http.delete<void>(`/watchlist/alerts/${encodeURIComponent(alertId)}`)
  },

  remove(symbol: string) {
    return http.delete(`/watchlist/${encodeURIComponent(symbol)}`)
  },
}
