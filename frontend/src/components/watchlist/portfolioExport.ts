import type { PortfolioDiagnosis } from '@/api/watchlist'
import { downloadCsv } from '@/utils/csv'
import { datedFilename } from '@/utils/pdf'
import { formatFullDateTime } from '@/utils/report'

/** 组合诊断 CSV：摘要与风险在前，逐只建议表格在后。 */
export function exportPortfolioCsv(diagnosis: PortfolioDiagnosis): void {
  const rows: Array<Array<string | number | null | undefined>> = [
    ['诊断时间', formatFullDateTime(diagnosis.generated_at)],
    ['组合健康度', diagnosis.health_score],
    ['持仓数', diagnosis.positions.length],
    ['摘要', diagnosis.summary],
    ['仓位建议', diagnosis.allocation_advice],
  ]
  if (diagnosis.risk_notes.length) {
    rows.push(['组合风险', diagnosis.risk_notes.join('；')])
  }
  rows.push(
    [],
    ['序号', '代码', '名称', '建议', '理由'],
  )
  diagnosis.positions.forEach((position, index) => {
    rows.push([index + 1, position.symbol, position.name, position.action, position.reason])
  })
  rows.push([], ['免责声明', diagnosis.disclaimer])
  downloadCsv(datedFilename('智盈AI_组合诊断', diagnosis.generated_at, 'csv'), rows)
}
