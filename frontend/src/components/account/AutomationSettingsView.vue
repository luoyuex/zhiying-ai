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
const notifyEmail = ref('')
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
  notifyEmail.value = data.notify_email || auth.user?.email || ''
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
      notify_email: notifyEmail.value.trim() || null,
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
        <label class="flex cursor-pointer items-center justify-between gap-4">
          <span>
            <span class="block text-[13px] font-medium text-ink">邮件通知</span>
            <span class="mt-0.5 block text-[11px] text-ink-3">
              可选；开启后把定时任务结果汇总发到指定邮箱，不开启不影响任务执行
            </span>
          </span>
          <input v-model="emailNotifyEnabled" type="checkbox" class="peer sr-only" />
          <span
            class="relative h-5 w-9 shrink-0 rounded-full bg-ink-3/30 transition-colors after:absolute after:left-0.5 after:top-0.5 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:bg-ink peer-checked:after:translate-x-4"
            aria-hidden="true"
          />
        </label>
        <div v-if="emailNotifyEnabled" class="mt-4 border-t border-line pt-4">
          <label class="flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-3">
            <span>接收地址</span>
            <input
              v-model.trim="notifyEmail"
              type="email"
              autocomplete="email"
              placeholder="name@example.com"
              class="w-60 rounded-md border border-line bg-canvas px-2 py-1.5 text-xs text-ink outline-none focus:border-ink-3"
            />
          </label>
          <p class="mt-2 text-[10px] leading-relaxed text-ink-3">
            同一天同一项任务只发一封；多个策略与自选股结果合并发送。任务量较大时，会先发送已完成部分。
          </p>
        </div>
      </section>

      <p v-if="error" class="mt-4 text-xs text-danger">{{ error }}</p>
      <p v-if="success" class="mt-4 text-xs text-down">{{ success }}</p>

      <Button class="mt-5" size="sm" :loading="saving" @click="save">保存设置</Button>
    </template>
  </div>
</template>
