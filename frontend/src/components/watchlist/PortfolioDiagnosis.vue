<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { watchlistApi, type PortfolioDiagnosis } from '@/api/watchlist'
import { getErrorMessage } from '@/utils/errors'
import { datedFilename, exportElementToPdf } from '@/utils/pdf'
import { formatFullDateTime } from '@/utils/report'
import PortfolioDiagnosisReport from './PortfolioDiagnosisReport.vue'
import { exportPortfolioCsv } from './portfolioExport'

const loading = ref(false)
const error = ref('')
const diagnosis = ref<PortfolioDiagnosis | null>(null)
const hasHistory = ref(false)
const expanded = ref(false)
const reportRoot = ref<HTMLElement | null>(null)
const pdfBusy = ref(false)
const exportError = ref('')

async function exportPdf(): Promise<void> {
  if (!reportRoot.value || !diagnosis.value || pdfBusy.value) return
  pdfBusy.value = true
  exportError.value = ''
  try {
    await exportElementToPdf(
      reportRoot.value,
      datedFilename('智盈AI_组合诊断', diagnosis.value.generated_at),
    )
  } catch (err) {
    exportError.value = getErrorMessage(err, 'PDF 导出失败，请稍后重试')
  } finally {
    pdfBusy.value = false
  }
}

async function restoreLatest(): Promise<void> {
  try {
    const { data } = await watchlistApi.portfolioLatest()
    if (!data) return
    hasHistory.value = true
    if (!diagnosis.value) {
      diagnosis.value = data.report
      expanded.value = false
    }
  } catch {
    // 历史恢复失败不影响重新诊断
  }
}

async function run(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await watchlistApi.portfolioAnalysis()
    diagnosis.value = data
    hasHistory.value = true
    expanded.value = true
  } catch (err) {
    error.value = getErrorMessage(err, '组合诊断失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void restoreLatest()
})
</script>

<template>
  <section class="rounded-lg border border-line bg-canvas p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="text-sm font-semibold text-ink">AI 组合诊断</h2>
          <span class="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-3">
            结合持仓与最新结论
          </span>
        </div>
        <p class="mt-1 text-[11px] leading-relaxed text-ink-3">
          从组合视角评估集中度与风险，逐只给出加仓 / 持有 / 减仓 / 清仓建议，每次消耗 1 次额度。
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <template v-if="diagnosis && expanded">
          <button
            type="button"
            class="text-xs text-ink-3 transition-colors hover:text-ink"
            @click="exportPortfolioCsv(diagnosis)"
          >
            导出 CSV
          </button>
          <button
            type="button"
            class="text-xs text-ink-3 transition-colors hover:text-ink disabled:opacity-50"
            :disabled="pdfBusy"
            @click="exportPdf"
          >
            {{ pdfBusy ? '导出中…' : '导出 PDF' }}
          </button>
          <button
            type="button"
            class="text-xs text-ink-3 transition-colors hover:text-ink"
            @click="expanded = false"
          >
            收起
          </button>
        </template>
        <RouterLink
          v-if="hasHistory"
          to="/reports?tab=portfolio"
          class="text-xs text-ink-3 transition-colors hover:text-ink"
        >
          历史诊断
        </RouterLink>
        <button
          type="button"
          class="h-8 rounded-md border px-3 text-xs transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          :class="
            loading
              ? 'border-line text-ink-2'
              : 'border-ink bg-ink text-canvas hover:opacity-80'
          "
          :disabled="loading"
          @click="run"
        >
          {{ loading ? '诊断中…' : diagnosis ? '重新诊断' : '开始诊断' }}
        </button>
      </div>
    </div>

    <div
      v-if="loading"
      class="mt-4 flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-xs text-ink-2"
    >
      <span
        class="size-3.5 shrink-0 animate-spin rounded-full border-2 border-ink-3/30 border-t-ink-3"
      />
      LLM 正在评估整个组合，通常需要 20–60 秒…
    </div>

    <div
      v-else-if="error"
      class="mt-4 rounded-md bg-danger-soft px-3 py-2 text-xs text-danger"
    >
      {{ error }}
    </div>

    <template v-else-if="diagnosis">
      <div v-if="expanded" ref="reportRoot">
        <PortfolioDiagnosisReport class="mt-4" :diagnosis="diagnosis" />
      </div>

      <div
        v-else
        class="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-surface px-4 py-3"
      >
      <div class="flex items-baseline gap-1">
        <span class="text-[24px] font-semibold leading-none tabular-nums text-ink">
          {{ diagnosis.health_score }}
        </span>
        <span class="text-[11px] text-ink-3">/ 100 健康度</span>
      </div>
      <div class="min-w-0 flex-1">
        <p class="line-clamp-2 text-xs leading-relaxed text-ink-2">
          {{ diagnosis.summary }}
        </p>
        <div class="mt-1 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
          <span>{{ formatFullDateTime(diagnosis.generated_at) }}</span>
          <span>{{ diagnosis.positions.length }} 只持仓</span>
          <span v-if="diagnosis.risk_notes.length">{{ diagnosis.risk_notes.length }} 条风险</span>
        </div>
      </div>
      <button
        type="button"
        class="shrink-0 text-xs text-ink-2 underline-offset-2 transition-colors hover:text-ink hover:underline"
        @click="expanded = true"
      >
        展开详情
      </button>
      </div>
    </template>

    <p v-if="exportError" class="mt-2 text-xs text-danger">{{ exportError }}</p>
  </section>
</template>
