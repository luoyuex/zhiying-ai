<script setup lang="ts">
import { computed, ref } from 'vue'

import { watchlistApi, type WatchlistEntry, type WatchlistJobState } from '@/api/watchlist'
import { getErrorMessage } from '@/utils/errors'
import { formatSourceList } from '@/utils/market'
import { formatDateTime, ratingTone } from '@/utils/report'

const props = defineProps<{
  item: WatchlistEntry
  selected: boolean
  batch: WatchlistJobState | null
}>()

const emit = defineEmits<{
  toggle: []
  remove: []
  updated: [payload: { note: string; cost_price: number | null; quantity: number | null }]
}>()

const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const noteInput = ref('')
const costInput = ref('')
const quantityInput = ref('')

const metaParts = computed(() => {
  const parts: string[] = []
  if (props.item.cost_price !== null) parts.push(`成本 ${props.item.cost_price.toFixed(2)}`)
  if (props.item.quantity !== null) parts.push(`${props.item.quantity} 股`)
  return parts
})

const pnlPct = computed(() => {
  const { price, cost_price: cost } = props.item
  if (price === null || cost === null || cost <= 0) return null
  return ((price - cost) / cost) * 100
})

const pnlAmount = computed(() => {
  const { price, cost_price: cost, quantity } = props.item
  if (price === null || cost === null || cost <= 0 || quantity === null) return null
  return (price - cost) * quantity
})

const pnlTone = computed(() => {
  if (pnlPct.value === null || pnlPct.value === 0) return 'text-ink-2'
  return pnlPct.value > 0 ? 'text-up' : 'text-down'
})

const actionTone = computed(() => {
  const action = props.item.latest?.position_action
  if (action === '加仓' || action === '建仓') return 'bg-up-soft text-up'
  if (action === '减仓' || action === '清仓') return 'bg-down-soft text-down'
  return 'bg-surface-2 text-ink-2'
})

function formatSignedPct(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatSignedAmount(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(0)} 元`
}

const batchText = computed(() => {
  const state = props.batch
  if (!state) return ''
  if (state.status === 'queued') return '排队中'
  if (state.status === 'running') return state.phase || '分析中'
  if (state.status === 'succeeded') return '分析完成'
  return state.message || '分析失败'
})

function changeTone(value: number | null): string {
  if (value === null) return 'text-ink-3'
  if (value > 0) return 'text-up'
  if (value < 0) return 'text-down'
  return 'text-ink-2'
}

function formatPrice(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

function formatPct(value: number | null): string {
  if (value === null) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function startEdit(): void {
  noteInput.value = props.item.note
  costInput.value = props.item.cost_price === null ? '' : String(props.item.cost_price)
  quantityInput.value = props.item.quantity === null ? '' : String(props.item.quantity)
  saveError.value = ''
  editing.value = true
}

function cancelEdit(): void {
  editing.value = false
  saveError.value = ''
}

async function saveEdit(): Promise<void> {
  if (saving.value) return
  const cost = String(costInput.value).trim()
  const quantity = String(quantityInput.value).trim()

  const costPrice = cost === '' ? null : Number(cost)
  if (costPrice !== null && (!Number.isFinite(costPrice) || costPrice < 0)) {
    saveError.value = '成本价需为非负数字'
    return
  }
  const quantityValue = quantity === '' ? null : Number(quantity)
  if (
    quantityValue !== null &&
    (!Number.isInteger(quantityValue) || quantityValue < 0)
  ) {
    saveError.value = '数量需为非负整数'
    return
  }

  saving.value = true
  saveError.value = ''
  try {
    const payload = {
      note: noteInput.value.trim(),
      cost_price: costPrice,
      quantity: quantityValue,
    }
    await watchlistApi.update(props.item.symbol, payload)
    emit('updated', payload)
    editing.value = false
  } catch (err) {
    saveError.value = getErrorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <article
    class="relative rounded-lg border bg-canvas transition-colors"
    :class="selected ? 'border-line-strong' : 'border-line hover:border-line-strong'"
  >
    <label class="absolute left-3 top-3 flex size-5 items-center justify-center">
      <input
        type="checkbox"
        class="size-3.5 cursor-pointer accent-ink"
        :checked="selected"
        :aria-label="`选择 ${item.name}`"
        @change="emit('toggle')"
      />
    </label>

    <button
      type="button"
      class="absolute right-2 top-2 flex size-6 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
      :aria-label="`移出 ${item.name}`"
      @click="emit('remove')"
    >
      <svg
        class="size-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        aria-hidden="true"
      >
        <path d="M6 6l12 12M18 6 6 18" stroke-linecap="round" />
      </svg>
    </button>

    <RouterLink :to="`/stock/${item.symbol}`" class="block p-4 pl-10 pr-9">
      <div class="flex items-baseline justify-between gap-2">
        <span class="truncate text-[13px] font-medium text-ink">{{ item.name }}</span>
        <span class="shrink-0 text-[11px] tabular-nums text-ink-3">
          {{ item.symbol }}
        </span>
      </div>
      <div class="mt-2 flex items-baseline justify-between gap-2">
        <span
          class="text-[22px] font-semibold leading-none tabular-nums"
          :class="changeTone(item.change_pct)"
        >
          {{ formatPrice(item.price) }}
        </span>
        <span class="text-xs tabular-nums" :class="changeTone(item.change_pct)">
          {{ formatPct(item.change_pct) }}
        </span>
      </div>
      <div class="mt-1 text-[11px] text-ink-3">
        <template v-if="item.fetched_at">
          {{ item.delayed ? '延迟' : '最新' }} · {{ formatSourceList([item.source]) }}
        </template>
        <template v-else>行情暂不可用</template>
      </div>
    </RouterLink>

    <div class="border-t border-line px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <div v-if="item.latest" class="flex min-w-0 items-center gap-2">
          <span
            class="inline-flex h-6 shrink-0 items-center rounded-md px-2 text-[11px] font-semibold"
            :class="ratingTone(item.latest.rating)"
          >
            {{ item.latest.rating }}
          </span>
          <span
            v-if="item.latest.position_action"
            class="inline-flex h-6 shrink-0 items-center rounded-md px-2 text-[11px] font-medium"
            :class="actionTone"
          >
            建议{{ item.latest.position_action }}
          </span>
          <span class="truncate text-[11px] text-ink-3">
            置信度 {{ item.latest.confidence }} ·
            {{ formatDateTime(item.latest.created_at) }}
          </span>
        </div>
        <span v-else class="text-[11px] text-ink-3">暂无 AI 结论</span>

        <RouterLink
          v-if="item.latest"
          :to="{ path: `/reports/${item.latest.report_id}`, query: { from: 'watchlist' } }"
          class="shrink-0 text-[11px] text-ink-3 transition-colors hover:text-ink"
        >
          查看报告 →
        </RouterLink>
        <RouterLink
          v-else
          :to="`/stock/${item.symbol}`"
          class="shrink-0 text-[11px] text-ink-3 transition-colors hover:text-ink"
        >
          去诊断 →
        </RouterLink>
      </div>

      <p
        v-if="item.latest?.summary"
        class="mt-1.5 line-clamp-2 text-[11px] leading-relaxed text-ink-2"
      >
        {{ item.latest.summary }}
      </p>

      <div class="mt-2 flex items-start justify-between gap-2">
        <div class="min-w-0 flex-1 text-[11px] text-ink-3">
          <span v-if="metaParts.length">{{ metaParts.join(' · ') }}</span>
          <span v-else>未填写成本/数量</span>
          <span v-if="pnlPct !== null" class="ml-1.5 tabular-nums" :class="pnlTone">
            浮动 {{ formatSignedPct(pnlPct) }}
            <template v-if="pnlAmount !== null">
              · {{ formatSignedAmount(pnlAmount) }}
            </template>
          </span>
          <p v-if="item.note" class="mt-0.5 truncate text-ink-2">{{ item.note }}</p>
        </div>
        <button
          type="button"
          class="shrink-0 text-[11px] text-ink-3 transition-colors hover:text-ink"
          @click="editing ? cancelEdit() : startEdit()"
        >
          {{ editing ? '收起' : '编辑' }}
        </button>
      </div>

      <div v-if="editing" class="mt-2 space-y-2">
        <input
          v-model="noteInput"
          type="text"
          maxlength="120"
          placeholder="备注（买入理由、目标价等）"
          class="h-8 w-full rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none"
        />
        <div class="grid grid-cols-2 gap-2">
          <input
            v-model="costInput"
            type="number"
            min="0"
            step="0.001"
            inputmode="decimal"
            placeholder="成本价（可选）"
            class="h-8 w-full rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none"
          />
          <input
            v-model="quantityInput"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            placeholder="数量（可选）"
            class="h-8 w-full rounded-md border border-line bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none"
          />
        </div>
        <div class="flex items-center justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-line px-2.5 py-1 text-[11px] text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
            @click="cancelEdit"
          >
            取消
          </button>
          <button
            type="button"
            class="rounded-md border border-ink bg-ink px-2.5 py-1 text-[11px] text-canvas transition-opacity hover:opacity-80 disabled:opacity-50"
            :disabled="saving"
            @click="saveEdit"
          >
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
        <p v-if="saveError" class="text-[11px] text-danger">{{ saveError }}</p>
      </div>

      <div
        v-if="batch"
        class="mt-2 flex items-center gap-2 rounded-md bg-surface px-2.5 py-1.5 text-[11px]"
      >
        <span
          class="size-1.5 shrink-0 rounded-full"
          :class="
            batch.status === 'failed'
              ? 'bg-danger'
              : batch.status === 'succeeded'
                ? 'bg-ink-2'
                : 'animate-pulse bg-ink-3'
          "
        />
        <span
          class="min-w-0 flex-1 truncate"
          :class="batch.status === 'failed' ? 'text-danger' : 'text-ink-2'"
        >
          {{ batchText }}
        </span>
      </div>
    </div>
  </article>
</template>
