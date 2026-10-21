<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { marketApi, type StockSearchItem } from '@/api/market'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'

const HOT_STOCKS = [
  { code: '600519', name: '贵州茅台' },
  { code: '300750', name: '宁德时代' },
  { code: '601318', name: '中国平安' },
  { code: '000001', name: '平安银行' },
]

const EXCHANGE_LABEL: Record<string, string> = { SH: '沪', SZ: '深', BJ: '京' }
const DEBOUNCE_MS = 250

const router = useRouter()
const keyword = ref('')
const error = ref('')
const suggestions = ref<StockSearchItem[]>([])
const open = ref(false)
const searching = ref(false)
const activeIndex = ref(-1)
const root = ref<HTMLElement | null>(null)

let debounceTimer: number | undefined
let requestSeq = 0

function openStock(code: string): void {
  const value = code.trim()
  if (!/^\d{6}$/.test(value)) {
    error.value = '请输入 6 位股票代码'
    return
  }
  error.value = ''
  open.value = false
  void router.push({ name: 'stock', params: { symbol: value } })
}

function choose(item: StockSearchItem): void {
  error.value = ''
  void router.push({ name: 'stock', params: { symbol: item.code } })
}

async function runSearch(text: string): Promise<void> {
  const seq = ++requestSeq
  searching.value = true
  try {
    const { data } = await marketApi.searchStocks(text)
    if (seq !== requestSeq) return
    suggestions.value = data
    activeIndex.value = data.length ? 0 : -1
    open.value = true
  } catch {
    if (seq !== requestSeq) return
    suggestions.value = []
    open.value = false
  } finally {
    if (seq === requestSeq) searching.value = false
  }
}

watch(keyword, (value) => {
  window.clearTimeout(debounceTimer)
  error.value = ''
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
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-ink">个股查询</h2>
          <span
            class="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary"
          >
            直达详情
          </span>
        </div>
        <p class="mt-1 text-xs text-ink-3">
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
          <div v-if="searching" class="px-3 py-2.5 text-xs text-ink-3">搜索中…</div>

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
      <span>快捷查询</span>
      <button
        v-for="item in HOT_STOCKS"
        :key="item.code"
        type="button"
        class="rounded-full border border-line px-2.5 py-1 transition-colors hover:border-line-strong hover:text-ink"
        @click="openStock(item.code)"
      >
        {{ item.name }} <span class="tabular-nums">{{ item.code }}</span>
      </button>
    </div>

    <p v-if="error" class="mt-3 rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
      {{ error }}
    </p>
  </section>
</template>
