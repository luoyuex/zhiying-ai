<script setup lang="ts">
import { computed } from 'vue'

import type { ReportSummary } from '@/api/reports'
import {
  formatDateTime,
  formatFullDateTime,
  formatRecentDateTime,
  formatTime,
  ratingTone,
  sourceLabel,
} from '@/utils/report'

const props = withDefaults(
  defineProps<{
    item: ReportSummary
    /** time：只显示时分（已在按日分组的列表里）；datetime：MMDD 时分；recent：今天/昨天 */
    timeStyle?: 'time' | 'datetime' | 'recent'
    /** always：总显示决策来源；fallback-only：只在规则兜底时提示 */
    sourceMode?: 'always' | 'fallback-only'
    /** 首页等紧凑场景隐藏「置信度」三字，只留数字 */
    showConfidenceLabel?: boolean
    /** 同一只股票在最近记录里另有几次分析 */
    repeats?: number
    /** 来源页，用于报告详情的「返回」目标 */
    from?: 'dashboard' | 'reports' | 'stock'
    /** 对比选择模式：点击整行切换选中，不跳转 */
    selectable?: boolean
    selected?: boolean
  }>(),
  {
    timeStyle: 'time',
    sourceMode: 'always',
    showConfidenceLabel: true,
    repeats: 0,
    from: 'reports',
  },
)

const emit = defineEmits<{ toggle: [] }>()

const to = computed(() => ({
  path: `/reports/${props.item.id}`,
  query: { from: props.from },
}))

const timeText = computed(() => {
  if (props.timeStyle === 'recent') return formatRecentDateTime(props.item.created_at)
  if (props.timeStyle === 'datetime') return formatDateTime(props.item.created_at)
  return formatTime(props.item.created_at)
})

const sourceText = computed(() => sourceLabel(props.item.decision_source))
const isFallback = computed(() => props.item.decision_source === 'rule_fallback')
const showSource = computed(
  () => props.sourceMode === 'always' || sourceText.value !== 'LLM 决策',
)
const fullTime = computed(() => formatFullDateTime(props.item.created_at))

function handleClick(
  event: MouseEvent,
  navigate: (event?: MouseEvent) => void,
): void {
  if (!props.selectable) {
    navigate(event)
    return
  }
  event.preventDefault()
  emit('toggle')
}
</script>

<template>
  <RouterLink v-slot="{ href, navigate }" :to="to" custom>
    <a
      :href="href"
      class="flex items-center gap-3 border-b border-line px-4 py-3.5 transition-colors last:border-b-0 hover:bg-surface"
      :class="selected ? 'bg-primary-soft' : ''"
      :title="fullTime"
      @click="handleClick($event, navigate)"
    >
      <span
        v-if="selectable"
        class="inline-flex size-4 shrink-0 items-center justify-center rounded border transition-colors"
        :class="selected ? 'border-primary bg-primary text-white' : 'border-line-strong'"
        aria-hidden="true"
      >
        <svg v-if="selected" class="size-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <path d="m5 12 5 5 9-10" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
      <span
        class="inline-flex h-7 w-12 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
        :class="ratingTone(item.rating)"
      >
        {{ item.rating }}
      </span>
      <span
        v-if="item.rating_change === 'up' || item.rating_change === 'down'"
        class="inline-flex h-7 shrink-0 items-center rounded-md px-2 text-[11px] font-medium"
        :class="item.rating_change === 'up' ? 'bg-up-soft text-up' : 'bg-down-soft text-down'"
      >
        {{ item.rating_change === 'up' ? '上调' : '下调' }}
      </span>

      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span class="text-[13px] font-medium text-ink">{{ item.name }}</span>
          <span class="text-xs tabular-nums text-ink-3">{{ item.symbol }}</span>
          <span class="text-[11px] text-ink-3">{{ timeText }}</span>
          <span
            v-if="repeats > 0"
            class="rounded bg-surface-2 px-1.5 py-px text-[10px] text-ink-3"
            :title="`该股在最近记录中另有 ${repeats} 次分析，历史报告页可查看全部`"
          >
            另有 {{ repeats }} 次
          </span>
        </div>
        <div
          v-if="showSource"
          class="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px]"
          :class="isFallback ? 'text-warn' : 'text-ink-3'"
        >
          <span>{{ sourceText }}</span>
        </div>
      </div>

      <div class="shrink-0 text-right" :title="`置信度 ${item.confidence}`">
        <div v-if="showConfidenceLabel" class="text-[11px] text-ink-3">置信度</div>
        <div class="text-sm font-semibold tabular-nums text-ink">{{ item.confidence }}</div>
      </div>
      <span v-if="!selectable" class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
    </a>
  </RouterLink>
</template>
