<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'

const HOT_STOCKS = [
  { code: '600519', name: '贵州茅台' },
  { code: '300750', name: '宁德时代' },
  { code: '601318', name: '中国平安' },
  { code: '000001', name: '平安银行' },
]

const router = useRouter()
const symbol = ref('')
const error = ref('')

function openStock(code = symbol.value): void {
  const value = code.trim()
  if (!/^\d{6}$/.test(value)) {
    error.value = '请输入 6 位股票代码'
    return
  }
  error.value = ''
  void router.push({ name: 'stock', params: { symbol: value } })
}
</script>

<template>
  <section class="rounded-lg border border-line bg-canvas p-5">
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
          输入 6 位代码或点快捷标的，直接进入个股页查看报价、K 线、技术诊断与 AI 分析。
        </p>
      </div>

      <form class="flex w-full gap-2 sm:w-auto" @submit.prevent="openStock()">
        <Input
          v-model="symbol"
          class="min-w-0 flex-1 sm:w-56 sm:flex-none"
          placeholder="输入 6 位股票代码"
          aria-label="股票代码"
          inputmode="numeric"
          autocomplete="off"
          maxlength="6"
        />
        <Button type="submit" class="shrink-0">查询</Button>
      </form>
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
