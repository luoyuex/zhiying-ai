<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatCard from '@/components/admin/StatCard.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import type { AdminCostCallItem, AdminCostSummary } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const days = ref(14)
const summary = ref<AdminCostSummary | null>(null)
const loadingSummary = ref(true)
const summaryError = ref('')

const columns = [
  { key: 'time', label: '时间' },
  { key: 'user', label: '用户' },
  { key: 'task', label: '任务' },
  { key: 'model', label: '模型' },
  { key: 'tokens', label: 'Token', align: 'right' as const },
  { key: 'duration', label: '耗时', align: 'right' as const },
  { key: 'status', label: '状态' },
  { key: 'cost', label: '成本', align: 'right' as const },
]

const calls = ref<AdminCostCallItem[]>([])
const callsTotal = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loadingCalls = ref(false)
const callsError = ref('')
const q = ref('')
const task = ref('')
const status = ref('')

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'error' },
]
const taskOptions = computed(() => [
  { label: '全部任务', value: '' },
  ...(summary.value?.top_tasks ?? []).map((item) => ({
    label: item.task,
    value: item.task,
  })),
])

const costText = computed(() =>
  summary.value ? `¥${summary.value.cost.toFixed(2)}` : '—',
)
const tokenText = computed(() =>
  summary.value ? summary.value.tokens.toLocaleString('zh-CN') : '—',
)
const successText = computed(() =>
  summary.value?.success_rate == null ? '—' : `${summary.value.success_rate}%`,
)
const callText = computed(() =>
  summary.value ? summary.value.calls.toLocaleString('zh-CN') : '—',
)
const dataSinceText = computed(() =>
  summary.value?.data_since ? formatFullDateTime(summary.value.data_since) : '',
)
const maxDailyCost = computed(() =>
  Math.max(0.0001, ...(summary.value?.daily ?? []).map((item) => item.cost)),
)

function shortDate(value: string): string {
  return value.slice(5)
}

async function loadSummary(): Promise<void> {
  loadingSummary.value = true
  summaryError.value = ''
  try {
    const { data } = await adminApi.costSummary(days.value)
    summary.value = data
  } catch (err) {
    summaryError.value = getErrorMessage(err, '成本汇总加载失败')
  } finally {
    loadingSummary.value = false
  }
}

async function loadCalls(): Promise<void> {
  loadingCalls.value = true
  callsError.value = ''
  try {
    const { data } = await adminApi.costCalls({
      page: page.value,
      page_size: pageSize.value,
      task: task.value || undefined,
      status: status.value || undefined,
      q: q.value.trim() || undefined,
    })
    calls.value = data.items
    callsTotal.value = data.total
  } catch (err) {
    callsError.value = getErrorMessage(err, '调用明细加载失败')
  } finally {
    loadingCalls.value = false
  }
}

function setDays(next: number): void {
  if (days.value === next) return
  days.value = next
  void loadSummary()
}

function applyFilters(): void {
  page.value = 1
  void loadCalls()
}

function onPageChange(value: number): void {
  if (value === page.value) return
  page.value = value
  void loadCalls()
}

function onPageSizeChange(value: number): void {
  pageSize.value = value
  page.value = 1
  void loadCalls()
}

function formatCost(value: number | null): string {
  return value == null ? '—' : `¥${value.toFixed(4)}`
}

function formatDuration(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`
}

onMounted(() => {
  void loadSummary()
  void loadCalls()
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="text-[13px] text-ink-3">按 LLM 调用流水聚合，成本为估算值</p>
      <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">成本日报</h1>
    </div>
    <div class="flex rounded-md bg-surface-2 p-0.5 text-xs">
      <button
        v-for="option in [7, 14, 30]"
        :key="option"
        type="button"
        class="rounded px-2.5 py-1 transition-colors"
        :class="days === option ? 'bg-canvas text-ink shadow-sm' : 'text-ink-3 hover:text-ink'"
        @click="setDays(option)"
      >
        近 {{ option }} 天
      </button>
    </div>
  </section>

  <p v-if="summaryError" class="mt-4 text-xs text-danger">{{ summaryError }}</p>

  <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <StatCard label="调用次数" :value="callText" :hint="`成功率 ${successText}`" />
    <StatCard label="估算成本" :value="costText" hint="按模型单价估算" />
    <StatCard label="Token 总量" :value="tokenText" hint="prompt + completion" />
    <StatCard
      label="未定价调用"
      :value="summary?.unpriced_calls ?? '—'"
      hint="模型未配置价格，成本计为 0"
      :tone="summary?.unpriced_calls ? 'warn' : 'default'"
    />
  </div>

  <p v-if="dataSinceText" class="mt-2 text-[11px] text-ink-3">
    调用台账从 {{ dataSinceText }} 开始记录，更早的数据无法回填。
  </p>

  <div class="mt-5 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
    <section class="rounded-lg border border-line bg-canvas p-5">
      <div class="flex items-baseline justify-between">
        <h2 class="text-[13px] font-medium text-ink">每日估算成本</h2>
        <span class="text-[11px] text-ink-3">峰值 ¥{{ maxDailyCost.toFixed(2) }}</span>
      </div>
      <div v-if="loadingSummary" class="mt-4 h-32 animate-pulse rounded bg-surface" />
      <div v-else class="mt-4 flex h-32 items-end gap-1">
        <div
          v-for="item in summary?.daily ?? []"
          :key="item.date"
          class="group relative flex h-full flex-1 flex-col items-center justify-end gap-1"
          :title="`${item.date} · ${item.calls} 次 · ¥${item.cost.toFixed(4)}`"
        >
          <div
            class="w-full rounded-t-sm transition-colors"
            :class="item.failures ? 'bg-warn/70 group-hover:bg-warn' : 'bg-ink/70 group-hover:bg-ink'"
            :style="{ height: `${Math.max(2, (item.cost / maxDailyCost) * 100)}%` }"
          />
          <span class="text-[9px] text-ink-3">{{ shortDate(item.date) }}</span>
        </div>
      </div>
    </section>

    <section class="rounded-lg border border-line bg-canvas p-5">
      <h2 class="text-[13px] font-medium text-ink">任务类型成本</h2>
      <div v-if="loadingSummary" class="mt-4 space-y-2">
        <div v-for="i in 5" :key="i" class="h-6 animate-pulse rounded bg-surface" />
      </div>
      <div v-else-if="!summary?.top_tasks.length" class="mt-4 text-[11px] text-ink-3">
        暂无调用记录。
      </div>
      <ul v-else class="mt-3 divide-y divide-line">
        <li
          v-for="item in summary.top_tasks"
          :key="item.task"
          class="flex items-center justify-between gap-3 py-2 text-[12px]"
        >
          <span class="truncate text-ink-2">{{ item.task }}</span>
          <span class="shrink-0 tabular-nums text-ink">
            ¥{{ item.cost.toFixed(3) }}
            <span class="ml-1 text-[11px] text-ink-3">{{ item.calls }} 次</span>
          </span>
        </li>
      </ul>
      <div v-if="summary?.top_users.length" class="mt-4 border-t border-line pt-3">
        <h3 class="text-[11px] font-medium text-ink-3">成本 Top 用户</h3>
        <ul class="mt-1.5 space-y-1.5">
          <li
            v-for="item in summary.top_users"
            :key="item.user_id ?? item.email"
            class="flex items-center justify-between gap-3 text-[11px]"
          >
            <span class="truncate text-ink-2">{{ item.email || '未知用户' }}</span>
            <span class="shrink-0 tabular-nums text-ink">¥{{ item.cost.toFixed(3) }}</span>
          </li>
        </ul>
      </div>
    </section>
  </div>

  <section class="mt-5 rounded-lg border border-line bg-canvas">
    <div class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
      <Input
        v-model="q"
        class="w-full sm:w-56"
        placeholder="搜索用户邮箱"
        aria-label="搜索用户邮箱"
        @keyup.enter="applyFilters"
      />
      <div class="w-36">
        <Select v-model="task" :options="taskOptions" size="lg" />
      </div>
      <div class="w-28">
        <Select v-model="status" :options="statusOptions" size="lg" />
      </div>
      <Button @click="applyFilters">筛选</Button>
    </div>

    <div v-if="callsError" class="border-b border-line px-4 py-3">
      <p class="text-xs text-danger">{{ callsError }}</p>
      <button
        type="button"
        class="mt-2 text-xs text-ink-2 underline underline-offset-2"
        @click="loadCalls"
      >
        重新加载
      </button>
    </div>

    <DataTable :columns="columns">
      <tr v-if="loadingCalls">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          加载中…
        </td>
      </tr>
      <tr v-else-if="!calls.length">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          没有匹配的调用记录。
        </td>
      </tr>
      <template v-else>
        <tr v-for="item in calls" :key="item.id" class="transition-colors hover:bg-surface/60">
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">
              {{ item.user_email || '—' }}
            </div>
          </td>
          <td class="px-4 py-2.5 text-ink-2">{{ item.task }}</td>
          <td class="px-4 py-2.5 text-[11px] text-ink-3">{{ item.model }}</td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-2">
            {{ (item.prompt_tokens + item.completion_tokens).toLocaleString('zh-CN') }}
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-3">
            {{ formatDuration(item.duration_ms) }}
          </td>
          <td class="px-4 py-2.5">
            <span
              class="rounded px-1.5 py-0.5 text-[11px] font-medium"
              :class="
                item.status === 'success'
                  ? 'bg-surface-2 text-ink-2'
                  : 'bg-danger-soft text-danger'
              "
            >
              {{ item.status === 'success' ? '成功' : item.error_code || '失败' }}
            </span>
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink">
            {{ formatCost(item.cost) }}
          </td>
        </tr>
      </template>
    </DataTable>

    <Pagination
      :page="page"
      :page-size="pageSize"
      :total="callsTotal"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
    />
  </section>
</template>
