/** 价位提醒的展示文案：首页、自选卡片、提醒总览共用 */

import type { PriceAlert } from '@/api/watchlist'

/** 提醒类型 → 动作词：入场 / 止盈 / 止损 / 涨到 / 跌破 */
export function alertActionLabel(alert: PriceAlert): string {
  if (alert.kind === 'entry') return '入场'
  if (alert.kind === 'take_profit') return '止盈'
  if (alert.kind === 'stop_loss') return '止损'
  return alert.direction === 'above' ? '涨到' : '跌破'
}

/** 目标价写法：入场/止损用 ≤，止盈用 ≥，自定义直接给数值 */
export function alertTargetText(alert: PriceAlert): string {
  if (alert.kind === 'entry' || alert.kind === 'stop_loss') {
    return `≤ ${alert.target_price.toFixed(2)}`
  }
  if (alert.kind === 'take_profit') return `≥ ${alert.target_price.toFixed(2)}`
  return alert.target_price.toFixed(2)
}
