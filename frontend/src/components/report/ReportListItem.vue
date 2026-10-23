<script setup lang="ts">
import { computed } from 'vue'

import type { ReportSummary } from '@/api/reports'
import { formatDateTime, formatTime, ratingTone, sourceLabel } from '@/utils/report'

const props = withDefaults(
  defineProps<{
    item: ReportSummary
    /** time：只显示时分（已在按日分组的列表里）；datetime：显示 MMDD 时分 */
    timeStyle?: 'time' | 'datetime'
    /** 来源页，用于报告详情的「返回」目标 */
    from?: 'dashboard' | 'reports' | 'stock'
    /** 对比选择模式：点击整行切换选中，不跳转 */
    selectable?: boolean
    selected?: boolean
  }>(),
  { timeStyle: 'time', from: 'reports' },
)

const emit = defineEmits<{ toggle: [] }>()

const to = computed(() => ({
  path: `/reports/${props.item.id}`,
  query: { from: props.from },
}))

function handleClick(event: MouseEvent): void {
  if (!props.selectable) return
  event.preventDefault()
  emit('toggle')
}
</script>

<template>
  <RouterLink
    :to="to"
    class="flex items-center gap-3 border-b border-line px-4 py-3.5 transition-colors last:border-b-0 hover:bg-surface"
    :class="selected ? 'bg-primary-soft' : ''"
    @click="handleClick"
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

    <div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span class="text-[13px] font-medium text-ink">{{ item.name }}</span>
        <span class="text-xs tabular-nums text-ink-3">{{ item.symbol }}</span>
        <span class="text-[11px] text-ink-3">
          {{ timeStyle === 'datetime' ? formatDateTime(item.created_at) : formatTime(item.created_at) }}
        </span>
      </div>
      <div class="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-ink-3">
        <span>{{ sourceLabel(item.decision_source) }}</span>
      </div>
    </div>

    <div class="shrink-0 text-right">
      <div class="text-[11px] text-ink-3">置信度</div>
      <div class="text-sm font-semibold tabular-nums text-ink">{{ item.confidence }}</div>
    </div>
    <span v-if="!selectable" class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
  </RouterLink>
</template>
