import { getAccessToken, http, refreshAccessToken } from './client'
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

export interface DiscussionTurn {
  speaker: string
  target: string
  stance: '同意' | '补充' | '质疑'
  content: string
}

export interface TeamDiscussion {
  turns: DiscussionTurn[]
  summary: string
  source: 'llm' | 'rule'
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
  /** 结合用户持仓的动作建议；未自选或旧报告为 null/空 */
  position_action: string | null
  position_advice: string
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
  discussion: TeamDiscussion | null
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

  startAnalysis(symbol: string, force = false) {
    return http.post<AIJobState>(
      `/stocks/${encodeURIComponent(symbol)}/ai-analysis`,
      null,
      { params: force ? { force: true } : undefined },
    )
  },

  job(jobId: string) {
    return http.get<AIJobState>(`/ai/jobs/${encodeURIComponent(jobId)}`)
  },

  /** 查询该股票当前仍在运行的任务；没有则返回 null */
  activeJob(symbol: string) {
    return http.get<AIJobState | null>('/ai/jobs/active', {
      params: { symbol },
    })
  },
}

export type AIJobEventType = 'snapshot' | 'phase' | 'done' | 'error'

export interface AIJobEvent {
  type: AIJobEventType
  job: AIJobState | null
  message?: string
}

function parseJobEvent(frame: string): AIJobEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }
  if (!data.length) return null

  const raw = data.join('\n')
  if (event === 'error') {
    let message = ''
    try {
      message = String(JSON.parse(raw).message ?? '')
    } catch {
      message = ''
    }
    return { type: 'error', job: null, message }
  }
  if (event !== 'snapshot' && event !== 'phase' && event !== 'done') return null
  return { type: event, job: JSON.parse(raw) as AIJobState }
}

async function openJobStream(jobId: string, signal: AbortSignal): Promise<Response> {
  const url = `/api/v1/ai/jobs/${encodeURIComponent(jobId)}/events`
  let token = getAccessToken()
  if (!token) token = await refreshAccessToken()
  if (!token) throw new Error('登录状态已失效')

  let response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
    signal,
  })
  if (response.status === 401) {
    const renewed = await refreshAccessToken()
    if (renewed) {
      response = await fetch(url, {
        headers: { Authorization: `Bearer ${renewed}`, Accept: 'text/event-stream' },
        signal,
      })
    }
  }
  if (!response.ok) throw new Error(`事件流连接失败（${response.status}）`)
  return response
}

/** 读取 AI 任务 SSE；连接失败时由调用方回退到轮询。 */
export async function streamJob(
  jobId: string,
  onEvent: (event: AIJobEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await openJobStream(jobId, signal)
  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseJobEvent(frame)
        if (event) onEvent(event)
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
