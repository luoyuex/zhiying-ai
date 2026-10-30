<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import type { AdminJobDetail, AdminJobItem } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const columns = [
  { key: 'time', label: '时间' },
  { key: 'kind', label: '类型' },
  { key: 'user', label: '用户' },
  { key: 'target', label: '标的' },
  { key: 'status', label: '状态' },
  { key: 'trigger', label: '来源' },
  { key: 'duration', label: '耗时', align: 'right' as const },
  { key: 'tokens', label: 'Token', align: 'right' as const },
  { key: 'error', label: '错误' },
]

const kindOptions = [
  { label: '全部类型', value: '' },
  { label: '个股分析', value: 'analysis' },
  { label: 'AI 选股', value: 'screener' },
]
const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '排队中', value: 'queued' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'succeeded' },
  { label: '失败', value: 'failed' },
]
const triggerOptions = [
  { label: '全部来源', value: '' },
  { label: '手动', value: 'manual' },
  { label: '定时', value: 'scheduled' },
]

const q = ref('')
const kind = ref('')
const status = ref('')
const trigger = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<AdminJobItem[]>([])
const loading = ref(true)
const error = ref('')

const detailOpen = ref(false)
const detail = ref<AdminJobDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const retrying = ref(false)
const retryMessage = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.jobs({
      page: page.value,
      page_size: pageSize.value,
      kind: kind.value || undefined,
      status: status.value || undefined,
      trigger: trigger.value || undefined,
      q: q.value.trim() || undefined,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    error.value = getErrorMessage(err, '任务列表加载失败')
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

async function openDetail(job: AdminJobItem): Promise<void> {
  detailOpen.value = true
  detail.value = null
  detailError.value = ''
  retryMessage.value = ''
  detailLoading.value = true
  try {
    const { data } = await adminApi.job(job.id)
    detail.value = data
  } catch (err) {
    detailError.value = getErrorMessage(err, '任务详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function closeDetail(): void {
  detailOpen.value = false
  detail.value = null
  retryMessage.value = ''
}

async function retry(): Promise<void> {
  if (!detail.value || retrying.value) return
  retrying.value = true
  detailError.value = ''
  try {
    const { data } = await adminApi.retryJob(detail.value.id)
    retryMessage.value = `${data.message}，新任务 ${data.job_id}`
    await load()
  } catch (err) {
    detailError.value = getErrorMessage(err, '重跑失败')
  } finally {
    retrying.value = false
  }
}

function kindLabel(value: string): string {
  return value === 'screener' ? '选股' : '个股分析'
}

function targetLabel(item: AdminJobItem): string {
  if (item.kind === 'screener') return item.strategy || '—'
  return item.symbol || '—'
}

function formatDuration(value: number | null): string {
  if (value == null) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`
}

function formatMeta(meta: Record<string, unknown> | null): string {
  if (!meta) return ''
  try {
    return JSON.stringify(meta, null, 2)
  } catch {
    return ''
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && detailOpen.value) closeDetail()
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <p class="text-[13px] text-ink-3">查看任务状态、耗时与错误，失败任务可重跑</p>
      <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">任务中心</h1>
    </div>
    <div class="text-right text-[11px] text-ink-3">
      <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
        {{ total }}
      </div>
      <div class="mt-1">个任务</div>
    </div>
  </section>

  <section class="mt-6 rounded-lg border border-line bg-canvas">
    <div class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
      <Input
        v-model="q"
        class="w-full sm:w-64"
        placeholder="搜索邮箱 / 代码 / 任务 ID"
        aria-label="搜索任务"
        @keyup.enter="applyFilters"
      />
      <div class="w-32">
        <Select v-model="kind" :options="kindOptions" size="lg" />
      </div>
      <div class="w-28">
        <Select v-model="status" :options="statusOptions" size="lg" />
      </div>
      <div class="w-28">
        <Select v-model="trigger" :options="triggerOptions" size="lg" />
      </div>
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
          没有匹配的任务。
        </td>
      </tr>
      <template v-else>
        <tr
          v-for="item in items"
          :key="item.id"
          class="cursor-pointer transition-colors hover:bg-surface/60"
          tabindex="0"
          @click="openDetail(item)"
          @keydown.enter="openDetail(item)"
        >
          <td class="whitespace-nowrap px-4 py-2.5 text-[11px] text-ink-3">
            {{ formatFullDateTime(item.created_at) }}
          </td>
          <td class="px-4 py-2.5 text-ink-2">{{ kindLabel(item.kind) }}</td>
          <td class="px-4 py-2.5">
            <div class="max-w-[200px] truncate text-ink-2">
              {{ item.user_email || '—' }}
            </div>
          </td>
          <td class="px-4 py-2.5 text-ink-2">{{ targetLabel(item) }}</td>
          <td class="px-4 py-2.5"><StatusPill :value="item.status" /></td>
          <td class="px-4 py-2.5 text-[11px] text-ink-3">
            {{ item.trigger === 'scheduled' ? '定时' : '手动' }}
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-3">
            {{ formatDuration(item.duration_ms) }}
          </td>
          <td class="px-4 py-2.5 text-right tabular-nums text-ink-3">
            {{ item.token_total.toLocaleString('zh-CN') }}
          </td>
          <td class="px-4 py-2.5">
            <div class="max-w-[220px] truncate text-[11px] text-ink-3">
              {{ item.error_message || item.error_code || '—' }}
            </div>
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

  <div v-if="detailOpen" class="fixed inset-0 z-50 flex justify-end">
    <button
      type="button"
      class="absolute inset-0 bg-ink/20"
      aria-label="关闭任务详情"
      @click="closeDetail"
    />
    <aside
      class="relative flex h-full w-full max-w-[520px] flex-col overflow-y-auto border-l border-line bg-canvas shadow-pop"
    >
      <header class="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div class="min-w-0">
          <p class="text-[10px] font-medium tracking-[0.14em] text-ink-3">TASK DETAIL</p>
          <h2 class="mt-1 text-[16px] font-semibold text-ink">
            {{ detail ? kindLabel(detail.kind) : '任务详情' }}
          </h2>
          <p v-if="detail" class="mt-0.5 truncate font-mono text-[11px] text-ink-3">
            {{ detail.id }}
          </p>
        </div>
        <button
          type="button"
          class="text-sm text-ink-3 transition-colors hover:text-ink"
          aria-label="关闭"
          @click="closeDetail"
        >
          ✕
        </button>
      </header>

      <div class="flex-1 px-5 py-4">
        <p v-if="detailLoading" class="text-xs text-ink-3">加载中…</p>
        <p v-else-if="detailError" class="text-xs text-danger">{{ detailError }}</p>
        <template v-else-if="detail">
          <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-[12px]">
            <div>
              <dt class="text-[11px] text-ink-3">状态</dt>
              <dd class="mt-1"><StatusPill :value="detail.status" /></dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">来源</dt>
              <dd class="mt-1 text-ink-2">
                {{ detail.trigger === 'scheduled' ? '定时任务' : '手动提交' }}
              </dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">用户</dt>
              <dd class="mt-1 truncate text-ink-2">{{ detail.user_email || '—' }}</dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">标的</dt>
              <dd class="mt-1 text-ink-2">
                {{ detail.kind === 'screener' ? detail.strategy || '—' : detail.symbol || '—' }}
              </dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">创建时间</dt>
              <dd class="mt-1 text-ink-2">{{ formatFullDateTime(detail.created_at) }}</dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">完成时间</dt>
              <dd class="mt-1 text-ink-2">
                {{ detail.finished_at ? formatFullDateTime(detail.finished_at) : '—' }}
              </dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">耗时</dt>
              <dd class="mt-1 tabular-nums text-ink-2">
                {{ formatDuration(detail.duration_ms) }}
              </dd>
            </div>
            <div>
              <dt class="text-[11px] text-ink-3">Token</dt>
              <dd class="mt-1 tabular-nums text-ink-2">
                {{ detail.token_total.toLocaleString('zh-CN') }}
              </dd>
            </div>
            <div class="col-span-2">
              <dt class="text-[11px] text-ink-3">当前阶段</dt>
              <dd class="mt-1 text-ink-2">{{ detail.phase || '—' }}</dd>
            </div>
            <div v-if="detail.error_code || detail.error_message" class="col-span-2">
              <dt class="text-[11px] text-ink-3">错误</dt>
              <dd class="mt-1 whitespace-pre-wrap text-danger">
                {{ detail.error_message || detail.error_code }}
                <span v-if="detail.error_code" class="text-ink-3">（{{ detail.error_code }}）</span>
              </dd>
            </div>
            <div v-if="detail.report_id" class="col-span-2">
              <dt class="text-[11px] text-ink-3">关联报告</dt>
              <dd class="mt-1">
                <RouterLink
                  :to="`/reports/${detail.report_id}`"
                  target="_blank"
                  class="text-ink-2 underline underline-offset-2 hover:text-ink"
                >
                  {{ detail.report_id }}
                </RouterLink>
              </dd>
            </div>
            <div v-if="detail.meta" class="col-span-2">
              <dt class="text-[11px] text-ink-3">任务参数</dt>
              <dd class="mt-1">
                <pre class="max-h-48 overflow-auto rounded-md bg-surface p-3 text-[11px] leading-relaxed text-ink-2">{{ formatMeta(detail.meta) }}</pre>
              </dd>
            </div>
          </dl>

          <p
            v-if="retryMessage"
            class="mt-4 rounded-md bg-surface px-3 py-2 text-[11px] text-ink-2"
          >
            {{ retryMessage }}
          </p>
        </template>
      </div>

      <footer class="border-t border-line px-5 py-3">
        <p class="mb-2 text-[10px] text-ink-3">
          重跑会以该用户身份重新提交，消耗 1 次分析额度；仅失败任务可重跑。
        </p>
        <Button
          v-if="detail?.status === 'failed'"
          size="sm"
          :loading="retrying"
          @click="retry"
        >
          重跑任务
        </Button>
      </footer>
    </aside>
  </div>
</template>
