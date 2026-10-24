<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import type { AdminAuditLogItem } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const columns = [
  { key: 'created', label: '时间' },
  { key: 'admin', label: '管理员' },
  { key: 'action', label: '动作' },
  { key: 'target', label: '目标' },
  { key: 'result', label: '结果' },
  { key: 'ip', label: 'IP' },
]

const ACTION_LABELS: Record<string, string> = {
  'user.update': '调整用户',
  'user.reset_quota': '重置额度',
  'user.revoke_sessions': '强制下线',
  'admin.create': '创建管理员',
  'admin.promote': '提升管理员',
  'admin.demote': '取消管理员',
}

const actionOptions = [
  { label: '全部动作', value: '' },
  { label: '调整用户', value: 'user.update' },
  { label: '重置额度', value: 'user.reset_quota' },
  { label: '强制下线', value: 'user.revoke_sessions' },
  { label: '创建管理员', value: 'admin.create' },
  { label: '提升管理员', value: 'admin.promote' },
  { label: '取消管理员', value: 'admin.demote' },
]

const targetOptions = [
  { label: '全部目标', value: '' },
  { label: '用户', value: 'user' },
]

const action = ref('')
const targetType = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<AdminAuditLogItem[]>([])
const expandedId = ref<number | null>(null)
const loading = ref(true)
const error = ref('')

function actionLabel(value: string): string {
  return ACTION_LABELS[value] ?? value
}

function targetText(item: AdminAuditLogItem): string {
  if (!item.target_type && !item.target_id) return '—'
  const suffix = item.target_id ? item.target_id.slice(0, 8) : ''
  return [item.target_type, suffix].filter(Boolean).join(' · ')
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  expandedId.value = null
  try {
    const { data } = await adminApi.auditLogs({
      page: page.value,
      page_size: pageSize.value,
      action: action.value.trim() || undefined,
      target_type: targetType.value.trim() || undefined,
      date_from: dateFrom.value
        ? new Date(`${dateFrom.value}T00:00:00`).toISOString()
        : undefined,
      date_to: dateTo.value
        ? new Date(`${dateTo.value}T23:59:59`).toISOString()
        : undefined,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    error.value = getErrorMessage(err, '审计日志加载失败')
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

function toggle(id: number): void {
  expandedId.value = expandedId.value === id ? null : id
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">管理员写操作与敏感查看，只追加不删除</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">审计日志</h1>
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
        <div class="w-36">
          <Select v-model="action" :options="actionOptions" size="lg" />
        </div>
        <div class="w-28">
          <Select v-model="targetType" :options="targetOptions" size="lg" />
        </div>
        <div class="w-40">
          <Input v-model="dateFrom" type="date" aria-label="开始日期" />
        </div>
        <span class="text-[11px] text-ink-3">至</span>
        <div class="w-40">
          <Input v-model="dateTo" type="date" aria-label="结束日期" />
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
            没有匹配的审计记录。
          </td>
        </tr>
        <template v-else>
          <template v-for="item in items" :key="item.id">
            <tr
              class="cursor-pointer transition-colors hover:bg-surface/60"
              tabindex="0"
              @click="toggle(item.id)"
              @keydown.enter="toggle(item.id)"
            >
              <td class="px-4 py-3 text-[11px] text-ink-3">
                {{ formatFullDateTime(item.created_at) }}
              </td>
              <td class="max-w-[200px] truncate px-4 py-3 text-[11px] text-ink-2">
                {{ item.admin_email || '命令行' }}
              </td>
              <td class="px-4 py-3 text-ink">{{ actionLabel(item.action) }}</td>
              <td class="px-4 py-3 font-mono text-[11px] text-ink-3">
                {{ targetText(item) }}
              </td>
              <td class="px-4 py-3">
                <StatusPill
                  :value="item.result === 'success' ? 'succeeded' : 'failed'"
                  :label="item.result === 'success' ? '成功' : '失败'"
                />
              </td>
              <td class="px-4 py-3 font-mono text-[11px] text-ink-3">
                {{ item.ip || '—' }}
              </td>
            </tr>
            <tr v-if="expandedId === item.id" class="bg-surface/60">
              <td :colspan="columns.length" class="px-4 py-4">
                <div class="grid gap-4 lg:grid-cols-2">
                  <div>
                    <div class="text-[11px] font-medium text-ink-3">变更前</div>
                    <pre class="mt-1 max-h-56 overflow-auto rounded bg-canvas p-3 text-[11px] leading-relaxed text-ink-2">{{
                      item.before ? JSON.stringify(item.before, null, 2) : '无'
                    }}</pre>
                  </div>
                  <div>
                    <div class="text-[11px] font-medium text-ink-3">变更后</div>
                    <pre class="mt-1 max-h-56 overflow-auto rounded bg-canvas p-3 text-[11px] leading-relaxed text-ink-2">{{
                      item.after ? JSON.stringify(item.after, null, 2) : '无'
                    }}</pre>
                  </div>
                </div>
                <div class="mt-3 space-y-1 text-[11px] text-ink-3">
                  <div>客户端：{{ item.ua || '—' }}</div>
                  <div v-if="item.note">备注：{{ item.note }}</div>
                </div>
              </td>
            </tr>
          </template>
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
