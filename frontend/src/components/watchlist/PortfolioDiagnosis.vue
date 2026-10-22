<script setup lang="ts">
import { ref } from 'vue'

import { watchlistApi, type PortfolioDiagnosis } from '@/api/watchlist'
import { getErrorMessage } from '@/utils/errors'
import { formatDateTime } from '@/utils/report'

const loading = ref(false)
const error = ref('')
const diagnosis = ref<PortfolioDiagnosis | null>(null)

async function run(): Promise<void> {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await watchlistApi.portfolioAnalysis()
    diagnosis.value = data
  } catch (err) {
    error.value = getErrorMessage(err, '组合诊断失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function actionTone(action: string): string {
  if (action === '加仓' || action === '建仓') return 'bg-up-soft text-up'
  if (action === '减仓' || action === '清仓') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
}
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
      <button
        type="button"
        class="h-8 shrink-0 rounded-md border px-3 text-xs transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
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
      <div class="mt-4 grid gap-4 lg:grid-cols-[168px_1fr]">
        <div class="rounded-md bg-surface p-4">
          <div class="text-[11px] text-ink-3">组合健康度</div>
          <div class="mt-1 flex items-baseline gap-1">
            <span class="text-[32px] font-semibold leading-none tabular-nums text-ink">
              {{ diagnosis.health_score }}
            </span>
            <span class="text-xs text-ink-3">/ 100</span>
          </div>
          <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full rounded-full bg-ink"
              :style="{ width: `${diagnosis.health_score}%` }"
            />
          </div>
          <div class="mt-2 text-[11px] leading-relaxed text-ink-3">
            {{ formatDateTime(diagnosis.generated_at) }}
          </div>
        </div>

        <div class="min-w-0">
          <p class="text-[13px] leading-relaxed text-ink-2">{{ diagnosis.summary }}</p>
          <p
            v-if="diagnosis.allocation_advice"
            class="mt-3 rounded-md bg-surface px-3 py-2 text-xs leading-relaxed text-ink-2"
          >
            <span class="font-medium text-ink">仓位建议：</span>
            {{ diagnosis.allocation_advice }}
          </p>
        </div>
      </div>

      <div class="mt-4 grid gap-2 sm:grid-cols-2">
        <div
          v-for="position in diagnosis.positions"
          :key="position.symbol"
          class="flex items-start gap-2 rounded-md border border-line px-3 py-2"
        >
          <span
            class="mt-0.5 inline-flex h-5 shrink-0 items-center rounded px-1.5 text-[11px] font-medium"
            :class="actionTone(position.action)"
          >
            {{ position.action }}
          </span>
          <div class="min-w-0">
            <div class="flex flex-wrap items-baseline gap-x-1.5">
              <RouterLink
                :to="`/stock/${position.symbol}`"
                class="text-xs font-medium text-ink transition-colors hover:text-primary"
              >
                {{ position.name }}
              </RouterLink>
              <span class="text-[11px] tabular-nums text-ink-3">{{ position.symbol }}</span>
            </div>
            <p class="mt-0.5 text-[11px] leading-relaxed text-ink-2">
              {{ position.reason }}
            </p>
          </div>
        </div>
      </div>

      <div v-if="diagnosis.risk_notes.length" class="mt-4">
        <div class="text-[11px] text-ink-3">组合风险</div>
        <ul class="mt-1.5 space-y-1">
          <li
            v-for="(note, index) in diagnosis.risk_notes"
            :key="index"
            class="flex gap-2 text-[11px] leading-relaxed text-ink-2"
          >
            <span class="mt-1.5 size-1 shrink-0 rounded-full bg-warn" />
            {{ note }}
          </li>
        </ul>
      </div>

      <p class="mt-3 text-[10px] leading-relaxed text-ink-3">
        {{ diagnosis.disclaimer }}
      </p>
    </template>
  </section>
</template>
