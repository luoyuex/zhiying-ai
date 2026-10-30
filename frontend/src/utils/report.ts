/** 报告列表的格式化与配色：历史页、首页共用 */

import type { PriceLevels } from '@/api/market'

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** 最近记录场景：今天 / 昨天 + 时分，跨年补年份，避免 MMDD 被误读 */
export function formatRecentDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  const now = new Date()
  const startOfDay = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
  const dayDiff = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  if (dayDiff === 0) return `今天 ${time}`
  if (dayDiff === 1) return `昨天 ${time}`
  if (date.getFullYear() === now.getFullYear()) {
    return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${time}`
  }
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${time}`
}

export function formatFullDateTime(iso: string): string {
  const date = new Date(iso)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function ratingTone(rating: string): string {
  if (rating === '买入' || rating === '看多') return 'bg-up-soft text-up'
  if (rating === '卖出' || rating === '看空') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink'
}

/** 评级变化标记：本次结论与上一份报告对比（持平不展示，避免噪音） */
export function ratingChangeBadge(
  change: string | null | undefined,
  prevRating: string | null | undefined,
): { label: string; tone: string } | null {
  if (change === 'up') return { label: '评级上调', tone: 'bg-up-soft text-up' }
  if (change === 'down') return { label: '评级下调', tone: 'bg-down-soft text-down' }
  return null
}

/** 分析师评分配色：越高越积极 */
export function analystScoreTone(score: number): string {
  if (score >= 65) return 'text-up'
  if (score < 45) return 'text-down'
  return 'text-ink-2'
}

export interface DecisionLevelItem {
  label: string
  value: string
  tone: string
}

/** 决策价位列表；个股页可只保留入场/止盈/止损/盈亏比 */
export function decisionLevels(
  levels: PriceLevels | null | undefined,
  includeSupport = true,
): DecisionLevelItem[] {
  if (!levels) return []
  const items: DecisionLevelItem[] = []
  if (includeSupport) {
    items.push({ label: '支撑位', value: levels.support.toFixed(2), tone: 'text-ink' })
    items.push({ label: '压力位', value: levels.resistance.toFixed(2), tone: 'text-ink' })
  }
  items.push(
    { label: '建议入场', value: levels.entry.toFixed(2), tone: 'text-primary' },
    { label: '止盈', value: levels.take_profit.toFixed(2), tone: 'text-up' },
    { label: '止损', value: levels.stop_loss.toFixed(2), tone: 'text-down' },
    { label: '盈亏比', value: `${levels.risk_reward.toFixed(2)} : 1`, tone: 'text-ink' },
  )
  return items
}

export function sourceLabel(source: string): string {
  if (source === 'rule_fallback') return '规则兜底'
  if (source === 'llm') return 'LLM 决策'
  return '—'
}

/** 按自然日给出「今天 / 昨天 / MM-DD」分组标题 */
export function dayLabel(date: Date): string {
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const days = Math.round((start - target) / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}
