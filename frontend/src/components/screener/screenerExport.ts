import type { ScreenerAnalysisResponse } from '@/api/screener'
import { downloadCsv } from '@/utils/csv'
import { datedFilename } from '@/utils/pdf'
import { formatFullDateTime } from '@/utils/report'

/** 选股结果 CSV：元信息在前，精选标的表格在后。 */
export function exportScreenerCsv(
  analysis: ScreenerAnalysisResponse,
  strategyName: string,
): void {
  const rows: Array<Array<string | number | null | undefined>> = [
    ['策略', strategyName],
    ['选股时间', formatFullDateTime(analysis.generated_at)],
    ['分析候选', analysis.analyzed_count],
    ['AI 精选', analysis.recommendations.length],
    [],
    ['排名', '代码', '名称', '推荐理由', '亮点', '风险', '建议仓位', '投资周期'],
  ]
  for (const item of analysis.recommendations) {
    rows.push([
      item.rank,
      item.symbol,
      item.name,
      item.reasons.join('；'),
      item.highlights,
      item.risks,
      item.position,
      item.investment_period,
    ])
  }
  rows.push([], ['免责声明', analysis.disclaimer])
  downloadCsv(
    datedFilename(`智盈AI_${strategyName}`, analysis.generated_at, 'csv'),
    rows,
  )
}
