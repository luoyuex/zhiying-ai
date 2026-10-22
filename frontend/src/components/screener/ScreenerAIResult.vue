<script setup lang="ts">
import { computed } from 'vue'

import type { ScreenerAnalysisResponse, ScreenerStrategyId } from '@/api/screener'
import { formatFullDateTime } from '@/utils/report'
import { strategyMeta } from './strategy'

const props = defineProps<{
  analysis: ScreenerAnalysisResponse
  strategy: ScreenerStrategyId
}>()

const meta = computed(() => strategyMeta(props.strategy))

const analystReports = computed(() => [
  { title: meta.value.fundFlow, content: props.analysis.fund_flow },
  { title: meta.value.industry, content: props.analysis.industry },
  { title: meta.value.fundamental, content: props.analysis.fundamental },
])
</script>

<template>
  <section class="space-y-4">
    <div class="rounded-lg border border-line bg-canvas p-4">
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-ink">
            AI 精选 {{ analysis.recommendations.length }} 只
          </h2>
          <p
            class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3"
          >
            <span class="inline-flex items-center gap-1 font-medium text-ink-2">
              <svg
                class="size-3.5 shrink-0 text-ink-3"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" stroke-linecap="round" />
              </svg>
              选股时间 {{ formatFullDateTime(analysis.generated_at) }}
            </span>
            <span>分析候选 {{ analysis.analyzed_count }} 只</span>
            <span>额度 {{ analysis.quota_used }} / {{ analysis.quota_limit }}</span>
          </p>
        </div>
        <span
          class="rounded-full bg-primary-soft px-2.5 py-1 text-[10px] font-medium text-primary"
        >
          资深研究员精选
        </span>
      </div>

      <div v-if="analysis.recommendations.length" class="mt-3 space-y-2">
        <div
          v-for="recommendation in analysis.recommendations"
          :key="recommendation.symbol"
          class="rounded-md border border-line px-3 py-2.5"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span
              class="flex size-5 items-center justify-center rounded bg-ink text-[11px] text-canvas"
            >
              {{ recommendation.rank }}
            </span>
            <RouterLink
              :to="`/stock/${recommendation.symbol}`"
              class="text-[13px] font-medium text-ink transition-colors hover:text-primary"
            >
              {{ recommendation.name }}
            </RouterLink>
            <span class="text-[11px] tabular-nums text-ink-3">
              {{ recommendation.symbol }}
            </span>
            <span
              v-if="recommendation.position || recommendation.investment_period"
              class="ml-auto text-[11px] text-ink-3"
            >
              {{
                [recommendation.position, recommendation.investment_period]
                  .filter(Boolean)
                  .join(' · ')
              }}
            </span>
          </div>
          <ul class="mt-1.5 space-y-1">
            <li
              v-for="(reason, index) in recommendation.reasons"
              :key="index"
              class="flex gap-2 text-[11px] leading-relaxed text-ink-2"
            >
              <span class="mt-1.5 size-1 shrink-0 rounded-full bg-ink-3" />
              {{ reason }}
            </li>
          </ul>
          <div class="mt-1.5 grid gap-1 text-[11px] leading-relaxed sm:grid-cols-2">
            <p v-if="recommendation.highlights" class="text-ink-2">
              <span class="text-ink-3">亮点：</span>{{ recommendation.highlights }}
            </p>
            <p v-if="recommendation.risks" class="text-ink-2">
              <span class="text-ink-3">风险：</span>{{ recommendation.risks }}
            </p>
          </div>
        </div>
      </div>

      <div
        v-else
        class="mt-3 rounded-md border border-dashed border-line px-4 py-8 text-center text-xs text-ink-3"
      >
        本次没有产生 AI 精选结果，可适当放宽筛选条件后重试。
      </div>
    </div>

    <div class="rounded-lg border border-line bg-canvas p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-sm font-semibold text-ink">AI 分析师团队报告</h3>
      </div>
      <div class="mt-3 grid gap-3 lg:grid-cols-3">
        <div
          v-for="report in analystReports"
          :key="report.title"
          class="rounded-md bg-surface p-3"
        >
          <div class="text-[11px] font-medium text-ink">{{ report.title }}</div>
          <p
            class="mt-1 max-h-72 overflow-y-auto whitespace-pre-line text-[11px] leading-relaxed text-ink-2"
          >
            {{ report.content || '暂无内容' }}
          </p>
        </div>
      </div>
    </div>

    <p class="text-[10px] leading-relaxed text-ink-3">{{ analysis.disclaimer }}</p>
  </section>
</template>
