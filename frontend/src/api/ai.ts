import { http } from './client'
import type { PriceLevels } from './market'

export type AIRating = '看多' | '偏多' | '中性' | '偏空' | '看空'
export type AITrend = '上升' | '下降' | '震荡'

export interface AIAnalysisPayload {
  rating: AIRating
  confidence: number
  trend: AITrend
  summary: string
  key_points: string[]
  risks: string[]
  watch: string
}

export interface AnalystReport {
  key: string
  name: string
  score: number
  rating: string
  summary: string
  points: string[]
  risks: string[]
  data_sources: string[]
  missing: string[]
  /** 该位分析师最终稿来自 LLM 还是规则引擎 */
  engine: 'llm' | 'rule'
}

export interface FinalDecision {
  rating: '买入' | '持有' | '卖出'
  confidence: number
  summary: string
  operation_advice: string
  holding_period: string
  position_size: string
  key_reasons: string[]
  risks: string[]
  risk_warning: string
  consensus: string[]
  dissent: string[]
  levels: PriceLevels
  decision_source: string
}

export interface WebSource {
  title: string
  url: string
  date: string
  site: string
  summary: string
}

export interface AIAnalysisResponse {
  report_id: string | null
  symbol: string
  name: string
  price: number | null
  change_pct: number | null
  model: string
  prompt_version: string
  generated_at: string
  data_as_of: string
  data_source: string
  cached: boolean
  quota_used: number
  quota_limit: number
  analysis: AIAnalysisPayload
  analysts: AnalystReport[]
  decision: FinalDecision | null
  web_search_used: boolean
  web_sources: WebSource[]
  disclaimer: string
}

export interface AIConfig {
  configured: boolean
  model: string
  prompt_version: string
  daily_quota: number
  quota_used: number
}

export type AIJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface AIJobState {
  job_id: string
  status: AIJobStatus
  symbol: string
  phase: string
  created_at: string
  updated_at: string
  elapsed_seconds: number
  result: AIAnalysisResponse | null
  error_code: string | null
  error_message: string | null
}

export const aiApi = {
  config() {
    return http.get<AIConfig>('/ai/config')
  },

  startAnalysis(symbol: string) {
    return http.post<AIJobState>(
      `/stocks/${encodeURIComponent(symbol)}/ai-analysis`,
      null,
    )
  },

  job(jobId: string) {
    return http.get<AIJobState>(`/ai/jobs/${encodeURIComponent(jobId)}`)
  },
}
