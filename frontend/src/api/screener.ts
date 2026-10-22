import { http } from './client'

export type ScreenerStrategyId =
  | 'main_force'
  | 'low_price_bull'
  | 'small_cap'
  | 'profit_growth'
  | 'value_stock'

export interface ScreenerStrategy {
  id: string
  name: string
  description: string
  status: 'available' | 'planned'
}

export interface ScreenerRecommendation {
  rank: number
  symbol: string
  name: string
  reasons: string[]
  highlights: string
  risks: string
  position: string
  investment_period: string
}

export interface ScreenerAnalysisResponse {
  record_id: string | null
  strategy: ScreenerStrategyId | string
  fund_flow: string
  industry: string
  fundamental: string
  recommendations: ScreenerRecommendation[]
  generated_at: string
  model: string
  quota_used: number
  quota_limit: number
  analyzed_count: number
  source: string
  disclaimer: string
}

export interface ScreenerRecordPick {
  rank: number
  symbol: string
  name: string
}

export interface ScreenerRecordSummary {
  id: string
  strategy: string
  created_at: string
  analyzed_count: number
  recommendation_count: number
  final_n: number
  max_change_pct: number | null
  picks: ScreenerRecordPick[]
}

export interface ScreenerRecordDetail {
  id: string
  strategy: string
  created_at: string
  filters: Record<string, unknown>
  result: ScreenerAnalysisResponse
}

export interface ScreenerJobState {
  job_id: string
  strategy: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  phase: string
  elapsed_seconds: number
  error_code: string
  error_message: string
  record_id: string | null
  created_at: string
  updated_at: string
}

export interface MainForceAnalysisRequest {
  final_n: number
  max_change_pct?: number | null
  min_price?: number | null
  max_price?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface LowPriceBullAnalysisRequest {
  final_n: number
  max_price: number
  min_profit_growth: number
  max_change_pct?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface SmallCapAnalysisRequest {
  final_n: number
  max_market_cap: number
  min_profit_growth: number
  min_revenue_growth: number
  max_change_pct?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface ProfitGrowthAnalysisRequest {
  final_n: number
  min_profit_growth: number
  max_change_pct?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface ValueStockAnalysisRequest {
  final_n: number
  max_pe: number
  max_pb: number
  min_dividend_yield: number
  max_debt_ratio: number
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export type ScreenerAnalysisRequest =
  | MainForceAnalysisRequest
  | LowPriceBullAnalysisRequest
  | SmallCapAnalysisRequest
  | ProfitGrowthAnalysisRequest
  | ValueStockAnalysisRequest

const JOB_PATHS: Record<ScreenerStrategyId, string> = {
  main_force: '/screener/main-force/jobs',
  low_price_bull: '/screener/low-price-bull/jobs',
  small_cap: '/screener/small-cap/jobs',
  profit_growth: '/screener/profit-growth/jobs',
  value_stock: '/screener/value-stock/jobs',
}

export const screenerApi = {
  strategies() {
    return http.get<ScreenerStrategy[]>('/screener/strategies')
  },

  startJob(strategy: ScreenerStrategyId, payload: ScreenerAnalysisRequest) {
    return http.post<ScreenerJobState>(JOB_PATHS[strategy], payload)
  },

  activeJob(strategy: ScreenerStrategyId) {
    return http.get<ScreenerJobState | null>('/screener/jobs/active', {
      params: { strategy },
    })
  },

  jobState(jobId: string) {
    return http.get<ScreenerJobState>(`/screener/jobs/${jobId}`)
  },

  records(strategy: ScreenerStrategyId, limit = 10) {
    return http.get<ScreenerRecordSummary[]>('/screener/records', {
      params: { strategy, limit },
    })
  },

  record(recordId: string) {
    return http.get<ScreenerRecordDetail>(`/screener/records/${recordId}`)
  },
}
