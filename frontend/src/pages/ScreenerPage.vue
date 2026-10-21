<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { screenerApi, type ScreenerStrategy } from '@/api/screener'
import AppShell from '@/components/layout/AppShell.vue'
import LowPriceBullPanel from '@/components/screener/LowPriceBullPanel.vue'
import MainForcePanel from '@/components/screener/MainForcePanel.vue'

const strategies = ref<ScreenerStrategy[]>([
  {
    id: 'main_force',
    name: '主力选股',
    description: '按超大单净流入排名筛选，剔除 ST / 创业板 / 科创板，可过滤涨幅过高的标的。',
    status: 'available',
  },
  {
    id: 'low_price_bull',
    name: '低价擒牛',
    description:
      '股价 < 10 元 + 净利润同比 ≥ 100%，剔除 ST / 创业板 / 科创板，按成交额由小到大排名。',
    status: 'available',
  },
])
const activeStrategy = ref('main_force')

const activeMeta = computed(
  () => strategies.value.find((item) => item.id === activeStrategy.value) ?? null,
)

function selectStrategy(strategy: ScreenerStrategy): void {
  if (strategy.status !== 'available') return
  activeStrategy.value = strategy.id
}

async function loadStrategies(): Promise<void> {
  try {
    const { data } = await screenerApi.strategies()
    if (data.length) strategies.value = data
  } catch {
    // 接口不可用时保留本地默认策略
  }
}

onMounted(() => {
  void loadStrategies()
})
</script>

<template>
  <AppShell>
    <section class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[13px] text-ink-3">按策略筛选 A 股，并可直接发起 AI 分析</p>
        <h1 class="mt-1 text-[24px] font-semibold tracking-tight text-ink">选股</h1>
      </div>
    </section>

    <div class="mt-5 flex flex-wrap gap-2">
      <button
        v-for="strategy in strategies"
        :key="strategy.id"
        type="button"
        class="h-8 rounded-md border px-3 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        :class="
          strategy.id === activeStrategy
            ? 'border-ink bg-ink text-canvas'
            : 'border-line text-ink-2 hover:border-line-strong hover:text-ink'
        "
        :disabled="strategy.status !== 'available'"
        @click="selectStrategy(strategy)"
      >
        {{ strategy.name }}
        <span v-if="strategy.status !== 'available'" class="ml-1 text-[10px] opacity-70">
          即将推出
        </span>
      </button>
    </div>

    <p v-if="activeMeta" class="mt-2 text-[11px] leading-relaxed text-ink-3">
      {{ activeMeta.description }}
    </p>

    <MainForcePanel v-if="activeStrategy === 'main_force'" class="mt-4" />
    <LowPriceBullPanel v-else-if="activeStrategy === 'low_price_bull'" class="mt-4" />

    <div
      v-else
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-14 text-center text-xs text-ink-3"
    >
      该策略还在开发中，可先使用主力选股或低价擒牛。
    </div>
  </AppShell>
</template>
