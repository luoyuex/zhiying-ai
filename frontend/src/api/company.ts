import { http } from './client'

export interface FundFlowDay {
  date: string
  main_net: number | null
  small_net: number | null
  medium_net: number | null
  large_net: number | null
  super_large_net: number | null
  main_pct: number | null
  close: number | null
  change_pct: number | null
}

export interface FundFlowData {
  symbol: string
  days: FundFlowDay[]
  source: string
  fetched_at: string
}

export type FundFlowMetric =
  | 'main_net'
  | 'super_large_net'
  | 'large_net'
  | 'medium_net'
  | 'small_net'

export interface NewsItem {
  id: string
  kind: 'announcement' | 'article'
  title: string
  summary: string
  url: string
  source: string
  published_at: string
}

export interface CompanyNewsData {
  symbol: string
  announcements: NewsItem[]
  articles: NewsItem[]
  source: string
  fetched_at: string
  partial: boolean
}

export interface WebSource {
  title: string
  url: string
  date: string
  site: string
  summary: string
}

export interface WebSearchResult {
  query: string
  success: boolean
  pages: WebSource[]
  version: string
  error: string | null
  fetched_at: string
  cached: boolean
}

export const companyApi = {
  fundFlow(symbol: string) {
    return http.get<FundFlowData>(`/stocks/${encodeURIComponent(symbol)}/fund-flow`)
  },

  news(symbol: string, limit = 20) {
    return http.get<CompanyNewsData>(`/stocks/${encodeURIComponent(symbol)}/news`, {
      params: { limit },
    })
  },

  aiSearchNews(symbol: string) {
    return http.post<WebSearchResult>(
      `/stocks/${encodeURIComponent(symbol)}/news/ai-search`,
    )
  },
}
