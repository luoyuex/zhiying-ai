<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { adminApi } from '@/api/admin'
import StatCard from '@/components/admin/StatCard.vue'
import Button from '@/components/ui/Button.vue'
import type { AdminOverview } from '@/types/admin'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const range = ref<'today' | '7d'>('today')
const data = ref<AdminOverview | null>(null)
const loading = ref(true)
const error = ref('')

const rangeLabel = computed(() => (range.value === 'today' ? '今日' : '近 7 日'))
const costText = computed(() =>
  data.value ? `¥${data.value.cost_estimate.toFixed(2)}` : '—',
)
const tokenText = computed(() =>
  data.value ? data.value.tokens_total.toLocaleString('zh-CN') : '—',
)
const successText = computed(() =>
  data.value?.success_rate == null ? '—' : `${data.value.success_rate}%`,
)
const dataSinceText = computed(() =>
  data.value?.data_since ? formatFullDateTime(data.value.data_since) : '',
)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data: payload } = await adminApi.overview(range.value)
    data.value = payload
  } catch (err) {
    error.value = getErrorMessage(err, '运营总览加载失败')
  } finally {
    loading.value = false
  }
}

function setRange(next: 'today' | '7d'): void {
  if (range.value === next) return
  range.value = next
  void load()
}

function kindLabel(kind: string): string {
  return kind === 'screener' ? '选股' : '个股分析'
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">只读本地数据，不主动请求行情源</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">运营总览</h1>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-md bg-surface-2 p-0.5 text-xs">
          <button
            type="button"
            class="rounded px-2.5 py-1 transition-colors"
            :class="range === 'today' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-3 hover:text-ink'"
            @click="setRange('today')"
          >
            今日
          </button>
          <button
            type="button"
            class="rounded px-2.5 py-1 transition-colors"
            :class="range === '7d' ? 'bg-canvas text-ink shadow-sm' : 'text-ink-3 hover:text-ink'"
            @click="setRange('7d')"
          >
            近 7 日
          </button>
        </div>
        <Button variant="secondary" size="sm" :loading="loading" @click="load">
          刷新
        </Button>
      </div>
    </section>

    <div v-if="loading && !data" class="mt-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
      <div v-for="index in 4" :key="index" class="rounded-lg border border-line bg-canvas p-5">
        <div class="h-3 w-20 animate-pulse rounded bg-surface-2" />
        <div class="mt-3 h-7 w-24 animate-pulse rounded bg-surface-2" />
        <div class="mt-3 h-3 w-32 animate-pulse rounded bg-surface-2" />
      </div>
    </div>

    <div v-else-if="error" class="mt-6 rounded-lg border border-line bg-canvas px-4 py-10 text-center">
      <p class="text-sm text-danger">{{ error }}</p>
      <Button variant="secondary" size="sm" class="mt-3" @click="load">重新加载</Button>
    </div>

    <template v-else-if="data">
      <section class="mt-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard
          label="新增用户"
          :value="data.new_users"
          :hint="`${rangeLabel}注册`"
        />
        <StatCard
          label="活跃用户"
          :value="data.active_users"
          :hint="`${rangeLabel}有报告或 AI 任务`"
        />
        <StatCard
          label="AI 任务"
          :value="data.jobs_total"
          :hint="`成功 ${data.jobs_succeeded} · 失败 ${data.jobs_failed} · 成功率 ${successText}`"
        />
        <StatCard
          label="估算成本"
          :value="costText"
          :hint="`${tokenText} tokens · 未配置单价的模型不计入`"
        />
      </section>

      <section class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="rounded-lg border border-line bg-canvas p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-ink">运行状态</h2>
            <span
              class="inline-flex items-center gap-1.5 text-[11px]"
              :class="data.worker_alive ? 'text-ink-2' : 'text-danger'"
            >
              <span
                class="size-1.5 rounded-full"
                :class="data.worker_alive ? 'bg-down' : 'bg-danger'"
              />
              Worker {{ data.worker_alive ? '在线' : '离线' }}
            </span>
          </div>
          <div class="mt-4 grid grid-cols-2 gap-x-6 gap-y-4">
            <div>
              <div class="text-[11px] text-ink-3">队列等待</div>
              <div class="mt-1 text-lg font-semibold tabular-nums text-ink">
                {{ data.queue_depth }}
              </div>
            </div>
            <div>
              <div class="text-[11px] text-ink-3">运行中任务</div>
              <div class="mt-1 text-lg font-semibold tabular-nums text-ink">
                {{ data.running_jobs }}
              </div>
            </div>
            <div>
              <div class="text-[11px] text-ink-3">熔断打开</div>
              <div
                class="mt-1 text-lg font-semibold tabular-nums"
                :class="data.open_circuits ? 'text-warn' : 'text-ink'"
              >
                {{ data.open_circuits }}
              </div>
            </div>
            <div>
              <div class="text-[11px] text-ink-3">代理健康</div>
              <div class="mt-1 text-lg font-semibold tabular-nums text-ink">
                {{ data.proxy_healthy }}
                <span class="text-xs font-normal text-ink-3">/ {{ data.proxy_total }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-line bg-canvas p-5">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-ink">额度消耗 Top 5</h2>
            <span class="text-[11px] text-ink-3">{{ rangeLabel }}</span>
          </div>
          <p
            v-if="data.quota_override_active"
            class="mt-2 text-[11px] text-warn"
          >
            全局额度覆盖已开启，用户单独额度暂不生效。
          </p>
          <div v-if="data.top_quota_users.length" class="mt-3 space-y-3">
            <div v-for="item in data.top_quota_users" :key="item.user_id">
              <div class="flex items-center justify-between gap-3 text-xs">
                <span class="truncate text-ink-2">{{ item.email }}</span>
                <span class="shrink-0 tabular-nums text-ink-3">
                  {{ item.used }} / {{ item.quota }}
                </span>
              </div>
              <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div
                  class="h-full rounded-full bg-ink-2"
                  :style="{
                    width: `${item.quota ? Math.min(100, (item.used / item.quota) * 100) : 0}%`,
                  }"
                />
              </div>
            </div>
          </div>
          <p v-else class="mt-6 text-xs text-ink-3">今天还没有用户消耗额度。</p>
        </div>
      </section>

      <section class="mt-6 rounded-lg border border-line bg-canvas">
        <div class="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 class="text-sm font-semibold text-ink">最近失败任务</h2>
          <span class="text-[11px] text-ink-3">最近 5 条</span>
        </div>
        <div v-if="data.recent_failures.length" class="divide-y divide-line">
          <div
            v-for="item in data.recent_failures"
            :key="item.job_id"
            class="px-4 py-3"
          >
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span class="font-medium text-ink">{{ kindLabel(item.kind) }}</span>
              <span v-if="item.symbol" class="text-ink-2">{{ item.symbol }}</span>
              <span v-if="item.strategy" class="text-ink-2">{{ item.strategy }}</span>
              <span class="text-ink-3">{{ item.user_email || '未知用户' }}</span>
              <span class="ml-auto text-[11px] text-ink-3">
                {{ formatFullDateTime(item.created_at) }}
              </span>
            </div>
            <p class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-3">
              {{ item.error_code || '任务失败' }} · {{ item.error_message || '未提供错误信息' }}
            </p>
          </div>
        </div>
        <p v-else class="px-4 py-10 text-center text-xs text-ink-3">
          最近没有失败任务。
        </p>
      </section>

      <p class="mt-4 text-[11px] text-ink-3">
        <template v-if="dataSinceText">
          成本与任务统计自 {{ dataSinceText }} 起，之前的历史无法回填。
        </template>
        <template v-else>
          还没有调用或任务记录；产生第一次 AI 任务后开始统计。
        </template>
      </p>
    </template>
</template>
