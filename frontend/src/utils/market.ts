import type { Quote } from '@/api/market'

export const SOURCE_LABELS: Record<string, string> = {
  tencent: '腾讯行情',
  sina: '新浪财经',
  eastmoney: '东方财富',
  eastmoney_finance: '东财财务',
  eastmoney_fundflow: '东财资金流',
  sina_fundflow: '新浪资金流',
  eastmoney_index: '东财指数',
  eastmoney_announcement: '东财公告',
  eastmoney_news: '东财资讯',
  computed: '本地计算',
  computed_technical: '本地计算',
}

export function sourceLabel(source?: string): string {
  if (!source) return '—'
  return SOURCE_LABELS[source] ?? source
}

export function formatSourceList(sources: string[]): string {
  const labels = sources
    .flatMap((source) => source.split('/'))
    .map((part) => sourceLabel(part.trim()))
    .filter((part) => part && part !== '—')
  // 不同原始 source 可能映射到同一中文名（如 tencent / tencent_kline），展示前去重
  return Array.from(new Set(labels)).join(' / ')
}

export function formatPrice(value: number | null): string {
  return value == null ? '—' : value.toFixed(2)
}

export function formatBig(value: number | null): string {
  if (value == null) return '—'
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(2)} 万`
  return value.toFixed(0)
}

export function formatVolume(value: number | null): string {
  if (value == null) return '—'
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)} 万手`
  return `${Math.round(value / 100)} 手`
}

export function formatPercent(value: number | null): string {
  return value == null ? '—' : `${value.toFixed(2)}%`
}

export function quoteToneClass(changePct: number | null | undefined): string {
  if (changePct == null || changePct === 0) return 'text-ink-2'
  return changePct > 0 ? 'text-up' : 'text-down'
}

export function formatChange(quote: Quote | null): string {
  if (!quote || quote.change == null || quote.change_pct == null) return '—'
  const sign = quote.change > 0 ? '+' : ''
  return `${sign}${quote.change.toFixed(2)}  ${sign}${quote.change_pct.toFixed(2)}%`
}

export function formatQuoteTime(iso: string | null | undefined): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function quoteMetrics(quote: Quote): { label: string; value: string }[] {
  return [
    { label: '今开', value: formatPrice(quote.open) },
    { label: '最高', value: formatPrice(quote.high) },
    { label: '最低', value: formatPrice(quote.low) },
    { label: '昨收', value: formatPrice(quote.pre_close) },
    { label: '成交量', value: formatVolume(quote.volume) },
    { label: '成交额', value: formatBig(quote.amount) },
    { label: '换手率', value: formatPercent(quote.turnover_pct) },
    { label: '市盈率', value: quote.pe == null ? '—' : quote.pe.toFixed(2) },
    { label: '总市值', value: formatBig(quote.total_market_cap) },
    { label: '市净率', value: quote.pb == null ? '—' : quote.pb.toFixed(2) },
    { label: '涨停', value: formatPrice(quote.limit_up) },
    { label: '跌停', value: formatPrice(quote.limit_down) },
  ]
}
