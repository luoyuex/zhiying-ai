<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Select from '@/components/ui/Select.vue'
import type { AdminUserListItem } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const router = useRouter()

const columns = [
  { key: 'email', label: '邮箱' },
  { key: 'nickname', label: '昵称' },
  { key: 'status', label: '状态' },
  { key: 'role', label: '角色' },
  { key: 'quota', label: '日额度', align: 'right' as const },
  { key: 'used', label: '今日已用', align: 'right' as const },
  { key: 'reports', label: '近 7 日报告', align: 'right' as const },
  { key: 'last_login', label: '最近登录' },
  { key: 'created', label: '注册时间' },
]

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '正常', value: 'active' },
  { label: '已封禁', value: 'banned' },
]
const roleOptions = [
  { label: '全部角色', value: '' },
  { label: '普通用户', value: 'user' },
  { label: '管理员', value: 'admin' },
]
const sortOptions = [
  { label: '注册时间', value: 'created_at' },
  { label: '最近登录', value: 'last_login_at' },
  { label: '日额度', value: 'daily_analysis_quota' },
  { label: '邮箱', value: 'email' },
]
const orderOptions = [
  { label: '倒序', value: 'desc' },
  { label: '正序', value: 'asc' },
]

const q = ref('')
const status = ref('')
const role = ref('')
const sort = ref('created_at')
const order = ref('desc')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const items = ref<AdminUserListItem[]>([])
const loading = ref(true)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await adminApi.users({
      page: page.value,
      page_size: pageSize.value,
      q: q.value.trim() || undefined,
      status: status.value || undefined,
      role: role.value || undefined,
      sort: sort.value,
      order: order.value,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    error.value = getErrorMessage(err, '用户列表加载失败')
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

function openUser(id: string): void {
  void router.push(`/admin/users/${id}`)
}

watch([status, role, sort, order], () => {
  applyFilters()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">搜索账号、查看额度与登录状态</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">用户与额度</h1>
      </div>
      <div class="text-right text-[11px] text-ink-3">
        <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
          {{ total }}
        </div>
        <div class="mt-1">个账号</div>
      </div>
    </section>

    <section class="mt-6 rounded-lg border border-line bg-canvas">
      <div class="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Input
          v-model="q"
          class="w-full sm:w-64"
          placeholder="搜索邮箱或昵称"
          aria-label="搜索用户"
          @keyup.enter="applyFilters"
        />
        <div class="w-32">
          <Select v-model="status" :options="statusOptions" size="lg" />
        </div>
        <div class="w-32">
          <Select v-model="role" :options="roleOptions" size="lg" />
        </div>
        <div class="w-32">
          <Select v-model="sort" :options="sortOptions" size="lg" />
        </div>
        <div class="w-24">
          <Select v-model="order" :options="orderOptions" size="lg" />
        </div>
        <Button @click="applyFilters">筛选</Button>
      </div>

      <p
        v-if="items.length && items[0].quota_override_active"
        class="border-b border-line bg-surface/60 px-4 py-2 text-[11px] text-warn"
      >
        全局额度覆盖已开启：所有用户实际额度为 {{ items[0].effective_quota }} 次/日，用户单独额度暂不生效。
      </p>

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
            没有匹配的用户。
          </td>
        </tr>
        <template v-else>
        <tr
          v-for="item in items"
          :key="item.id"
          class="cursor-pointer transition-colors hover:bg-surface/60"
          tabindex="0"
          @click="openUser(item.id)"
          @keydown.enter="openUser(item.id)"
        >
          <td class="px-4 py-3">
            <div class="max-w-[240px] truncate text-ink">{{ item.email }}</div>
          </td>
          <td class="px-4 py-3 text-ink-2">{{ item.nickname }}</td>
          <td class="px-4 py-3">
            <StatusPill :value="item.status" />
          </td>
          <td class="px-4 py-3">
            <StatusPill :value="item.role" />
          </td>
          <td class="px-4 py-3 text-right tabular-nums text-ink">
            {{ item.daily_analysis_quota }}
          </td>
          <td class="px-4 py-3 text-right tabular-nums text-ink-2">
            {{ item.today_used }}
          </td>
          <td class="px-4 py-3 text-right tabular-nums text-ink-2">
            {{ item.reports_7d }}
          </td>
          <td class="px-4 py-3 text-[11px] text-ink-3">
            {{ item.last_login_at ? formatFullDateTime(item.last_login_at) : '—' }}
          </td>
          <td class="px-4 py-3 text-[11px] text-ink-3">
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

    <p class="mt-3 text-[11px] text-ink-3">
      后台只允许调整每日额度与账号状态；角色变更请使用管理员命令。
    </p>
</template>
