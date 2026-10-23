<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  companyApi,
  type CompanyNewsData,
  type NewsItem,
  type WebSearchResult,
} from '@/api/company'
import { getErrorMessage } from '@/utils/errors'
import { formatQuoteTime, formatSourceList } from '@/utils/market'

const props = defineProps<{
  symbol: string
}>()

type NewsTab = 'announcements' | 'articles' | 'ai'

const TABS: { value: NewsTab; label: string }[] = [
  { value: 'announcements', label: '公告' },
  { value: 'articles', label: '新闻' },
  { value: 'ai', label: 'AI 资讯' },
]

const tab = ref<NewsTab>('announcements')
const data = ref<CompanyNewsData | null>(null)
const loading = ref(false)
const error = ref('')
const aiResult = ref<WebSearchResult | null>(null)
const aiLoading = ref(false)
const aiError = ref('')

const items = computed<NewsItem[]>(() => {
  if (!data.value) return []
  return tab.value === 'articles' ? data.value.articles : data.value.announcements
})

function showTime(value: string): string {
  return value ? value.slice(0, 16).replace('T', ' ') : '时间未知'
}

async function load(): Promise<void> {
  const symbol = props.symbol
  if (!/^\d{6}$/.test(symbol)) {
    data.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    const { data: result } = await companyApi.news(symbol)
    if (props.symbol === symbol) data.value = result
  } catch (err) {
    if (props.symbol === symbol) {
      data.value = null
      error.value = getErrorMessage(err, '资讯加载失败')
    }
  } finally {
    if (props.symbol === symbol) loading.value = false
  }
}

async function runAISearch(): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  aiError.value = ''
  try {
    const { data: result } = await companyApi.aiSearchNews(props.symbol)
    aiResult.value = result
    if (!result.success) {
      aiError.value = result.error || '未检索到相关资讯'
    }
  } catch (err) {
    aiError.value = getErrorMessage(err, 'AI 检索失败')
  } finally {
    aiLoading.value = false
  }
}

watch(
  () => props.symbol,
  () => {
    data.value = null
    aiResult.value = null
    aiError.value = ''
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <section class="mt-4 rounded-lg border border-line bg-canvas p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-ink">资讯</h2>
        <p class="mt-1 text-[11px] text-ink-3">
          公告与新闻来自东方财富公开数据；AI 资讯仅在手动点击后调用一次元宝搜索。
        </p>
      </div>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="item in TABS"
          :key="item.value"
          type="button"
          class="h-7 rounded-sm px-2.5 text-xs transition-colors duration-150"
          :class="
            tab === item.value
              ? 'bg-primary-soft font-medium text-primary'
              : 'text-ink-2 hover:text-ink'
          "
          @click="tab = item.value"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <template v-if="tab !== 'ai'">
      <div v-if="loading && !data" class="mt-4 animate-pulse space-y-2">
        <div v-for="index in 4" :key="index" class="h-11 rounded bg-surface-2" />
      </div>

      <div
        v-else-if="error"
        class="mt-4 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn"
      >
        {{ error }}
        <button
          type="button"
          class="ml-2 font-medium text-primary underline-offset-2 hover:text-primary-hover hover:underline"
          @click="load"
        >
          重试
        </button>
      </div>

      <template v-else-if="data">
        <p v-if="data.partial" class="mt-3 text-[11px] text-warn">
          部分数据源暂时不可用，列表可能不完整。
        </p>

        <ul v-if="items.length" class="mt-3 divide-y divide-line">
          <li v-for="item in items" :key="item.id" class="py-2.5">
            <a
              :href="item.url"
              target="_blank"
              rel="noopener noreferrer"
              class="block text-xs leading-relaxed text-ink-2 transition-colors hover:text-primary"
            >
              {{ item.title }}
            </a>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-ink-3">
              <span>{{ showTime(item.published_at) }}</span>
              <span v-if="item.source">{{ item.source }}</span>
              <span v-if="item.summary">{{ item.summary }}</span>
            </div>
          </li>
        </ul>

        <div
          v-else
          class="mt-4 flex h-24 items-center justify-center rounded-md border border-dashed border-line bg-surface text-xs text-ink-3"
        >
          暂无{{ tab === 'announcements' ? '公告' : '新闻' }}数据
        </div>

        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-3">
          <span>共 {{ items.length }} 条</span>
          <span class="tabular-nums">
            来源 {{ formatSourceList(data.source.split('+')) }} · {{ formatQuoteTime(data.fetched_at) }}
          </span>
        </div>
      </template>
    </template>

    <template v-else>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          class="inline-flex h-9 items-center rounded-md border border-line-strong bg-canvas px-3 text-xs font-medium text-ink-2 transition-colors hover:border-ink-3 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="aiLoading"
          @click="runAISearch"
        >
          {{ aiLoading ? '检索中…' : 'AI 检索资讯' }}
        </button>
        <span class="text-[11px] text-ink-3">每次手动检索消耗 1 次元宝调用，结果缓存 6 小时。</span>
      </div>

      <div
        v-if="aiError"
        class="mt-3 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn"
      >
        {{ aiError }}
      </div>

      <ul v-if="aiResult?.pages.length" class="mt-3 divide-y divide-line">
        <li v-for="(page, index) in aiResult.pages" :key="`${page.url}-${index}`" class="py-2.5">
          <a
            :href="page.url"
            target="_blank"
            rel="noopener noreferrer"
            class="block text-xs leading-relaxed text-ink-2 transition-colors hover:text-primary"
          >
            {{ page.title }}
          </a>
          <p v-if="page.summary" class="mt-1 text-[11px] leading-relaxed text-ink-3">
            {{ page.summary }}
          </p>
          <div class="mt-1 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
            <span>{{ showTime(page.date) }}</span>
            <span v-if="page.site">{{ page.site }}</span>
          </div>
        </li>
      </ul>

      <div
        v-else-if="!aiLoading && !aiError"
        class="mt-4 flex h-24 items-center justify-center rounded-md border border-dashed border-line bg-surface text-xs text-ink-3"
      >
        点击上方按钮，让 AI 从公开网页中检索该股最新资讯。
      </div>

      <p v-if="aiResult?.success" class="mt-3 text-[11px] text-ink-3">
        共 {{ aiResult.pages.length }} 条 · 结果仅作事件线索，需以正式公告核实。
      </p>
    </template>
  </section>
</template>
