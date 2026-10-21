import { http } from './client'
import type { AIJobStatus } from './ai'

export interface LatestAnalysis {
  report_id: string
  rating: string
  confidence: number
  decision_source: string
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

  remove(symbol: string) {
    return http.delete(`/watchlist/${encodeURIComponent(symbol)}`)
  },
}
