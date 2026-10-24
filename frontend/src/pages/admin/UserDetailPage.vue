<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { adminApi } from '@/api/admin'
import DataTable from '@/components/admin/DataTable.vue'
import Pagination from '@/components/admin/Pagination.vue'
import StatCard from '@/components/admin/StatCard.vue'
import StatusPill from '@/components/admin/StatusPill.vue'
import Button from '@/components/ui/Button.vue'
import Field from '@/components/ui/Field.vue'
import Input from '@/components/ui/Input.vue'
import type { AdminSessionItem, AdminUserDetail } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const route = useRoute()

const STRATEGY_LABELS: Record<string, string> = {
  main_force: '主力追踪',
  low_price_bull: '低价寻宝',
  small_cap: '小盘精选',
  profit_growth: '业绩高增',
  value_stock: '价值洼地',
}

const userId = computed(() => String(route.params.id ?? ''))
const detail = ref<AdminUserDetail | null>(null)
const sessions = ref<AdminSessionItem[]>([])
const sessionTotal = ref(0)
const sessionPage = ref(1)
const sessionPageSize = 20
const quotaInput = ref('5')
const loading = ref(true)
const error = ref('')
const actionLoading = ref(false)
const actionMessage = ref('')
const actionError = ref('')

const sessionColumns = [
  { key: 'ip', label: 'IP' },
  { key: 'ua', label: '客户端' },
  { key: 'created', label: '登录时间' },
  { key: 'expires', label: '过期时间' },
  { key: 'status', label: '状态' },
]

function strategyLabel(strategy: string): string {
  return STRATEGY_LABELS[strategy] ?? strategy
}

async function load(): Promise<void> {
  if (!userId.value) return
  loading.value = true
  error.value = ''
  actionMessage.value = ''
  actionError.value = ''
  try {
    const [detailResponse, sessionResponse] = await Promise.all([
      adminApi.user(userId.value),
      adminApi.sessions(userId.value, { page: 1, page_size: sessionPageSize }),
    ])
    detail.value = detailResponse.data
    quotaInput.value = String(detailResponse.data.daily_analysis_quota)
    sessions.value = sessionResponse.data.items
    sessionTotal.value = sessionResponse.data.total
    sessionPage.value = 1
  } catch (err) {
    error.value = getErrorMessage(err, '用户详情加载失败')
  } finally {
    loading.value = false
  }
}

async function loadSessions(): Promise<void> {
  if (!userId.value) return
  try {
    const { data } = await adminApi.sessions(userId.value, {
      page: sessionPage.value,
      page_size: sessionPageSize,
    })
    sessions.value = data.items
    sessionTotal.value = data.total
  } catch (err) {
    actionError.value = getErrorMessage(err, '会话列表加载失败')
  }
}

function onSessionPageChange(value: number): void {
  sessionPage.value = value
  void loadSessions()
}

async function saveQuota(): Promise<void> {
  if (!detail.value) return
  const value = Number(quotaInput.value)
  if (!Number.isInteger(value) || value < 0 || value > 100) {
    actionError.value = '每日额度需要是 0–100 的整数'
    return
  }
  actionLoading.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const { data } = await adminApi.updateUser(detail.value.id, {
      daily_analysis_quota: value,
    })
    detail.value = data
    quotaInput.value = String(data.daily_analysis_quota)
    actionMessage.value = '每日额度已更新'
  } catch (err) {
    actionError.value = getErrorMessage(err, '额度更新失败')
  } finally {
    actionLoading.value = false
  }
}

async function toggleStatus(): Promise<void> {
  if (!detail.value) return
  actionLoading.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const next = detail.value.status === 'active' ? 'banned' : 'active'
    const { data } = await adminApi.updateUser(detail.value.id, { status: next })
    detail.value = data
    actionMessage.value = next === 'active' ? '账号已解封' : '账号已封禁'
  } catch (err) {
    actionError.value = getErrorMessage(err, '账号状态更新失败')
  } finally {
    actionLoading.value = false
  }
}

async function resetQuota(): Promise<void> {
  if (!detail.value) return
  actionLoading.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const { data } = await adminApi.resetQuota(detail.value.id)
    actionMessage.value = `${data.message}（重置前已用 ${data.used_before} 次）`
    const { data: refreshed } = await adminApi.user(detail.value.id)
    detail.value = refreshed
    quotaInput.value = String(refreshed.daily_analysis_quota)
  } catch (err) {
    actionError.value = getErrorMessage(err, '重置额度失败')
  } finally {
    actionLoading.value = false
  }
}

async function revokeSessions(): Promise<void> {
  if (!detail.value) return
  actionLoading.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const { data } = await adminApi.revokeSessions(detail.value.id)
    actionMessage.value = data.message
    await loadSessions()
  } catch (err) {
    actionError.value = getErrorMessage(err, '强制下线失败')
  } finally {
    actionLoading.value = false
  }
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <RouterLink
    to="/admin/users"
      class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
    >
      <span aria-hidden="true">←</span>
      用户列表
    </RouterLink>

    <div v-if="loading" class="mt-6 space-y-4">
      <div class="h-8 w-56 animate-pulse rounded bg-surface-2" />
      <div class="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <div v-for="index in 4" :key="index" class="h-28 animate-pulse rounded-lg bg-surface-2" />
      </div>
      <div class="h-64 animate-pulse rounded-lg bg-surface-2" />
    </div>

    <div v-else-if="error" class="mt-6 rounded-lg border border-line bg-canvas px-4 py-10 text-center">
      <p class="text-sm text-danger">{{ error }}</p>
      <Button variant="secondary" size="sm" class="mt-3" @click="load">重新加载</Button>
    </div>

    <template v-else-if="detail">
      <section class="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div class="min-w-0">
          <p class="text-[13px] text-ink-3">{{ detail.email }}</p>
          <h1 class="mt-1 truncate text-[24px] font-semibold tracking-tight text-ink">
            {{ detail.nickname }}
          </h1>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <StatusPill :value="detail.role" />
            <StatusPill :value="detail.status" />
            <span
              v-if="detail.last_login_at"
              class="text-[11px] text-ink-3"
            >
              最近登录 {{ formatFullDateTime(detail.last_login_at) }}
            </span>
          </div>
        </div>
      </section>

      <section class="mt-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="每日额度"
          :value="detail.effective_quota"
          :hint="detail.quota_override_active ? '全局额度覆盖生效中' : `账号设置 ${detail.daily_analysis_quota} 次`"
        />
        <StatCard
          label="今日已用"
          :value="detail.today_used"
          hint="按 Asia/Shanghai 自然日"
        />
        <StatCard
          label="分析报告"
          :value="detail.counts.reports"
          :hint="`近 7 日 ${detail.counts.reports_7d} 份`"
        />
        <StatCard
          label="自选股"
          :value="detail.counts.watchlist_items"
          :hint="`选股 ${detail.counts.screener_records} · 组合诊断 ${detail.counts.portfolio_diagnoses}`"
        />
      </section>

      <p
        v-if="detail.quota_override_active"
        class="mt-3 rounded-md bg-surface px-3 py-2 text-[11px] text-warn"
      >
        全局额度覆盖已开启，实际额度为 {{ detail.effective_quota }} 次；调整用户单独额度暂不生效。
      </p>

      <section class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="rounded-lg border border-line bg-canvas p-5">
          <h2 class="text-sm font-semibold text-ink">账号操作</h2>
          <div class="mt-4">
            <Field label="每日额度" hint="0–100">
              <div class="flex items-center gap-2">
                <div class="w-32">
                  <Input v-model="quotaInput" type="number" inputmode="numeric" />
                </div>
                <Button :loading="actionLoading" @click="saveQuota">保存</Button>
              </div>
            </Field>
          </div>

          <div class="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-4">
            <button
              v-if="detail.status === 'active'"
              type="button"
              :disabled="actionLoading || detail.role === 'admin'"
              class="h-8 rounded-md border border-line-strong px-3 text-[13px] text-danger transition-colors hover:bg-danger-soft disabled:cursor-not-allowed disabled:opacity-50"
              @click="toggleStatus"
            >
              封禁账号
            </button>
            <Button
              v-else
              variant="secondary"
              size="sm"
              :loading="actionLoading"
              @click="toggleStatus"
            >
              解封账号
            </Button>
            <Button
              variant="secondary"
              size="sm"
              :loading="actionLoading"
              @click="resetQuota"
            >
              重置今日额度
            </Button>
            <Button
              variant="secondary"
              size="sm"
              :loading="actionLoading"
              @click="revokeSessions"
            >
              强制下线
            </Button>
          </div>
          <p v-if="detail.role === 'admin'" class="mt-2 text-[11px] text-ink-3">
            管理员账号不能在这里封禁；如需停用请使用管理员命令。
          </p>
          <p v-if="actionMessage" class="mt-3 text-[11px] text-ink-2">{{ actionMessage }}</p>
          <p v-if="actionError" class="mt-3 text-[11px] text-danger">{{ actionError }}</p>
        </div>

        <div class="rounded-lg border border-line bg-canvas p-5">
          <h2 class="text-sm font-semibold text-ink">定时任务</h2>
          <div class="mt-4 space-y-3 text-[13px]">
            <div class="flex items-center justify-between">
              <span class="text-ink-2">每日选股</span>
              <span class="text-ink">
                {{ detail.automation.screener_enabled ? '已开启' : '未开启' }}
                <span class="ml-2 text-[11px] text-ink-3 tabular-nums">
                  {{ String(detail.automation.screener_run_hour).padStart(2, '0') }}:{{
                    String(detail.automation.screener_run_minute).padStart(2, '0')
                  }}
                </span>
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-ink-2">每日分析自选</span>
              <span class="text-ink">
                {{ detail.automation.analysis_enabled ? '已开启' : '未开启' }}
                <span class="ml-2 text-[11px] text-ink-3 tabular-nums">
                  {{ String(detail.automation.analysis_run_hour).padStart(2, '0') }}:{{
                    String(detail.automation.analysis_run_minute).padStart(2, '0')
                  }}
                </span>
              </span>
            </div>
            <div class="border-t border-line pt-3">
              <div class="text-[11px] text-ink-3">启用的选股策略</div>
              <div v-if="detail.automation.enabled_strategies.length" class="mt-2 flex flex-wrap gap-1.5">
                <span
                  v-for="strategy in detail.automation.enabled_strategies"
                  :key="strategy"
                  class="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2"
                >
                  {{ strategyLabel(strategy) }}
                </span>
              </div>
              <p v-else class="mt-2 text-[11px] text-ink-3">没有启用策略。</p>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-6 rounded-lg border border-line bg-canvas">
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 class="text-sm font-semibold text-ink">最近报告</h2>
          <span class="text-[11px] text-ink-3">最近 5 份</span>
        </div>
        <div v-if="detail.recent_reports.length" class="divide-y divide-line">
          <div
            v-for="report in detail.recent_reports"
            :key="report.id"
            class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-xs"
          >
            <span class="font-medium text-ink">{{ report.symbol }}</span>
            <span class="text-ink-2">{{ report.name }}</span>
            <span class="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">
              {{ report.rating }} · {{ report.confidence }}
            </span>
            <span class="ml-auto text-[11px] text-ink-3">
              {{ formatFullDateTime(report.created_at) }}
            </span>
          </div>
        </div>
        <p v-else class="px-4 py-10 text-center text-xs text-ink-3">
          该用户还没有分析报告。
        </p>
      </section>

      <section class="mt-6 rounded-lg border border-line bg-canvas">
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 class="text-sm font-semibold text-ink">登录会话</h2>
          <span class="text-[11px] text-ink-3">最近 {{ sessionTotal }} 条</span>
        </div>
        <DataTable :columns="sessionColumns">
          <tr v-if="!sessions.length">
            <td :colspan="sessionColumns.length" class="px-4 py-10 text-center text-xs text-ink-3">
              还没有登录会话。
            </td>
          </tr>
          <template v-else>
          <tr v-for="session in sessions" :key="session.id">
            <td class="px-4 py-3 font-mono text-[11px] text-ink-2">
              {{ session.ip || '—' }}
            </td>
            <td class="max-w-[320px] truncate px-4 py-3 text-[11px] text-ink-3">
              {{ session.user_agent || '—' }}
            </td>
            <td class="px-4 py-3 text-[11px] text-ink-3">
              {{ formatFullDateTime(session.created_at) }}
            </td>
            <td class="px-4 py-3 text-[11px] text-ink-3">
              {{ formatFullDateTime(session.expires_at) }}
            </td>
            <td class="px-4 py-3">
              <StatusPill
                :value="session.active ? 'active' : 'expired'"
                :label="session.active ? '有效' : '已失效'"
              />
            </td>
          </tr>
          </template>
        </DataTable>
        <Pagination
          :page="sessionPage"
          :page-size="sessionPageSize"
          :total="sessionTotal"
          @update:page="onSessionPageChange"
        />
      </section>

      <details class="mt-6 rounded-lg border border-line bg-canvas px-4 py-3">
        <summary class="cursor-pointer text-xs text-ink-3">账号时间与数据量</summary>
        <dl class="mt-3 grid gap-2 text-[11px] text-ink-3 sm:grid-cols-2">
          <div class="flex justify-between gap-4">
            <dt>注册时间</dt>
            <dd class="text-ink-2">{{ formatFullDateTime(detail.created_at) }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt>资料更新时间</dt>
            <dd class="text-ink-2">{{ formatFullDateTime(detail.updated_at) }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt>最近登录</dt>
            <dd class="text-ink-2">
              {{ detail.last_login_at ? formatFullDateTime(detail.last_login_at) : '—' }}
            </dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt>选股记录</dt>
            <dd class="text-ink-2">{{ detail.counts.screener_records }}</dd>
          </div>
          <div class="flex justify-between gap-4">
            <dt>组合诊断</dt>
            <dd class="text-ink-2">{{ detail.counts.portfolio_diagnoses }}</dd>
          </div>
        </dl>
      </details>
    </template>
</template>
