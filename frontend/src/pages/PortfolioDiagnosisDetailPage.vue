<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { watchlistApi, type PortfolioDiagnosisDetail } from '@/api/watchlist'
import AppShell from '@/components/layout/AppShell.vue'
import PortfolioDiagnosisReport from '@/components/watchlist/PortfolioDiagnosisReport.vue'
import { getErrorMessage } from '@/utils/errors'

const route = useRoute()
const detail = ref<PortfolioDiagnosisDetail | null>(null)
const loading = ref(false)
const error = ref('')

async function load(id: string): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await watchlistApi.portfolioHistoryDetail(id)
    detail.value = data
  } catch (err) {
    detail.value = null
    error.value = getErrorMessage(err, '组合诊断记录加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => String(route.params.id ?? ''),
  (id) => {
    if (id) void load(id)
  },
  { immediate: true },
)
</script>

<template>
  <AppShell>
    <RouterLink
      to="/reports?tab=portfolio"
      class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
    >
      <span aria-hidden="true">←</span>
      返回组合诊断记录
    </RouterLink>

    <div v-if="loading" class="mt-6 animate-pulse rounded-lg border border-line bg-canvas p-5">
      <div class="h-6 w-40 rounded bg-surface-2" />
      <div class="mt-3 h-10 w-60 rounded bg-surface-2" />
      <div class="mt-5 h-40 rounded bg-surface-2" />
    </div>

    <div
      v-else-if="error || !detail"
      class="mt-6 rounded-lg border border-line bg-canvas px-5 py-10 text-center text-sm text-danger"
    >
      {{ error || '组合诊断记录不存在' }}
    </div>

    <template v-else>
      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-xs text-ink-3">自选组合 AI 诊断</p>
            <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">组合诊断</h1>
          </div>
          <div class="text-right text-[11px] text-ink-3">
            {{ detail.report.positions.length }} 只持仓
          </div>
        </div>
        <PortfolioDiagnosisReport class="mt-4" :diagnosis="detail.report" />
      </section>

      <p class="mt-3 text-[11px] leading-relaxed text-ink-3">
        此为历史诊断快照，持仓与行情可能已变化，请结合最新情况判断。
      </p>
    </template>
  </AppShell>
</template>
