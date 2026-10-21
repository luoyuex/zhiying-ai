/** 选股结果列表的展示模型：不同策略只决定右侧指标。 */

export interface ScreenerMetricDisplay {
  label: string
  value: string
  tone?: string
}

export interface ScreenerDisplayItem {
  symbol: string
  name: string
  price: number | null
  change_pct: number | null
  metrics: ScreenerMetricDisplay[]
}
