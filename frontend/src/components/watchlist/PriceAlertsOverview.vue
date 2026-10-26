<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { watchlistApi, type PriceAlert } from '@/api/watchlist'
import {
  notifyPriceAlertsChanged,
  usePriceAlertsVersion,
} from '@/composables/usePriceAlertsSync'
import { formatDateTime } from '@/utils/report'

const alerts = ref<PriceAlert[]>([])
const loading = ref(true)
const error = ref('')
const cancelling = ref('')
const alertVersion = usePriceAlertsVersion()

const active = computed(() => alerts.value.filter((alert) => alert.status === 'active'))
const triggered = computed(() =>
  alerts.value.filter((alert) => alert.status === 'triggered').slice(0, 8),
)

function label(alert: PriceAlert): string {
  if (alert.kind === 'entry') return '入场'
  if (alert.kind === 'take_profit') return '止盈'
  if (alert.kind === 'stop_loss') return '止损'
  return alert.direction === 'above' ? '涨到' : '跌破'
}

function threshold(alert: PriceAlert): string {
  if (alert.kind === 'entry' || alert.kind === 'stop_loss') {
    return `≤ ${alert.target_price.toFixed(2)}`
  }
  if (alert.kind === 'take_profit') return `≥ ${alert.target_price.toFixed(2)}`
  return alert.target_price.toFixed(2)
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await watchlistApi.alerts()
    alerts.value = data
  } catch {
    alerts.value = []
  } finally {
    loading.value = false
  }
}

async function cancel(alert: PriceAlert): Promise<void> {
  if (cancelling.value) return
  cancelling.value = alert.id
  try {
    await watchlistApi.cancelAlert(alert.id)
    alerts.value = alerts.value.filter((item) => item.id !== alert.id)
    notifyPriceAlertsChanged()
  } catch {
    error.value = '取消失败，请稍后重试'
  } finally {
    cancelling.value = ''
  }
}

onMounted(load)
watch(alertVersion, () => {
  void load()
})
</script>

<template>
  <section
    v-if="!loading && (active.length || triggered.length)"
    class="mt-4 rounded-lg border border-line bg-canvas px-4 py-3"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-baseline gap-2">
        <h2 class="text-[13px] font-semibold text-ink">价位提醒</h2>
        <span class="text-[11px] text-ink-3">
          生效中 {{ active.length }} 条 · 触发一次后自动结束
        </span>
      </div>
      <span class="text-[10px] text-ink-3">交易时段内每 5 分钟检查</span>
    </div>

    <div v-if="active.length" class="mt-2 divide-y divide-line">
      <div
        v-for="alert in active"
        :key="alert.id"
        class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[11px]"
      >
        <RouterLink
          :to="`/stock/${alert.symbol}`"
          class="font-medium text-ink transition-colors hover:text-primary"
        >
          {{ alert.name || alert.symbol }}
        </RouterLink>
        <span class="tabular-nums text-ink-3">{{ alert.symbol }}</span>
        <span class="text-ink-2">{{ label(alert) }} {{ threshold(alert) }}</span>
        <button
          type="button"
          class="ml-auto text-ink-3 transition-colors hover:text-danger disabled:opacity-50"
          :disabled="cancelling === alert.id"
          @click="cancel(alert)"
        >
          {{ cancelling === alert.id ? '取消中…' : '取消' }}
        </button>
      </div>
    </div>
    <p v-else class="mt-2 text-[11px] text-ink-3">暂无生效中的提醒。</p>

    <details v-if="triggered.length" class="mt-2 border-t border-line pt-2">
      <summary class="cursor-pointer text-[11px] text-ink-3 transition-colors hover:text-ink">
        最近触发 {{ triggered.length }} 条
      </summary>
      <div class="mt-1 divide-y divide-line">
        <div
          v-for="alert in triggered"
          :key="alert.id"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 py-1.5 text-[11px] text-ink-2"
        >
          <span class="font-medium text-ink">{{ alert.name || alert.symbol }}</span>
          <span class="tabular-nums text-ink-3">{{ alert.symbol }}</span>
          <span>{{ label(alert) }} {{ threshold(alert) }}</span>
          <span class="text-ink-3">
            触发价
            {{ alert.triggered_price === null ? '—' : alert.triggered_price.toFixed(2) }}
          </span>
          <span class="ml-auto text-ink-3">
            {{ alert.triggered_at ? formatDateTime(alert.triggered_at) : '' }}
          </span>
        </div>
      </div>
    </details>

    <p v-if="error" class="mt-2 text-[11px] text-danger">{{ error }}</p>
  </section>
</template>
