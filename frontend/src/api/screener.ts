import { http } from './client'

export interface ScreenerStrategy {
  id: string
  name: string
  description: string
  status: 'available' | 'planned'
}

export interface FundFlowRankItem {
  symbol: string
  name: string
  price: number | null
  change_pct: number | null
  main_net: number
  main_net_pct: number | null
  amount: number | null
}

export interface MainForceScreenRequest {
  top_n: number
  max_change_pct?: number | null
  min_price?: number | null
  max_price?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface MainForceScreenResponse {
  strategy: string
  items: FundFlowRankItem[]
  scanned_count: number
  candidate_count: number
  fetched_at: string
  source: string
  filters: Record<string, unknown>
  disclaimer: string
}

export interface LowPriceBullRequest {
  top_n: number
  max_price: number
  min_profit_growth: number
  max_change_pct?: number | null
  exclude_st: boolean
  exclude_gem: boolean
  exclude_star: boolean
  exclude_bj: boolean
}

export interface LowPriceBullItem {
  symbol: string
  name: string
  price: number | null
  change_pct: number | null
  amount: number | null
  profit_growth: number | null
  revenue_growth: number | null
  report_date: string
}

export interface LowPriceBullResponse {
  strategy: string
  items: LowPriceBullItem[]
  scanned_count: number
  candidate_count: number
  fetched_at: string
  source: string
  filters: Record<string, unknown>
  disclaimer: string
}

export const screenerApi = {
  strategies() {
    return http.get<ScreenerStrategy[]>('/screener/strategies')
  },

  mainForce(payload: MainForceScreenRequest) {
    return http.post<MainForceScreenResponse>('/screener/main-force', payload, {
      timeout: 40000,
    })
  },

  lowPriceBull(payload: LowPriceBullRequest) {
    return http.post<LowPriceBullResponse>('/screener/low-price-bull', payload, {
      timeout: 40000,
    })
  },
}
