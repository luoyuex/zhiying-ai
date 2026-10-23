<script setup lang="ts">
import type { PortfolioDiagnosis } from '@/api/watchlist'
import { formatFullDateTime } from '@/utils/report'

defineProps<{ diagnosis: PortfolioDiagnosis }>()

function actionTone(action: string): string {
  if (action === '加仓' || action === '建仓') return 'bg-up-soft text-up'
  if (action === '减仓' || action === '清仓') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
}
</script>

<template>
  <div>
    <div class="grid gap-4 lg:grid-cols-[168px_1fr]">
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
          {{ formatFullDateTime(diagnosis.generated_at) }}
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

    <div v-if="diagnosis.positions.length" class="mt-4 grid gap-2 sm:grid-cols-2">
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
  </div>
</template>
