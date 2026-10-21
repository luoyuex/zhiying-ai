/** 报告列表的格式化与配色：历史页、工作台共用 */

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

export function ratingTone(rating: string): string {
  if (rating === '买入' || rating === '看多') return 'bg-up-soft text-up'
  if (rating === '卖出' || rating === '看空') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
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
