import type { ScreenerStrategyId } from '@/api/screener'

export interface StrategyMeta {
  name: string
  fundFlow: string
  industry: string
  fundamental: string
}

export const STRATEGY_META: Record<ScreenerStrategyId, StrategyMeta> = {
  main_force: {
    name: '主力追踪',
    fundFlow: '资金流向分析师',
    industry: '行业板块分析师',
    fundamental: '财务基本面分析师',
  },
  low_price_bull: {
    name: '低价寻宝',
    fundFlow: '资金与流动性分析师',
    industry: '行业板块分析师',
    fundamental: '业绩成长分析师',
  },
  small_cap: {
    name: '小盘精选',
    fundFlow: '资金与流动性分析师',
    industry: '行业板块分析师',
    fundamental: '成长与估值分析师',
  },
  profit_growth: {
    name: '业绩高增',
    fundFlow: '资金与流动性分析师',
    industry: '行业板块分析师',
    fundamental: '成长质量分析师',
  },
  value_stock: {
    name: '价值洼地',
    fundFlow: '资金与流动性分析师',
    industry: '行业板块分析师',
    fundamental: '估值质量分析师',
  },
}

export function strategyMeta(strategy: string): StrategyMeta {
  return STRATEGY_META[strategy as ScreenerStrategyId] ?? STRATEGY_META.main_force
}
