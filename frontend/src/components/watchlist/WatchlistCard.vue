<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  watchlistApi,
  type PriceAlert,
  type PositionChangeEntry,
  type WatchlistEntry,
  type WatchlistJobState,
} from '@/api/watchlist'
import { automationApi } from '@/api/automation'
import {
  notifyPriceAlertsChanged,
  usePriceAlertsVersion,
} from '@/composables/usePriceAlertsSync'
import { useAuthStore } from '@/stores/auth'
import { getErrorMessage } from '@/utils/errors'
import { formatSourceList } from '@/utils/market'
import { formatDateTime, ratingChangeBadge, ratingTone } from '@/utils/report'

const props = defineProps<{
  item: WatchlistEntry
  selected: boolean
  batch: WatchlistJobState | null
  sortable?: boolean
  dragging?: boolean
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

// 调仓记录：展开时按需加载
const historyOpen = ref(false)
const history = ref<PositionChangeEntry[] | null>(null)
const historyLoading = ref(false)
const historyError = ref('')

// 价位提醒：展开时按需加载
const alertPanelOpen = ref(false)
const alerts = ref<PriceAlert[] | null>(null)
const alertsLoading = ref(false)
const alertError = ref('')
const alertDirection = ref<'above' | 'below'>('above')
const alertPriceInput = ref('')
const alertSaving = ref(false)
// 统一通知设置：打开提醒面板时按需加载实际收件地址与 Webhook 状态
const notifyTarget = ref<string | null>(null)
const webhookReady = ref(false)
const notifyLoaded = ref(false)
const alertVersion = usePriceAlertsVersion()
const auth = useAuthStore()

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

const latestChange = computed(() =>
  ratingChangeBadge(props.item.latest?.rating_change, props.item.latest?.prev_rating),
)

function directionLabel(direction: string): string {
  return direction === 'above' ? '涨到' : '跌破'
}

function alertLabel(alert: PriceAlert): string {
  if (alert.kind === 'entry') return '入场'
  if (alert.kind === 'take_profit') return '止盈'
  if (alert.kind === 'stop_loss') return '止损'
  return directionLabel(alert.direction)
}

function alertThreshold(alert: PriceAlert): string {
  if (alert.kind === 'entry' || alert.kind === 'stop_loss') {
    return `≤ ${alert.target_price.toFixed(2)}`
  }
  if (alert.kind === 'take_profit') {
    return `≥ ${alert.target_price.toFixed(2)}`
  }
  return alert.target_price.toFixed(2)
}

const symbolAlerts = computed(() =>
  (alerts.value ?? []).filter((alert) => alert.symbol === props.item.symbol),
)
const activeAlerts = computed(() => symbolAlerts.value.filter((alert) => alert.status === 'active'))
const triggeredAlerts = computed(() =>
  symbolAlerts.value.filter((alert) => alert.status === 'triggered'),
)

async function loadAlerts(force = false): Promise<void> {
  if (alerts.value !== null && !force) return
  alertsLoading.value = true
  alertError.value = ''
  try {
    const { data } = await watchlistApi.alerts()
    alerts.value = data
  } catch (err) {
    alertError.value = getErrorMessage(err, '提醒加载失败')
  } finally {
    alertsLoading.value = false
  }
}

async function toggleAlertPanel(): Promise<void> {
  alertPanelOpen.value = !alertPanelOpen.value
  if (alertPanelOpen.value) {
    await Promise.all([loadAlerts(), loadNotifyTarget()])
  }
}

async function loadNotifyTarget(): Promise<void> {
  if (notifyLoaded.value) return
  try {
    const { data } = await automationApi.getSettings()
    notifyTarget.value = data.price_alert_email_enabled
      ? data.notify_email || auth.user?.email || null
      : null
    webhookReady.value = Boolean(
      data.price_alert_webhook_enabled && data.webhook_url,
    )
  } catch {
    // 设置加载失败时不在卡片上展示通知渠道提示
    notifyTarget.value = null
    webhookReady.value = false
  } finally {
    notifyLoaded.value = true
  }
}

async function refreshAlerts(): Promise<void> {
  try {
    const { data } = await watchlistApi.alerts()
    alerts.value = data
  } catch {
    // 刷新失败保留旧数据
  }
}

async function saveAlert(): Promise<void> {
  if (alertSaving.value) return
  const price = Number(String(alertPriceInput.value).trim())
  if (!Number.isFinite(price) || price <= 0) {
    alertError.value = '请输入大于 0 的目标价'
    return
  }
  alertSaving.value = true
  alertError.value = ''
  try {
    await watchlistApi.createAlert(props.item.symbol, alertDirection.value, price)
    alertPriceInput.value = ''
    notifyPriceAlertsChanged()
  } catch (err) {
    alertError.value = getErrorMessage(err, '提醒创建失败')
  } finally {
    alertSaving.value = false
  }
}

async function removeAlert(id: string): Promise<void> {
  try {
    await watchlistApi.cancelAlert(id)
    notifyPriceAlertsChanged()
  } catch (err) {
    alertError.value = getErrorMessage(err, '取消失败')
  }
}

// 其它位置（汇总面板 / 报告页）修改提醒后，已展开的面板同步刷新
watch(alertVersion, () => {
  if (alertPanelOpen.value) void refreshAlerts()
})

async function toggleHistory(): Promise<void> {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value || history.value !== null) return
  historyLoading.value = true
  historyError.value = ''
  try {
    const { data } = await watchlistApi.positionHistory(props.item.symbol)
    history.value = data
  } catch (err) {
    historyError.value = getErrorMessage(err, '调仓记录加载失败')
  } finally {
    historyLoading.value = false
  }
}

function historyText(entry: PositionChangeEntry): string {
  const parts: string[] = []
  if (entry.old_cost_price !== entry.new_cost_price) {
    parts.push(
      `成本 ${entry.old_cost_price === null ? '空' : entry.old_cost_price.toFixed(2)} → ${
        entry.new_cost_price === null ? '空' : entry.new_cost_price.toFixed(2)
      }`,
    )
  }
  if (entry.old_quantity !== entry.new_quantity) {
    parts.push(`数量 ${entry.old_quantity ?? '空'} → ${entry.new_quantity ?? '空'}`)
  }
  return parts.length ? parts.join(' · ') : '持仓信息更新'
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
    // 成本/数量可能已变化，下次展开调仓记录时重新拉取
    history.value = null
    if (historyOpen.value) await toggleHistory()
  } catch (err) {
    saveError.value = getErrorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <article
    :data-wl-card="item.symbol"
    class="relative rounded-lg border bg-canvas transition-[opacity,border-color,box-shadow]"
    :class="[
      selected ? 'border-line-strong' : 'border-line hover:border-line-strong',
      dragging ? 'opacity-60 shadow-md' : '',
    ]"
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
      v-if="sortable"
      type="button"
      class="absolute right-9 top-2 flex size-6 cursor-grab touch-none items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink active:cursor-grabbing"
      title="拖动调整顺序"
      :aria-label="`拖动 ${item.name} 调整顺序`"
      :data-wl-grip="item.symbol"
    >
      <svg class="size-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <circle cx="9" cy="6" r="1.5" />
        <circle cx="15" cy="6" r="1.5" />
        <circle cx="9" cy="12" r="1.5" />
        <circle cx="15" cy="12" r="1.5" />
        <circle cx="9" cy="18" r="1.5" />
        <circle cx="15" cy="18" r="1.5" />
      </svg>
    </button>

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

    <RouterLink :to="`/stock/${item.symbol}`" class="block p-4 pl-10 pr-16">
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
            v-if="latestChange"
            class="inline-flex h-6 shrink-0 items-center rounded-md px-2 text-[11px] font-medium"
            :class="latestChange.tone"
          >
            {{ latestChange.label }}
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
        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="flex items-center gap-1 text-[11px] transition-colors"
            :class="activeAlerts.length ? 'text-ink' : 'text-ink-3 hover:text-ink'"
            @click="toggleAlertPanel"
          >
            <svg
              class="size-3"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              aria-hidden="true"
            >
              <path
                d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8M10.3 21a2 2 0 0 0 3.4 0"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            提醒{{ activeAlerts.length ? ` ${activeAlerts.length}` : '' }}
          </button>
          <button
            type="button"
            class="text-[11px] text-ink-3 transition-colors hover:text-ink"
            @click="editing ? cancelEdit() : startEdit()"
          >
            {{ editing ? '收起' : '编辑' }}
          </button>
        </div>
      </div>

      <div v-if="alertPanelOpen" class="mt-2 space-y-2 rounded-md bg-surface px-2.5 py-2">
        <div class="flex items-center justify-between gap-2">
          <span class="text-[11px] font-medium text-ink">价位提醒</span>
          <span class="text-[10px] text-ink-3">交易时段内检查，触发一次后自动结束</span>
        </div>
        <p v-if="notifyLoaded" class="text-[10px] leading-relaxed text-ink-3">
          <template v-if="notifyTarget || webhookReady">
            触发后
            <template v-if="notifyTarget">发送邮件至 {{ notifyTarget }}</template>
            <template v-if="notifyTarget && webhookReady">，</template>
            <template v-if="webhookReady">同时发送 Webhook</template>
            （个人中心 → 定时与通知 可改）
          </template>
          <template v-else>
            价位提醒通知已关闭，触发记录仍会保留；可在个人中心 → 定时与通知 开启
          </template>
        </p>
        <p v-if="alertsLoading" class="text-[11px] text-ink-3">加载中…</p>
        <template v-else>
          <div v-if="activeAlerts.length" class="space-y-1">
            <div
              v-for="alert in activeAlerts"
              :key="alert.id"
              class="flex items-center justify-between gap-2 text-[11px]"
            >
              <span class="text-ink-2">
                {{ alertLabel(alert) }}
                <span class="tabular-nums">{{ alertThreshold(alert) }}</span>
              </span>
              <button
                type="button"
                class="text-ink-3 transition-colors hover:text-danger"
                @click="removeAlert(alert.id)"
              >
                取消
              </button>
            </div>
          </div>
          <p v-else class="text-[11px] text-ink-3">暂无生效中的提醒</p>

          <div v-if="triggeredAlerts.length" class="space-y-1 border-t border-line pt-1.5">
            <p class="text-[10px] text-ink-3">已触发（最近 {{ Math.min(triggeredAlerts.length, 5) }} 条）</p>
            <div
              v-for="alert in triggeredAlerts.slice(0, 5)"
              :key="alert.id"
              class="flex items-center justify-between gap-2 text-[11px] text-ink-2"
            >
              <span>
                {{ alertLabel(alert) }}
                {{ alertThreshold(alert) }} · 触发价
                {{ alert.triggered_price === null ? '—' : alert.triggered_price.toFixed(2) }}
              </span>
              <span class="shrink-0 text-ink-3">
                {{ alert.triggered_at ? formatDateTime(alert.triggered_at) : '' }}
              </span>
            </div>
          </div>

          <div class="flex items-center gap-1.5">
            <div class="flex overflow-hidden rounded-md border border-line">
              <button
                type="button"
                class="px-2 py-1 text-[11px] transition-colors"
                :class="alertDirection === 'above' ? 'bg-ink text-canvas' : 'bg-canvas text-ink-2'"
                @click="alertDirection = 'above'"
              >
                涨到
              </button>
              <button
                type="button"
                class="px-2 py-1 text-[11px] transition-colors"
                :class="alertDirection === 'below' ? 'bg-ink text-canvas' : 'bg-canvas text-ink-2'"
                @click="alertDirection = 'below'"
              >
                跌破
              </button>
            </div>
            <input
              v-model="alertPriceInput"
              type="number"
              min="0"
              step="0.01"
              inputmode="decimal"
              placeholder="目标价"
              class="h-7 w-20 rounded-md border border-line bg-canvas px-2 text-[11px] text-ink placeholder:text-ink-3 focus:border-line-strong focus:outline-none"
              @keyup.enter="saveAlert"
            />
            <button
              type="button"
              class="ml-auto rounded-md border border-ink bg-ink px-2.5 py-1 text-[11px] text-canvas transition-opacity hover:opacity-80 disabled:opacity-50"
              :disabled="alertSaving"
              @click="saveAlert"
            >
              {{ alertSaving ? '保存中…' : '添加提醒' }}
            </button>
          </div>
          <p v-if="alertError" class="text-[11px] text-danger">{{ alertError }}</p>
        </template>
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
        <div class="border-t border-line pt-2">
          <button
            type="button"
            class="text-[11px] text-ink-3 transition-colors hover:text-ink"
            @click="toggleHistory"
          >
            {{ historyOpen ? '收起调仓记录' : '调仓记录' }}
          </button>
          <div v-if="historyOpen" class="mt-1.5 space-y-1">
            <p v-if="historyLoading" class="text-[11px] text-ink-3">加载中…</p>
            <p v-else-if="historyError" class="text-[11px] text-danger">{{ historyError }}</p>
            <p v-else-if="!history?.length" class="text-[11px] text-ink-3">暂无调仓记录</p>
            <div
              v-for="entry in history ?? []"
              :key="entry.id"
              class="flex items-center justify-between gap-2 text-[11px] text-ink-2"
            >
              <span>{{ historyText(entry) }}</span>
              <span class="shrink-0 text-ink-3">{{ formatDateTime(entry.created_at) }}</span>
            </div>
          </div>
        </div>
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
