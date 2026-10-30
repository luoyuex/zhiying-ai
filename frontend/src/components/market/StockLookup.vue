<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { marketApi, type StockSearchItem } from '@/api/market'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { getErrorMessage, getErrorStatus } from '@/utils/errors'

const HOT_STOCKS = [
  { code: '600519', name: '贵州茅台' },
  { code: '300750', name: '宁德时代' },
  { code: '601318', name: '中国平安' },
  { code: '000001', name: '平安银行' },
]

const EXCHANGE_LABEL: Record<string, string> = { SH: '沪', SZ: '深', BJ: '京' }
const DEBOUNCE_MS = 250
const RECENT_KEY = 'zhiying.recent-stocks'
const RECENT_LIMIT = 3
const QUICK_LIMIT = 4

interface QuickPick {
  code: string
  name: string
}

const router = useRouter()
const keyword = ref('')
const error = ref('')
const searchError = ref('')
const suggestions = ref<StockSearchItem[]>([])
const open = ref(false)
const searching = ref(false)
const activeIndex = ref(-1)
const root = ref<HTMLElement | null>(null)
const recent = ref<QuickPick[]>(readRecent())
const hot = ref<QuickPick[]>([])
const hotLoading = ref(false)

const quickPicks = computed<QuickPick[]>(() => {
  if (recent.value.length) return recent.value
  if (hot.value.length) return hot.value.slice(0, QUICK_LIMIT)
  return HOT_STOCKS
})
const quickLabel = computed(() => (recent.value.length ? '最近查询' : '热门股票'))
const quickHint = computed(() =>
  recent.value.length ? '本机最近查询过的股票' : '按当日成交额排序',
)

let debounceTimer: number | undefined
let requestSeq = 0

function readRecent(): QuickPick[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (item): item is QuickPick =>
          !!item &&
          typeof item === 'object' &&
          typeof (item as QuickPick).code === 'string' &&
          /^\d{6}$/.test((item as QuickPick).code),
      )
      .map((item) => ({ code: item.code, name: typeof item.name === 'string' ? item.name : '' }))
      .slice(0, RECENT_LIMIT)
  } catch {
    return []
  }
}

function remember(code: string, name: string): void {
  const next = [{ code, name }, ...recent.value.filter((item) => item.code !== code)].slice(
    0,
    RECENT_LIMIT,
  )
  recent.value = next
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    // 隐私模式或配额已满时忽略，不影响查询
  }
}

function openStock(code: string, name = ''): void {
  const value = code.trim()
  if (!/^\d{6}$/.test(value)) {
    error.value = '请输入 6 位股票代码'
    return
  }
  error.value = ''
  open.value = false
  remember(value, name)
  void router.push({ name: 'stock', params: { symbol: value } })
}

function choose(item: StockSearchItem): void {
  error.value = ''
  remember(item.code, item.name)
  void router.push({ name: 'stock', params: { symbol: item.code } })
}

/** 有本机最近查询时不请求；失败静默回落到固定热门，入口不空 */
async function loadHot(): Promise<void> {
  if (recent.value.length) return
  hotLoading.value = true
  try {
    const { data } = await marketApi.hotStocks(QUICK_LIMIT)
    hot.value = data
      .filter((item) => /^\d{6}$/.test(item.code) && item.name)
      .map((item) => ({ code: item.code, name: item.name }))
  } catch {
    hot.value = []
  } finally {
    hotLoading.value = false
  }
}

async function runSearch(text: string): Promise<void> {
  const seq = ++requestSeq
  searching.value = true
  try {
    const { data } = await marketApi.searchStocks(text)
    if (seq !== requestSeq) return
    searchError.value = ''
    suggestions.value = data
    activeIndex.value = data.length ? 0 : -1
    open.value = true
  } catch (err) {
    if (seq !== requestSeq) return
    suggestions.value = []
    activeIndex.value = -1
    open.value = true
    searchError.value =
      getErrorStatus(err) === 404
        ? '搜索接口未就绪，请重启后端后重试'
        : getErrorMessage(err, '股票搜索失败，请稍后重试')
  } finally {
    if (seq === requestSeq) searching.value = false
  }
}

watch(keyword, (value) => {
  window.clearTimeout(debounceTimer)
  error.value = ''
  searchError.value = ''
  const text = value.trim()
  if (!text) {
    requestSeq += 1
    suggestions.value = []
    open.value = false
    searching.value = false
    return
  }
  debounceTimer = window.setTimeout(() => void runSearch(text), DEBOUNCE_MS)
})

function submit(): void {
  const text = keyword.value.trim()
  if (/^\d{6}$/.test(text)) {
    openStock(text)
    return
  }
  if (searchError.value) {
    error.value = searchError.value
    return
  }
  if (searching.value) {
    error.value = '正在搜索，请稍候'
    return
  }
  if (open.value && activeIndex.value >= 0 && suggestions.value[activeIndex.value]) {
    choose(suggestions.value[activeIndex.value])
    return
  }
  if (suggestions.value.length === 1) {
    choose(suggestions.value[0])
    return
  }
  error.value = !text
    ? '请输入股票代码、名称或拼音'
    : suggestions.value.length
      ? '请从下拉结果中选择股票'
      : '没有找到匹配的股票'
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!suggestions.value.length) return
    if (!open.value) {
      open.value = true
      activeIndex.value = 0
      return
    }
    activeIndex.value = (activeIndex.value + 1) % suggestions.value.length
  } else if (event.key === 'ArrowUp') {
    if (!open.value || !suggestions.value.length) return
    event.preventDefault()
    activeIndex.value =
      (activeIndex.value - 1 + suggestions.value.length) % suggestions.value.length
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (!open.value) return
  const target = event.target as Node | null
  if (target && root.value && !root.value.contains(target)) open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  void loadHot()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  window.clearTimeout(debounceTimer)
})
</script>

<template>
  <section ref="root" class="rounded-lg border border-line bg-canvas p-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold text-ink">个股查询</h2>
        <p class="mt-1 text-xs text-ink-2">
          支持代码、名称与拼音首字母，选中后直接进入个股页查看报价、K 线与 AI 分析。
        </p>
      </div>

      <div class="relative w-full sm:w-[420px]">
        <form class="flex w-full gap-2" @submit.prevent="submit">
          <Input
            v-model="keyword"
            class="min-w-0 flex-1"
            placeholder="代码 / 名称 / 拼音，如 gzmt"
            aria-label="搜索股票"
            role="combobox"
            aria-autocomplete="list"
            :aria-expanded="open"
            autocomplete="off"
            maxlength="20"
            @keydown="onKeydown"
          />
          <Button type="submit" class="shrink-0">查询</Button>
        </form>

        <div
          v-if="open"
          class="absolute left-0 right-0 top-[calc(100%+6px)] z-20 overflow-hidden rounded-lg border border-line bg-canvas shadow-pop"
          role="listbox"
          aria-label="股票搜索建议"
        >
          <div v-if="searchError" class="px-3 py-2.5 text-xs text-danger">
            {{ searchError }}
          </div>

          <div v-else-if="searching" class="px-3 py-2.5 text-xs text-ink-3">搜索中…</div>

          <div v-else-if="!suggestions.length" class="px-3 py-2.5 text-xs text-ink-3">
            没有匹配的股票
          </div>

          <template v-else>
            <button
              v-for="(item, index) in suggestions"
              :key="item.code"
              type="button"
              role="option"
              :aria-selected="index === activeIndex"
              class="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors"
              :class="index === activeIndex ? 'bg-surface' : 'hover:bg-surface'"
              @click="choose(item)"
              @mouseenter="activeIndex = index"
            >
              <span class="w-12 shrink-0 text-xs tabular-nums text-ink-3">{{ item.code }}</span>
              <span class="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">
                {{ item.name }}
              </span>
              <span
                class="shrink-0 rounded-full bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-3"
              >
                {{ EXCHANGE_LABEL[item.exchange] ?? item.exchange }}
              </span>
            </button>
          </template>
        </div>
      </div>
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-ink-3">
      <span :title="quickHint">{{ quickLabel }}</span>
      <template v-if="hotLoading && !recent.length">
        <div
          v-for="index in 3"
          :key="index"
          class="h-[30px] w-28 animate-pulse rounded-full bg-surface-2"
        />
      </template>
      <template v-else>
        <button
          v-for="item in quickPicks"
          :key="item.code"
          type="button"
          class="rounded-full border border-line px-3 py-1.5 text-[12px] text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
          @click="openStock(item.code, item.name)"
        >
          {{ item.name || item.code }}
          <span v-if="item.name" class="tabular-nums text-ink-3">{{ item.code }}</span>
        </button>
      </template>
    </div>

    <p v-if="error" class="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
      {{ error }}
    </p>
  </section>
</template>
