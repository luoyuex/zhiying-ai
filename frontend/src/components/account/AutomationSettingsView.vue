<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  automationApi,
  type AutomationSettings,
  type AutomationSettingsUpdate,
  type AutomationStrategyId,
} from '@/api/automation'
import Button from '@/components/ui/Button.vue'
import {
  STRATEGY_FORM_SPECS,
  mergeFilters,
  type StrategyFormSpec,
} from './automationSpecs'
import { getErrorMessage } from '@/utils/errors'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const screenerEnabled = ref(false)
const analysisEnabled = ref(false)
const screenerTime = ref('17:35')
const analysisTime = ref('17:35')
const enabledStrategies = ref<AutomationStrategyId[]>([])
const formValues = ref<Record<string, Record<string, number | boolean | string | null>>>({})
const emailNotifyEnabled = ref(false)
const priceAlertEmailEnabled = ref(true)
const notifyEmail = ref('')
const webhookNotifyEnabled = ref(false)
const priceAlertWebhookEnabled = ref(true)
const webhookType = ref<'dingtalk' | 'feishu'>('dingtalk')
const webhookUrl = ref('')
const webhookKeyword = ref('')
const screenerExpanded = ref(false)

const screenerSummary = computed(() => {
  const names = STRATEGY_FORM_SPECS.filter((spec) =>
    enabledStrategies.value.includes(spec.id),
  ).map((spec) => spec.name)
  const strategyText = names.length ? names.join('、') : '未启用任何策略'
  return `每个交易日 ${screenerTime.value} 执行 · ${strategyText}`
})

function onScreenerEnabledChange(): void {
  screenerExpanded.value = screenerEnabled.value
}

function toggleScreenerExpanded(): void {
  screenerExpanded.value = !screenerExpanded.value
}

function specById(id: AutomationStrategyId): StrategyFormSpec {
  return STRATEGY_FORM_SPECS.find((item) => item.id === id) as StrategyFormSpec
}

function toTime(hour: number, minute: number): string {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function splitTime(value: string): { hour: number; minute: number } {
  const [hour, minute] = value.split(':').map(Number)
  return {
    hour: Number.isFinite(hour) ? hour : 17,
    minute: Number.isFinite(minute) ? minute : 35,
  }
}

function applySettings(data: AutomationSettings): void {
  screenerEnabled.value = data.screener_enabled
  analysisEnabled.value = data.analysis_enabled
  screenerTime.value = toTime(data.screener_run_hour, data.screener_run_minute)
  analysisTime.value = toTime(data.analysis_run_hour, data.analysis_run_minute)
  enabledStrategies.value = Object.entries(data.strategy_settings ?? {})
    .filter(([, setting]) => setting?.enabled)
    .map(([id]) => id as AutomationStrategyId)
  const values: Record<string, Record<string, number | boolean | string | null>> = {}
  for (const spec of STRATEGY_FORM_SPECS) {
    values[spec.id] = mergeFilters(spec, data.strategy_settings?.[spec.id]?.filters)
  }
  formValues.value = values
  screenerExpanded.value = false
  emailNotifyEnabled.value = data.email_notify_enabled
  priceAlertEmailEnabled.value = data.price_alert_email_enabled
  notifyEmail.value = data.notify_email || auth.user?.email || ''
  webhookNotifyEnabled.value = data.webhook_notify_enabled
  priceAlertWebhookEnabled.value = data.price_alert_webhook_enabled
  webhookType.value = data.webhook_type === 'feishu' ? 'feishu' : 'dingtalk'
  webhookUrl.value = data.webhook_url || ''
  webhookKeyword.value = data.webhook_keyword || ''
}

function webhookHostAllowed(url: string): boolean {
  try {
    const parsed = new URL(url)
    return (
      parsed.protocol === 'https:' &&
      ['oapi.dingtalk.com', 'open.feishu.cn', 'open.larksuite.com'].includes(
        parsed.hostname,
      )
    )
  } catch {
    return false
  }
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const { data } = await automationApi.getSettings()
    applySettings(data)
  } catch (err) {
    error.value = getErrorMessage(err, '定时任务设置加载失败')
  } finally {
    loading.value = false
  }
})

async function save(): Promise<void> {
  error.value = ''
  success.value = ''
  if (emailNotifyEnabled.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(notifyEmail.value.trim())) {
    error.value = '请填写有效的邮件接收地址'
    return
  }
  const webhookUrlValue = webhookUrl.value.trim()
  if (webhookNotifyEnabled.value && !webhookUrlValue) {
    error.value = '开启 Webhook 通知时必须填写机器人地址'
    return
  }
  if (webhookUrlValue && !webhookHostAllowed(webhookUrlValue)) {
    error.value = 'Webhook 只支持钉钉或飞书官方 https 机器人地址'
    return
  }
  saving.value = true
  const strategy_settings: AutomationSettingsUpdate['strategy_settings'] = {}
  for (const spec of STRATEGY_FORM_SPECS) {
    if (!enabledStrategies.value.includes(spec.id)) continue
    strategy_settings[spec.id] = {
      enabled: true,
      filters: { ...formValues.value[spec.id] },
    }
  }
  try {
    const screener = splitTime(screenerTime.value)
    const analysis = splitTime(analysisTime.value)
    const { data } = await automationApi.updateSettings({
      screener_enabled: screenerEnabled.value,
      analysis_enabled: analysisEnabled.value,
      screener_run_hour: screener.hour,
      screener_run_minute: screener.minute,
      analysis_run_hour: analysis.hour,
      analysis_run_minute: analysis.minute,
      strategy_settings,
      email_notify_enabled: emailNotifyEnabled.value,
      price_alert_email_enabled: priceAlertEmailEnabled.value,
      notify_email: notifyEmail.value.trim() || null,
      webhook_notify_enabled: webhookNotifyEnabled.value,
      price_alert_webhook_enabled: priceAlertWebhookEnabled.value,
      webhook_type: webhookType.value,
      webhook_url: webhookUrlValue || null,
      webhook_keyword: webhookKeyword.value.trim() || null,
    })
    applySettings(data)
    success.value = '定时任务设置已保存'
  } catch (err) {
    error.value = getErrorMessage(err, '定时任务设置保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl">
    <p class="text-xs leading-relaxed text-ink-3">
      开启后，每个交易日由系统在你设定的时间自动执行并写入历史记录；额度不足或 AI
      未配置时自动跳过。实际执行可能比设定时间晚至多 5 分钟。
    </p>

    <div v-if="loading" class="mt-6 space-y-3">
      <div class="h-14 animate-pulse rounded-md bg-surface" />
      <div class="h-14 animate-pulse rounded-md bg-surface" />
    </div>

    <template v-else>
      <section class="mt-6 rounded-lg border border-line bg-surface p-4">
        <div class="flex items-center justify-between gap-4">
          <div class="min-w-0">
            <span class="block text-[13px] font-medium text-ink">每日定时选股</span>
            <span class="mt-0.5 block text-[11px] text-ink-3">
              {{
                screenerEnabled && !screenerExpanded
                  ? screenerSummary
                  : '为下方启用的策略自动跑一轮 AI 选股并落历史记录'
              }}
            </span>
          </div>
          <div class="flex shrink-0 items-center gap-3">
            <button
              v-if="screenerEnabled"
              type="button"
              class="flex items-center gap-1 text-[11px] text-ink-3 transition-colors hover:text-ink"
              :aria-expanded="screenerExpanded"
              @click="toggleScreenerExpanded"
            >
              {{ screenerExpanded ? '收起' : '展开设置' }}
              <svg
                class="size-3.5 transition-transform duration-150"
                :class="screenerExpanded ? 'rotate-180' : ''"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
            <label class="cursor-pointer">
              <input
                v-model="screenerEnabled"
                type="checkbox"
                class="peer sr-only"
                aria-label="开启每日定时选股"
                @change="onScreenerEnabledChange"
              />
              <span
                class="relative block h-5 w-9 shrink-0 rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
                aria-hidden="true"
              />
            </label>
          </div>
        </div>

        <div
          v-if="screenerEnabled && screenerExpanded"
          class="mt-4 space-y-2 border-t border-line pt-4"
        >
          <label class="flex items-center justify-between gap-3 text-[11px] text-ink-3">
            <span>每个交易日执行时间</span>
            <input
              v-model="screenerTime"
              type="time"
              class="rounded-md border border-line bg-canvas px-2 py-1 text-xs tabular-nums text-ink outline-none focus:border-ink-3"
            />
          </label>
          <div
            v-for="spec in STRATEGY_FORM_SPECS"
            :key="spec.id"
            class="rounded-md bg-canvas"
          >
            <label class="flex cursor-pointer items-center justify-between gap-3 px-3 py-2.5">
              <span class="min-w-0">
                <span class="block text-xs font-medium text-ink">{{ spec.name }}</span>
                <span class="mt-0.5 block truncate text-[11px] text-ink-3">
                  {{ spec.description }}
                </span>
              </span>
              <input
                v-model="enabledStrategies"
                type="checkbox"
                :value="spec.id"
                class="size-4 shrink-0 accent-[var(--color-ink)]"
              />
            </label>
            <div
              v-if="enabledStrategies.includes(spec.id)"
              class="grid gap-x-6 gap-y-3 border-t border-line px-3 py-3 sm:grid-cols-2"
            >
              <label
                v-for="field in specById(spec.id).fields"
                :key="field.key"
                class="flex items-center justify-between gap-3 text-[11px] text-ink-3"
              >
                <span class="shrink-0">{{ field.label }}</span>
                <span v-if="field.type === 'boolean'" class="flex items-center">
                  <input
                    v-model="formValues[spec.id][field.key]"
                    type="checkbox"
                    class="size-3.5 accent-[var(--color-ink)]"
                  />
                </span>
                <span v-else-if="field.type === 'select'" class="flex items-center">
                  <select
                    v-model="formValues[spec.id][field.key]"
                    class="rounded-md border border-line bg-canvas px-2 py-1 text-xs text-ink outline-none focus:border-ink-3"
                  >
                    <option
                      v-for="option in field.options"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </span>
                <span v-else class="flex items-center gap-1">
                  <input
                    v-model.number="formValues[spec.id][field.key]"
                    type="number"
                    :min="field.min"
                    :max="field.max"
                    :step="field.step ?? 0.1"
                    class="w-20 rounded-md border border-line bg-canvas px-2 py-1 text-right text-xs tabular-nums text-ink outline-none focus:border-ink-3"
                  />
                  <span v-if="field.suffix" class="w-4">{{ field.suffix }}</span>
                </span>
              </label>
            </div>
          </div>
          <p class="text-[10px] text-ink-3">未启用任何策略时，定时选股不会执行。</p>
        </div>
      </section>

      <section class="mt-3 rounded-lg border border-line bg-surface p-4">
        <label class="flex cursor-pointer items-center justify-between gap-4">
          <span>
            <span class="block text-[13px] font-medium text-ink">每日定时分析自选股</span>
            <span class="mt-0.5 block text-[11px] text-ink-3">
              自动分析自选列表全部股票；按额度逐只执行，耗尽即停
            </span>
          </span>
          <input v-model="analysisEnabled" type="checkbox" class="peer sr-only" />
          <span
            class="relative h-5 w-9 shrink-0 rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
            aria-hidden="true"
          />
        </label>
        <div v-if="analysisEnabled" class="mt-4 border-t border-line pt-4">
          <label class="flex items-center justify-between gap-3 text-[11px] text-ink-3">
            <span>每个交易日执行时间</span>
            <input
              v-model="analysisTime"
              type="time"
              class="rounded-md border border-line bg-canvas px-2 py-1 text-xs tabular-nums text-ink outline-none focus:border-ink-3"
            />
          </label>
        </div>
      </section>

      <section class="mt-3 rounded-lg border border-line bg-surface p-4">
        <div>
          <span class="block text-[13px] font-medium text-ink">消息通知</span>
          <span class="mt-0.5 block text-[11px] text-ink-3">
            定时汇总与价位提醒可分别选择邮件、Webhook 或两者同时发送；关闭渠道不影响任务与提醒记录
          </span>
        </div>

        <div class="mt-4 border-t border-line pt-3">
          <div class="grid grid-cols-[1fr_auto_auto] items-center gap-x-4 text-[10px] text-ink-3">
            <span>事件</span>
            <span class="w-9 text-center">邮件</span>
            <span class="w-9 text-center">Webhook</span>
          </div>

          <div class="mt-2 grid grid-cols-[1fr_auto_auto] items-center gap-x-4 border-t border-line pt-3">
            <span>
              <span class="block text-[12px] font-medium text-ink">定时任务结果汇总</span>
              <span class="mt-0.5 block text-[11px] text-ink-3">
                每天任务跑完后，把选股与分析结果合并发送
              </span>
            </span>
            <label class="flex w-9 justify-center">
              <input v-model="emailNotifyEnabled" type="checkbox" class="peer sr-only" />
              <span
                class="relative block h-5 w-9 shrink-0 cursor-pointer rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
                aria-hidden="true"
              />
            </label>
            <label class="flex w-9 justify-center">
              <input v-model="webhookNotifyEnabled" type="checkbox" class="peer sr-only" />
              <span
                class="relative block h-5 w-9 shrink-0 cursor-pointer rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
                aria-hidden="true"
              />
            </label>
          </div>

          <div class="mt-3 grid grid-cols-[1fr_auto_auto] items-center gap-x-4 border-t border-line pt-3">
            <span>
              <span class="block text-[12px] font-medium text-ink">关键价位提醒</span>
              <span class="mt-0.5 block text-[11px] text-ink-3">
                入场、止盈、止损或自定义目标价触发时发送（默认开启）
              </span>
            </span>
            <label class="flex w-9 justify-center">
              <input v-model="priceAlertEmailEnabled" type="checkbox" class="peer sr-only" />
              <span
                class="relative block h-5 w-9 shrink-0 cursor-pointer rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
                aria-hidden="true"
              />
            </label>
            <label class="flex w-9 justify-center">
              <input v-model="priceAlertWebhookEnabled" type="checkbox" class="peer sr-only" />
              <span
                class="relative block h-5 w-9 shrink-0 cursor-pointer rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
                aria-hidden="true"
              />
            </label>
          </div>
        </div>

        <div class="mt-4 border-t border-line pt-3">
          <label class="flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-3">
            <span>邮件接收地址</span>
            <input
              v-model.trim="notifyEmail"
              type="email"
              autocomplete="email"
              placeholder="默认发送到账号邮箱"
              class="w-60 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink outline-none focus:border-ink-3"
            />
          </label>
          <p class="mt-2 text-[10px] leading-relaxed text-ink-3">
            定时任务汇总需填写地址；价位提醒留空时发送到账号邮箱（{{ auth.user?.email || '—' }}）。
            同一天同一项任务只发一封，多个结果合并发送。
          </p>
        </div>

        <div class="mt-4 border-t border-line pt-3">
          <div class="flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-3">
            <span>Webhook 机器人</span>
            <div class="flex flex-wrap items-center gap-2">
              <select
                v-model="webhookType"
                class="rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink outline-none focus:border-ink-3"
              >
                <option value="dingtalk">钉钉</option>
                <option value="feishu">飞书</option>
              </select>
              <input
                v-model.trim="webhookUrl"
                type="url"
                autocomplete="off"
                placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
                class="w-72 max-w-full rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink outline-none focus:border-ink-3"
              />
            </div>
          </div>
          <label
            v-if="webhookType === 'dingtalk'"
            class="mt-2 flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-3"
          >
            <span>自定义关键词</span>
            <input
              v-model.trim="webhookKeyword"
              type="text"
              maxlength="64"
              placeholder="机器人安全设置中的关键词（可选）"
              class="w-72 max-w-full rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink outline-none focus:border-ink-3"
            />
          </label>
          <p class="mt-2 text-[10px] leading-relaxed text-ink-3">
            仅支持钉钉、飞书官方机器人地址。钉钉用“自定义关键词”校验时请填写关键词；
            飞书若开启签名校验，当前不支持，请改用关键词或 IP 白名单。
          </p>
        </div>
      </section>

      <p v-if="error" class="mt-4 text-xs text-danger">{{ error }}</p>
      <p v-if="success" class="mt-4 text-xs text-down">{{ success }}</p>

      <Button class="mt-5" size="sm" :loading="saving" @click="save">保存设置</Button>
    </template>
  </div>
</template>
