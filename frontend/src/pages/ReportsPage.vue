<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { reportsApi, type ReportSummary } from '@/api/reports'
import AppShell from '@/components/layout/AppShell.vue'
import ReportListItem from '@/components/report/ReportListItem.vue'
import ReportListSkeleton from '@/components/report/ReportListSkeleton.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getErrorMessage } from '@/utils/errors'
import { dayLabel } from '@/utils/report'

const router = useRouter()
const reports = ref<ReportSummary[]>([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')

const stockCount = computed(() => new Set(reports.value.map((item) => item.symbol)).size)

const filtered = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return reports.value
  return reports.value.filter(
    (item) =>
      item.symbol.includes(value) || item.name.toLowerCase().includes(value),
  )
})

const groups = computed(() => {
  const result: { key: string; label: string; items: ReportSummary[] }[] = []
  for (const item of filtered.value) {
    const date = new Date(item.created_at)
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
    let group = result.find((entry) => entry.key === key)
    if (!group) {
      group = { key, label: dayLabel(date), items: [] }
      result.push(group)
    }
    group.items.push(item)
  }
  return result
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await reportsApi.list(undefined, 50)
    reports.value = data
  } catch (err) {
    reports.value = []
    error.value = getErrorMessage(err, '历史报告加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <AppShell>
    <RouterLink
      to="/"
      class="inline-flex items-center gap-1 text-xs text-ink-3 transition-colors hover:text-ink"
    >
      <span aria-hidden="true">←</span>
      返回首页
    </RouterLink>

    <section class="mt-4 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">所有个股的 AI 分析记录</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">历史报告</h1>
      </div>
      <div v-if="reports.length" class="flex gap-5 text-right text-[11px] text-ink-3">
        <div>
          <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
            {{ reports.length }}
          </div>
          <div class="mt-1">份报告</div>
        </div>
        <div>
          <div class="text-[20px] font-semibold leading-none tabular-nums text-ink">
            {{ stockCount }}
          </div>
          <div class="mt-1">只股票</div>
        </div>
      </div>
    </section>

    <section class="mt-6 rounded-lg border border-line bg-canvas">
      <div
        class="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-ink">全部分析</h2>
          <span
            v-if="reports.length"
            class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-ink-3"
          >
            {{ filtered.length }} 条
          </span>
        </div>
        <div class="w-full sm:w-64">
          <Input
            v-model="keyword"
            placeholder="筛选股票代码或名称"
            aria-label="筛选历史报告"
            autocomplete="off"
          />
        </div>
      </div>

      <ReportListSkeleton v-if="loading" />

      <div v-else-if="error" class="px-4 py-10 text-center">
        <p class="text-sm text-danger">{{ error }}</p>
        <Button variant="secondary" size="sm" class="mt-3" @click="load">重新加载</Button>
      </div>

      <div
        v-else-if="!reports.length"
        class="px-4 py-14 text-center"
      >
        <div class="text-sm font-medium text-ink">还没有分析报告</div>
        <p class="mt-1 text-xs text-ink-3">
          在个股详情页完成一次 AI 分析后，报告会自动保存在这里。
        </p>
        <Button variant="secondary" size="sm" class="mt-4" @click="router.push('/')">
          去查询股票
        </Button>
      </div>

      <div
        v-else-if="!filtered.length"
        class="px-4 py-12 text-center text-xs text-ink-3"
      >
        没有匹配「{{ keyword.trim() }}」的报告
      </div>

      <div v-else>
        <div v-for="group in groups" :key="group.key">
          <div
            class="border-b border-line bg-surface/60 px-4 py-2 text-[11px] font-medium text-ink-3"
          >
            {{ group.label }}
          </div>
          <ReportListItem
            v-for="item in group.items"
            :key="item.id"
            :item="item"
            from="reports"
          />
        </div>
      </div>
    </section>
  </AppShell>
</template>
