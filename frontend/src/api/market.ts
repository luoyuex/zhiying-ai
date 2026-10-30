import { http } from './client'

export interface Quote {
  symbol: string
  name: string
  price: number
  open: number | null
  pre_close: number | null
  high: number | null
  low: number | null
  change: number | null
  change_pct: number | null
  volume: number | null
  amount: number | null
  turnover_pct: number | null
  pe: number | null
  pb: number | null
  total_market_cap: number | null
  float_market_cap: number | null
  limit_up: number | null
  limit_down: number | null
  source: string
  fetched_at: string
  delayed: boolean
}

export interface KlineBar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
  turnover_pct: number | null
}

export interface KlineSeries {
  symbol: string
  period: string
  adjust: string
  bars: KlineBar[]
  source: string
  fetched_at: string
  delayed: boolean
}

export interface KlineParams {
  period?: '1m' | '5m' | '15m' | '30m' | '60m' | 'day' | 'week' | 'month'
  adjust?: 'none' | 'qfq' | 'hfq'
  limit?: number
}

export type SignalDirection = 'bullish' | 'bearish' | 'neutral'

export interface AnalysisSignal {
  name: string
  direction: SignalDirection
  detail: string
}

export interface IndicatorSnapshot {
  ma5: number | null
  ma10: number | null
  ma20: number | null
  ma60: number | null
  rsi14: number | null
  macd_dif: number | null
  macd_dea: number | null
  macd_hist: number | null
  boll_upper: number | null
  boll_mid: number | null
  boll_lower: number | null
  atr14: number | null
  volume_ratio: number | null
}

export interface PriceLevels {
  entry: number
  take_profit: number
  stop_loss: number
  risk_reward: number
  support: number
  resistance: number
  computed_by: string
}

export interface TechnicalAnalysis {
  symbol: string
  name: string
  price: number
  as_of: string
  score: number
  rating: string
  trend: string
  summary: string
  signals: AnalysisSignal[]
  indicators: IndicatorSnapshot
  levels: PriceLevels
  source: string
  disclaimer: string
}

export interface StockSearchItem {
  code: string
  name: string
  exchange: string
}

export interface HotStockItem {
  code: string
  name: string
  price: number | null
  change_pct: number | null
}

export const marketApi = {
  searchStocks(q: string, limit = 8) {
    return http.get<StockSearchItem[]>('/stocks/search', { params: { q, limit } })
  },

  /** 按当日成交额排序的活跃榜；取数失败时后端返回空数组 */
  hotStocks(limit = 8) {
    return http.get<HotStockItem[]>('/stocks/hot', { params: { limit } })
  },

  quote(symbol: string) {
    return http.get<Quote>(`/stocks/${encodeURIComponent(symbol)}/quote`)
  },

  kline(symbol: string, params: KlineParams = {}) {
    return http.get<KlineSeries>(`/stocks/${encodeURIComponent(symbol)}/kline`, { params })
  },

  analysis(symbol: string) {
    return http.get<TechnicalAnalysis>(`/stocks/${encodeURIComponent(symbol)}/analysis`)
  },
}
