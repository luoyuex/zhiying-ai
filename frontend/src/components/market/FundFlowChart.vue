<script setup lang="ts">
import { computed } from 'vue'

import type { FundFlowDay, FundFlowMetric } from '@/api/company'
import { formatBig } from '@/utils/market'

const props = defineProps<{
  days: FundFlowDay[]
  metric: FundFlowMetric
}>()

const W = 720
const H = 190
const PAD_X = 6
const PAD_TOP = 14
const PAD_BOTTOM = 26

const geometry = computed(() => {
  const days = props.days
  if (!days.length) return null

  const values = days.map((day) => day[props.metric] ?? 0)
  const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 1)
  const step = (W - PAD_X * 2) / days.length
  const width = Math.min(Math.max(step * 0.62, 1.5), 14)
  const plotHeight = H - PAD_TOP - PAD_BOTTOM
  const zeroY = PAD_TOP + plotHeight / 2
  const scale = plotHeight / 2 / maxAbs

  const bars = values.map((value, index) => {
    const height = Math.max(Math.abs(value) * scale, value === 0 ? 0 : 1)
    return {
      x: PAD_X + step * index + step / 2,
      width,
      y: value >= 0 ? zeroY - height : zeroY,
      height,
      tone: value > 0 ? 'up' : value < 0 ? 'down' : 'flat',
      date: days[index].date,
      value,
    }
  })

  return {
    bars,
    zeroY,
    maxAbs,
    top: PAD_TOP,
    bottom: H - PAD_BOTTOM,
  }
})

function toneColor(tone: string): string {
  if (tone === 'up') return 'var(--color-up)'
  if (tone === 'down') return 'var(--color-down)'
  return 'var(--color-flat)'
}

const axisLabels = computed(() => {
  const chart = geometry.value
  if (!chart) return []
  return [
    { y: chart.top, text: formatBig(chart.maxAbs) },
    { y: chart.zeroY, text: '0' },
    { y: chart.bottom, text: `-${formatBig(chart.maxAbs)}` },
  ]
})
</script>

<template>
  <svg
    :viewBox="`0 0 ${W} ${H}`"
    preserveAspectRatio="none"
    class="h-[180px] w-full sm:h-[190px]"
    role="img"
    aria-label="资金流净额柱状图"
  >
    <template v-if="geometry">
      <line
        v-for="label in axisLabels"
        :key="`grid-${label.y}`"
        :x1="PAD_X"
        :x2="W - PAD_X"
        :y1="label.y"
        :y2="label.y"
        :stroke="label.y === geometry.zeroY ? 'var(--color-line-strong)' : 'var(--color-line)'"
        stroke-width="1"
        :stroke-dasharray="label.y === geometry.zeroY ? '' : '3 5'"
        vector-effect="non-scaling-stroke"
      />
      <g v-for="bar in geometry.bars" :key="bar.date">
        <rect
          :x="bar.x - bar.width / 2"
          :y="bar.y"
          :width="bar.width"
          :height="bar.height"
          :fill="toneColor(bar.tone)"
          opacity="0.85"
        >
          <title>{{ bar.date }} · {{ formatBig(bar.value) }}</title>
        </rect>
      </g>
    </template>
  </svg>
</template>
