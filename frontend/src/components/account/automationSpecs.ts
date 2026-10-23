import type { AutomationStrategyId } from '@/api/automation'

export interface StrategyFieldSpec {
  key: string
  label: string
  type: 'number' | 'boolean' | 'select'
  default: number | boolean | string | null
  min?: number
  max?: number
  step?: number
  suffix?: string
  options?: { label: string; value: string }[]
}

export interface StrategyFormSpec {
  id: AutomationStrategyId
  name: string
  description: string
  fields: StrategyFieldSpec[]
}

const EXCLUDE_FIELDS: StrategyFieldSpec[] = (
  [
    ['exclude_st', '剔除 ST'],
    ['exclude_gem', '剔除创业板'],
    ['exclude_star', '剔除科创板'],
    ['exclude_bj', '剔除北交所'],
  ] as const
).map(([key, label]) => ({ key, label, type: 'boolean', default: true }))

export const STRATEGY_FORM_SPECS: StrategyFormSpec[] = [
  {
    id: 'main_force',
    name: '主力追踪',
    description: '按所选区间主力净流入排行 + 市值区间筛选',
    fields: [
      { key: 'final_n', label: '精选数量', type: 'number', default: 5, min: 3, max: 10 },
      {
        key: 'window',
        label: '统计区间',
        type: 'select',
        default: '10d',
        options: [
          { label: '今日', value: 'today' },
          { label: '近 3 日', value: '3d' },
          { label: '近 5 日', value: '5d' },
          { label: '近 10 日', value: '10d' },
        ],
      },
      { key: 'max_change_pct', label: '区间涨幅上限', type: 'number', default: 30, min: -100, max: 500, suffix: '%' },
      { key: 'min_market_cap', label: '总市值下限', type: 'number', default: 50, min: 1, max: 50000, suffix: '亿' },
      { key: 'max_market_cap', label: '总市值上限', type: 'number', default: 5000, min: 1, max: 50000, suffix: '亿' },
      { key: 'min_price', label: '最低价', type: 'number', default: null, min: 0, suffix: '元' },
      { key: 'max_price', label: '最高价', type: 'number', default: null, min: 0, suffix: '元' },
      ...EXCLUDE_FIELDS,
    ],
  },
  {
    id: 'low_price_bull',
    name: '低价寻宝',
    description: '低价 + 高净利增长，按成交额升序',
    fields: [
      { key: 'final_n', label: '精选数量', type: 'number', default: 5, min: 3, max: 10 },
      { key: 'max_price', label: '股价上限', type: 'number', default: 10, min: 0.1, max: 100, suffix: '元' },
      { key: 'min_profit_growth', label: '净利同比下限', type: 'number', default: 100, min: 0, suffix: '%' },
      ...EXCLUDE_FIELDS,
    ],
  },
  {
    id: 'small_cap',
    name: '小盘精选',
    description: '小市值 + 营收净利双增长，按市值升序',
    fields: [
      { key: 'final_n', label: '精选数量', type: 'number', default: 5, min: 3, max: 10 },
      { key: 'max_market_cap', label: '总市值上限', type: 'number', default: 50, min: 1, max: 500, suffix: '亿' },
      { key: 'min_profit_growth', label: '净利同比下限', type: 'number', default: 100, min: 0, suffix: '%' },
      { key: 'min_revenue_growth', label: '营收同比下限', type: 'number', default: 10, min: 0, suffix: '%' },
      ...EXCLUDE_FIELDS,
    ],
  },
  {
    id: 'profit_growth',
    name: '业绩高增',
    description: '净利同比达标 + 排除低基数与一次性收益',
    fields: [
      { key: 'final_n', label: '精选数量', type: 'number', default: 5, min: 3, max: 10 },
      { key: 'min_profit_growth', label: '净利同比下限', type: 'number', default: 10, min: 0, suffix: '%' },
      ...EXCLUDE_FIELDS,
    ],
  },
  {
    id: 'value_stock',
    name: '价值洼地',
    description: '低 PE/PB + 高股息 + 低负债，防价值陷阱',
    fields: [
      { key: 'final_n', label: '精选数量', type: 'number', default: 5, min: 3, max: 10 },
      { key: 'max_pe', label: 'PE 上限', type: 'number', default: 20, min: 0.1, max: 200 },
      { key: 'max_pb', label: 'PB 上限', type: 'number', default: 1.5, min: 0.1, max: 20 },
      { key: 'min_dividend_yield', label: '股息率下限', type: 'number', default: 1, min: 0, max: 20, suffix: '%' },
      { key: 'max_debt_ratio', label: '资产负债率上限', type: 'number', default: 30, min: 0, max: 100, suffix: '%' },
      ...EXCLUDE_FIELDS,
    ],
  },
]

/** 用服务端返回的 filters 合并出完整表单值（缺失项用默认值占位） */
export function mergeFilters(
  spec: StrategyFormSpec,
  filters: Record<string, unknown> | undefined,
): Record<string, number | boolean | string | null> {
  const result: Record<string, number | boolean | string | null> = {}
  for (const field of spec.fields) {
    const raw = filters?.[field.key]
    if (field.type === 'boolean') {
      result[field.key] = typeof raw === 'boolean' ? raw : Boolean(field.default)
    } else if (field.type === 'select') {
      const values = (field.options ?? []).map((option) => option.value)
      result[field.key] =
        typeof raw === 'string' && values.includes(raw)
          ? raw
          : String(field.default ?? values[0] ?? '')
    } else if (raw === null || raw === undefined || raw === '') {
      result[field.key] = field.default as number | null
    } else {
      result[field.key] = Number(raw)
    }
  }
  return result
}
