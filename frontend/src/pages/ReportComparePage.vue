<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import type { AIAnalysisResponse } from '@/api/ai'
import { reportsApi, type ReportDetail } from '@/api/reports'
import AppShell from '@/components/layout/AppShell.vue'
import AnalystRadar from '@/components/report/AnalystRadar.vue'
import { getErrorMessage } from '@/utils/errors'
import { formatFullDateTime } from '@/utils/report'

const route = useRoute()

const AXES = [
  { key: 'technical', label: '技术面' },
  { key: 'fundamental', label: '基本面' },
  { key: 'fund_flow', label: '资金面' },
  { key: 'sentiment', label: '情绪' },
  { key: 'risk', label: '风险' },
  { key: 'news', label: '新闻' },
]

const newer = ref<ReportDetail | null>(null)
const older = ref<ReportDetail | null>(null)
const loading = ref(false)
const error = ref('')

const left = computed(() => newer.value?.report ?? null)
const right = computed(() => older.value?.report ?? null)

function ratingOf(report: AIAnalysisResponse | null): string {
  return report?.decision?.rating ?? report?.analysis.rating ?? '—'
}

function ratingTone(rating: string): string {
  if (rating === '买入' || rating === '看多') return 'text-up'
  if (rating === '卖出' || rating === '看空') return 'text-down'
  return 'text-ink-2'
}

function scoreOf(report: AIAnalysisResponse | null, key: string): number | null {
  return report?.analysts.find((analyst) => analyst.key === key)?.score ?? null
}

function levelOf(report: AIAnalysisResponse | null, key: 'entry' | 'take_profit' | 'stop_loss' | 'risk_reward'): string {
  const levels = report?.decision?.levels
  if (!levels) return '—'
  if (key === 'risk_reward') return `${levels.risk_reward.toFixed(2)} : 1`
  return levels[key].toFixed(2)
}

const dimensionRows = computed(() =>
  AXES.map((axis) => {
    const leftScore = scoreOf(left.value, axis.key)
    const rightScore = scoreOf(right.value, axis.key)
    return {
      label: axis.label,
      left: leftScore,
      right: rightScore,
      delta:
        leftScore != null && rightScore != null
          ? leftScore - rightScore
          : null,
    }
  }),
)

const levelRows = [
  { label: '建议入场', key: 'entry' as const },
  { label: '止盈', key: 'take_profit' as const },
  { label: '止损', key: 'stop_loss' as const },
  { label: '盈亏比', key: 'risk_reward' as const },
]

const contentGroups = computed(() => [
  {
    key: 'reason',
    title: '核心理由',
    pick: (report: AIAnalysisResponse) => report.decision?.key_reasons ?? [],
  },
  {
    key: 'risk',
    title: '风险提示',
    pick: (report: AIAnalysisResponse) => report.decision?.risks ?? [],
  },
])

async function load(): Promise<void> {
  const ids = String(route.query.ids ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

  if (ids.length !== 2) {
    error.value = '对比链接无效，请从报告详情或历史列表重新进入'
    return
  }

  loading.value = true
  error.value = ''
  newer.value = null
  older.value = null
  try {
    const [first, second] = (
      await Promise.all(ids.map((id) => reportsApi.get(id)))
    ).map((response) => response.data)
    if (first.report.symbol !== second.report.symbol) {
      error.value = '只能对比同一只股票的报告'
      return
    }
    const sorted = [first, second].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    newer.value = sorted[0]
    older.value = sorted[1]
  } catch (err) {
    error.value = getErrorMessage(err, '报告对比加载失败')
  } finally {
    loading.value = false
  }
}

watch(() => route.query.ids, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      to="/reports"
      class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
    >
      <span aria-hidden="true">←</span>
      返回全部历史报告
    </RouterLink>

    <div v-if="loading" class="mt-6 animate-pulse rounded-lg border border-line bg-canvas p-5">
      <div class="h-6 w-40 rounded bg-surface-2" />
      <div class="mt-3 h-10 w-60 rounded bg-surface-2" />
      <div class="mt-5 h-64 rounded bg-surface-2" />
    </div>

    <div
      v-else-if="error || !newer || !older"
      class="mt-6 rounded-lg border border-line bg-canvas px-5 py-10 text-center text-sm text-danger"
    >
      {{ error || '报告对比数据不完整' }}
    </div>

    <template v-else>
      <section class="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="text-[24px] font-semibold tracking-tight text-ink">
            {{ newer.report.name }} · 报告对比
          </h1>
          <p class="mt-1 text-xs tabular-nums text-ink-3">
            {{ newer.report.symbol }} · 左侧为较新报告，右侧为较早报告
          </p>
        </div>
        <div class="flex flex-wrap gap-2 text-[11px] text-ink-3">
          <RouterLink
            :to="{ path: `/reports/${newer.id}`, query: { from: 'reports' } }"
            class="font-medium text-primary hover:text-primary-hover"
          >
            查看较新报告 →
          </RouterLink>
          <RouterLink
            :to="{ path: `/reports/${older.id}`, query: { from: 'reports' } }"
            class="font-medium text-primary hover:text-primary-hover"
          >
            查看较早报告 →
          </RouterLink>
        </div>
      </section>

      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-for="item in [newer, older]" :key="item.id" class="rounded-md bg-surface px-4 py-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="text-[11px] font-medium text-ink-3">
                {{ item.id === newer.id ? '较新' : '较早' }}
              </span>
              <span class="text-[11px] tabular-nums text-ink-3">
                {{ formatFullDateTime(item.created_at) }}
              </span>
            </div>
            <div class="mt-1 flex flex-wrap items-baseline gap-2">
              <span class="text-[18px] font-semibold" :class="ratingTone(ratingOf(item.report))">
                {{ ratingOf(item.report) }}
              </span>
              <span class="text-xs text-ink-3">
                置信度 {{ item.report.decision?.confidence ?? item.report.analysis.confidence }}
              </span>
            </div>
            <p class="mt-1 text-[11px] text-ink-3">
              操作 {{ item.report.decision?.operation_advice || '—' }} ·
              周期 {{ item.report.decision?.holding_period || '—' }} ·
              仓位 {{ item.report.decision?.position_size || '—' }}
            </p>
          </div>
        </div>
      </section>

      <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-sm font-semibold text-ink">六维评分变化</h2>
          <span class="text-[11px] text-ink-3">分数越高越积极；风险维度分数越高表示风险越低</span>
        </div>

        <div class="mt-4 grid items-center gap-6 lg:grid-cols-[320px_1fr]">
          <AnalystRadar
            :series="[
              { label: '较新', analysts: newer.report.analysts },
              { label: '较早', analysts: older.report.analysts },
            ]"
            :size="320"
          />

          <div class="overflow-hidden rounded-md border border-line">
            <div class="grid grid-cols-4 bg-surface px-3 py-2 text-[11px] font-medium text-ink-3">
              <span>维度</span>
              <span class="text-right">较新</span>
              <span class="text-right">较早</span>
              <span class="text-right">变化</span>
            </div>
            <div
              v-for="row in dimensionRows"
              :key="row.label"
              class="grid grid-cols-4 items-center border-t border-line px-3 py-2 text-xs"
            >
              <span class="text-ink-2">{{ row.label }}</span>
              <span class="text-right font-medium tabular-nums text-ink">{{ row.left ?? '—' }}</span>
              <span class="text-right tabular-nums text-ink-2">{{ row.right ?? '—' }}</span>
              <span
                class="text-right font-medium tabular-nums"
                :class="
                  row.delta == null || row.delta === 0
                    ? 'text-ink-3'
                    : row.delta > 0
                      ? 'text-up'
                      : 'text-down'
                "
              >
                {{ row.delta == null ? '—' : `${row.delta > 0 ? '+' : ''}${row.delta}` }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <section class="rounded-lg border border-line bg-canvas p-5">
          <h2 class="text-sm font-semibold text-ink">关键价位</h2>
          <div class="mt-3 overflow-hidden rounded-md border border-line">
            <div class="grid grid-cols-3 bg-surface px-3 py-2 text-[11px] font-medium text-ink-3">
              <span>项目</span>
              <span class="text-right">较新</span>
              <span class="text-right">较早</span>
            </div>
            <div
              v-for="row in levelRows"
              :key="row.key"
              class="grid grid-cols-3 border-t border-line px-3 py-2 text-xs"
            >
              <span class="text-ink-2">{{ row.label }}</span>
              <span class="text-right font-medium tabular-nums text-ink">
                {{ levelOf(left, row.key) }}
              </span>
              <span class="text-right tabular-nums text-ink-2">
                {{ levelOf(right, row.key) }}
              </span>
            </div>
          </div>
          <p v-if="!left?.decision?.levels || !right?.decision?.levels" class="mt-2 text-[11px] text-warn">
            旧报告可能没有价位数据。
          </p>
        </section>

        <section class="rounded-lg border border-line bg-canvas p-5">
          <h2 class="text-sm font-semibold text-ink">持仓建议</h2>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <div v-for="item in [newer, older]" :key="`position-${item.id}`" class="rounded-md bg-surface px-3 py-3">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-[11px] text-ink-3">
                  {{ item.id === newer.id ? '较新' : '较早' }}
                </span>
                <span v-if="item.report.decision?.position_action" class="rounded bg-canvas px-1.5 py-0.5 text-[11px] font-semibold text-ink-2">
                  {{ item.report.decision.position_action }}
                </span>
              </div>
              <p class="mt-1 text-xs leading-relaxed text-ink-2">
                {{ item.report.decision?.position_advice || '—' }}
              </p>
            </div>
          </div>
        </section>
      </div>

      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <section
          v-for="group in contentGroups"
          :key="group.key"
          class="rounded-lg border border-line bg-canvas p-5"
        >
          <h2 class="text-sm font-semibold text-ink">{{ group.title }}</h2>
          <div class="mt-3 grid gap-4 sm:grid-cols-2">
            <div v-for="item in [newer, older]" :key="`${group.key}-${item.id}`">
              <div class="text-[11px] text-ink-3">
                {{ item.id === newer.id ? '较新' : '较早' }}
              </div>
              <ul v-if="group.pick(item.report).length" class="mt-1 space-y-1">
                <li
                  v-for="(text, index) in group.pick(item.report)"
                  :key="index"
                  class="flex gap-1.5 text-xs leading-relaxed text-ink-2"
                >
                  <span class="mt-1.5 size-1 shrink-0 rounded-full bg-primary" />
                  {{ text }}
                </li>
              </ul>
              <p v-else class="mt-1 text-xs text-ink-3">—</p>
            </div>
          </div>
        </section>
      </div>

      <section class="mt-4 rounded-lg border border-line bg-surface p-4 text-[11px] leading-relaxed text-ink-3">
        <div>
          团队讨论：
          较新 {{ newer.report.discussion?.turns.length ?? 0 }} 轮 ·
          较早 {{ older.report.discussion?.turns.length ?? 0 }} 轮
          <span v-if="!newer.report.discussion || !older.report.discussion">（旧报告可能没有讨论记录）</span>
        </div>
        <div class="mt-1">{{ newer.report.disclaimer }}</div>
      </section>
    </template>
  </AppShell>
</template>
