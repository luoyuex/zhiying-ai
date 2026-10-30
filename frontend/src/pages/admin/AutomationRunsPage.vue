<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import type { AdminAutomationRunItem } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const columns = [
  { key: 'date', label: '执行日期' },
  { key: 'user', label: '用户' },
  { key: 'line', label: '任务线' },
  { key: 'status', label: '结果' },
  { key: 'enqueued', label: '入队数', align: 'right' as const },
  { key: 'reason', label: '说明' },
  { key: 'created', label: '记录时间' },
]

const lineOptions = [
  { label: '全部任务', value: '' },
  { label: '定时选股', value: 'screener' },
  { label: '定时分析', value: 'analysis' },
]
const statusOptions = [
  { label: '全部结果', value: '' },
  { label: '已入队', value: 'enqueued' },
  { label: '无任务', value: 'no_tasks' },
  { label: '额度不足', value: 'skipped_quota' },
  { label: '失败', value: 'failed' },
]

function today(): string {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const runDate = ref(today())
const line = ref('')
const status = ref('')
const q = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<AdminAutomationRunItem[]>([])
const loading = ref(true)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.automationRuns({
      page: page.value,
      page_size: pageSize.value,
      run_date: runDate.value || undefined,
      line: line.value || undefined,
      status: status.value || undefined,
      q: q.value.trim() || undefined,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    error.value = getErrorMessage(err, '执行记录加载失败')
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  page.value = 1
  void load()
}

function onPageChange(value: number): void {
  if (value === page.value) return
  page.value = value
  void load()
}

function onPageSizeChange(value: number): void {
  pageSize.value = value
  page.value = 1
  void load()
}

function lineLabel(value: string): string {
  return value === 'screener' ? '定时选股' : '定时分析'
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="text-[13px] text-ink-3">
        按用户与任务线记录每日执行结果，跳过的任务会写明原因
      </p>
      <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">定时执行记录</h1>
    </div>
    <div class="text-right text-[11px] text-ink-3">
      <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
        {{ total }}
      </div>
      <div class="mt-1">条记录</div>
    </div>
  </section>

  <section class="mt-6 rounded-lg border border-line bg-canvas">
    <div class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
      <input
        v-model="runDate"
        type="date"
        aria-label="执行日期"
        class="h-9 rounded-md border border-line bg-canvas px-2.5 text-xs text-ink focus:border-line-strong focus:outline-none"
        @change="applyFilters"
      />
      <div class="w-32">
        <Select v-model="line" :options="lineOptions" size="lg" />
      </div>
      <div class="w-32">
        <Select v-model="status" :options="statusOptions" size="lg" />
      </div>
      <Input
        v-model="q"
        class="w-full sm:w-56"
        placeholder="搜索用户邮箱"
        aria-label="搜索用户邮箱"
        @keyup.enter="applyFilters"
      />
      <Button @click="applyFilters">筛选</Button>
    </div>

    <div v-if="error" class="border-b border-line px-4 py-3">
      <p class="text-xs text-danger">{{ error }}</p>
      <button
        type="button"
        class="mt-2 text-xs text-ink-2 underline underline-offset-2"
        @click="load"
      >
        重新加载
      </button>
    </div>

    <DataTable :columns="columns">
      <tr v-if="loading">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          加载中…
        </td>
      </tr>
      <tr v-else-if="!items.length">
        <td :colspan="columns.length" class="px-4 py-12 text-center text-xs text-ink-3">
          当天没有执行记录。任务按用户设置的时间触发，未到点或未启用的用户不会产生记录。
        </td>
      </tr>
      <template v-else>
        <tr v-for="item in items" :key="item.id" class="transition-colors hover:bg-surface/60">
          <td class="whitespace-nowrap px-4 py-2.5 tabular-nums text-ink-2">
            {{ item.run_date }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[240px] truncate text-ink-2">
              {{ item.user_email || '—' }}
            </div>
          </td>
          <td class="px-4 py-2.5 text-ink-2">{{ lineLabel(item.line) }}</td>
          <td class="px-4 py-2.5"><StatusPill :value="item.status" /></td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-2">
            {{ item.enqueued }}
          </td>
          <td class="px-4 py-2.5 text-[11px] text-ink-3">{{ item.reason || '—' }}</td>
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
        </tr>
      </template>
    </DataTable>

    <Pagination
      :page="page"
      :page-size="pageSize"
      :total="total"
      @update:page="onPageChange"
      @update:page-size="onPageSizeChange"
    />
  </section>
</template>
