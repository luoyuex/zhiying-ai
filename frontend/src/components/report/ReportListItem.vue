<script setup lang="ts">
import type { ReportSummary } from '@/api/reports'
import { formatDateTime, formatTime, ratingTone, sourceLabel } from '@/utils/report'

withDefaults(
  defineProps<{
    item: ReportSummary
    /** time：只显示时分（已在按日分组的列表里）；datetime：显示 MMDD 时分 */
    timeStyle?: 'time' | 'datetime'
  }>(),
  { timeStyle: 'time' },
)
</script>

<template>
  <RouterLink
    :to="`/reports/${item.id}`"
    class="flex items-center gap-3 border-b border-line px-4 py-3.5 transition-colors last:border-b-0 hover:bg-surface"
  >
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
        <span class="truncate">{{ item.model }}</span>
      </div>
    </div>

    <div class="shrink-0 text-right">
      <div class="text-[11px] text-ink-3">置信度</div>
      <div class="text-sm font-semibold tabular-nums text-ink">{{ item.confidence }}</div>
    </div>
    <span class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
  </RouterLink>
</template>
