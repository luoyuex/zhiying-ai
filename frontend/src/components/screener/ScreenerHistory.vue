<script setup lang="ts">
import type { ScreenerRecordSummary } from '@/api/screener'
import { formatFullDateTime } from '@/utils/report'

defineProps<{
  records: ScreenerRecordSummary[]
  loading: boolean
  error: string
  activeRecordId: string | null
  detailRecordId: string | null
}>()

const emit = defineEmits<{ view: [recordId: string] }>()

function recordPicksLabel(record: ScreenerRecordSummary): string {
  const names = record.picks.map((pick) => pick.name || pick.symbol).filter(Boolean)
  return names.length ? names.join('、') : '没有产生 AI 精选'
}
</script>

<template>
  <section class="rounded-lg border border-line bg-canvas">
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3"
    >
      <div class="flex items-center gap-2">
        <h2 class="text-sm font-semibold text-ink">历史 AI 选股</h2>
        <span
          v-if="records.length"
          class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3"
        >
          {{ records.length }} 条
        </span>
      </div>
      <span class="text-[11px] text-ink-3">刷新后自动恢复最近一次</span>
    </div>

    <div v-if="loading" class="px-4 py-6 text-center text-[11px] text-ink-3">
      加载中…
    </div>
    <div v-else-if="error" class="px-4 py-4 text-[11px] text-ink-3">{{ error }}</div>
    <div v-else-if="!records.length" class="px-4 py-6 text-center text-[11px] text-ink-3">
      还没有记录，完成一次 AI 选股后会自动保存。
    </div>
    <div v-else>
      <div
        v-for="record in records"
        :key="record.id"
        class="flex w-full items-center gap-3 border-b border-line px-4 py-3 last:border-b-0"
        :class="activeRecordId === record.id ? 'bg-surface' : ''"
      >
        <div class="min-w-0 flex-1">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-[11px] text-ink-2">
              选股时间 {{ formatFullDateTime(record.created_at) }}
            </span>
            <span
              v-if="activeRecordId === record.id"
              class="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] font-medium text-primary"
            >
              当前
            </span>
            <span
              v-else-if="detailRecordId === record.id"
              class="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-3"
            >
              查看中
            </span>
          </div>
          <div class="mt-1 truncate text-[13px] text-ink">
            {{ recordPicksLabel(record) }}
          </div>
          <div class="mt-0.5 flex flex-wrap gap-x-2 text-[11px] text-ink-3">
            <span>AI 精选 {{ record.recommendation_count }} 只</span>
            <span>分析 {{ record.analyzed_count }} 只</span>
            <span v-if="record.final_n">目标 {{ record.final_n }} 只</span>
            <span v-if="record.max_change_pct !== null">
              涨幅上限 {{ record.max_change_pct }}%
            </span>
          </div>
        </div>
        <button
          type="button"
          class="shrink-0 rounded-md border border-line px-2.5 py-1 text-[11px] text-ink-2 transition-colors hover:border-line-strong hover:bg-surface hover:text-ink"
          @click="emit('view', record.id)"
        >
          查看 →
        </button>
      </div>
    </div>
  </section>
</template>
