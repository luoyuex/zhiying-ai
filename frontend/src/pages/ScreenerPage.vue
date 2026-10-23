<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { screenerApi, type ScreenerStrategy } from '@/api/screener'
import AppShell from '@/components/layout/AppShell.vue'
import LowPriceBullPanel from '@/components/screener/LowPriceBullPanel.vue'
import MainForcePanel from '@/components/screener/MainForcePanel.vue'
import ProfitGrowthPanel from '@/components/screener/ProfitGrowthPanel.vue'
import SmallCapPanel from '@/components/screener/SmallCapPanel.vue'
import ValueStockPanel from '@/components/screener/ValueStockPanel.vue'

const strategies = ref<ScreenerStrategy[]>([
  {
    id: 'main_force',
    name: '主力追踪',
    description:
      '按所选区间主力资金净流入排行与市值区间筛选，AI 三位分析师（资金流向 / 行业板块 / 财务基本面）整体分析后由资深研究员精选。',
    status: 'available',
  },
  {
    id: 'low_price_bull',
    name: '低价寻宝',
    description:
      'AI 三位分析师（资金与流动性 / 行业板块 / 业绩成长）分析低价、高净利增长标的，由资深研究员精选最终结果。',
    status: 'available',
  },
  {
    id: 'small_cap',
    name: '小盘精选',
    description:
      'AI 三位分析师（资金与流动性 / 行业板块 / 成长与估值）分析小市值、高增长标的，由资深研究员精选最终结果。',
    status: 'available',
  },
  {
    id: 'profit_growth',
    name: '业绩高增',
    description:
      'AI 三位分析师（资金与流动性 / 行业板块 / 成长质量）分析高净利增长标的，由资深研究员精选最终结果。',
    status: 'available',
  },
  {
    id: 'value_stock',
    name: '价值洼地',
    description:
      'AI 三位分析师（资金与流动性 / 行业板块 / 估值质量）分析低 PE/PB、近 12 个月高股息、最新报告期低负债标的，由资深研究员精选最终结果。',
    status: 'available',
  },
])
const activeStrategy = ref('main_force')

const STRATEGY_STORAGE_KEY = 'zhiying:screener:strategy'
const AVAILABLE_STRATEGIES = [
  'main_force',
  'low_price_bull',
  'small_cap',
  'profit_growth',
  'value_stock',
]
const savedStrategy = localStorage.getItem(STRATEGY_STORAGE_KEY)
if (savedStrategy && AVAILABLE_STRATEGIES.includes(savedStrategy)) {
  activeStrategy.value = savedStrategy
}

const activeMeta = computed(
  () => strategies.value.find((item) => item.id === activeStrategy.value) ?? null,
)

function selectStrategy(strategy: ScreenerStrategy): void {
  if (strategy.status !== 'available') return
  activeStrategy.value = strategy.id
  localStorage.setItem(STRATEGY_STORAGE_KEY, strategy.id)
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
        <p class="text-[13px] text-ink-3">
          策略圈定候选，AI 三位分析师与资深研究员给出最终选择
        </p>
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
    <SmallCapPanel v-else-if="activeStrategy === 'small_cap'" class="mt-4" />
    <ProfitGrowthPanel v-else-if="activeStrategy === 'profit_growth'" class="mt-4" />
    <ValueStockPanel v-else-if="activeStrategy === 'value_stock'" class="mt-4" />

    <div
      v-else
      class="mt-4 rounded-lg border border-dashed border-line bg-canvas px-4 py-14 text-center text-xs text-ink-3"
    >
      该策略还在开发中，可先使用主力追踪、低价寻宝或小盘精选。
    </div>
  </AppShell>
</template>
