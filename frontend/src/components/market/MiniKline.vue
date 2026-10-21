<script setup lang="ts">
import { computed } from 'vue'

import type { KlineBar } from '@/api/market'

const props = withDefaults(
  defineProps<{
    bars: KlineBar[]
    count?: number
    title?: string
    large?: boolean
  }>(),
  {
    count: 60,
    title: '近 60 个交易日',
    large: false,
  },
)

const W = 720
const H = 248
const PRICE_TOP = 8
const PRICE_BOTTOM = 184
const VOL_TOP = 202
const VOL_BOTTOM = 240

type Tone = 'up' | 'down' | 'flat'

interface Candle {
  x: number
  width: number
  wickTop: number
  wickBottom: number
  bodyY: number
  bodyH: number
  volY: number
  volH: number
  tone: Tone
}

interface ChartGeometry {
  max: number
  min: number
  candles: Candle[]
  grid: number[]
  lastCloseY: number
}

const EMPTY: ChartGeometry = { max: 0, min: 0, candles: [], grid: [], lastCloseY: 0 }

const shown = computed(() => props.bars.slice(-props.count))

const chart = computed<ChartGeometry>(() => {
  const bars = shown.value
  if (!bars.length) return EMPTY

  const max = Math.max(...bars.map((bar) => bar.high))
  const min = Math.min(...bars.map((bar) => bar.low))
  const range = max - min || Math.max(Math.abs(max) * 0.01, 0.01)
  const maxVolume = Math.max(...bars.map((bar) => bar.volume), 1)
  const step = W / bars.length
  const width = Math.min(Math.max(step * 0.62, 1.2), 10)

  const y = (price: number): number =>
    PRICE_TOP + ((max - price) / range) * (PRICE_BOTTOM - PRICE_TOP)

  const candles: Candle[] = bars.map((bar, index) => {
    const tone: Tone = bar.close > bar.open ? 'up' : bar.close < bar.open ? 'down' : 'flat'
    const bodyTop = Math.min(y(bar.open), y(bar.close))
    const bodyBottom = Math.max(y(bar.open), y(bar.close))
    const volumeHeight = (bar.volume / maxVolume) * (VOL_BOTTOM - VOL_TOP)
    return {
      x: step * index + step / 2,
      width,
      wickTop: y(bar.high),
      wickBottom: y(bar.low),
      bodyY: bodyTop,
      bodyH: Math.max(1, bodyBottom - bodyTop),
      volY: VOL_BOTTOM - volumeHeight,
      volH: Math.max(1, volumeHeight),
      tone,
    }
  })

  const last = bars[bars.length - 1]
  return {
    max,
    min,
    candles,
    grid: [0.25, 0.5, 0.75].map(
      (fraction) => PRICE_TOP + fraction * (PRICE_BOTTOM - PRICE_TOP),
    ),
    lastCloseY: y(last.close),
  }
})

const dateRange = computed(() => {
  const bars = shown.value
  if (!bars.length) return ''
  return `${bars[0].time.slice(0, 10)} → ${bars[bars.length - 1].time.slice(0, 10)}`
})

function toneColor(tone: Tone): string {
  if (tone === 'up') return 'var(--color-up)'
  if (tone === 'down') return 'var(--color-down)'
  return 'var(--color-flat)'
}
</script>

<template>
  <div class="rounded-md border border-line bg-surface/60 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-3">
      <span>{{ title }}</span>
      <span class="tabular-nums">{{ dateRange }}</span>
    </div>

    <svg
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="none"
      class="mt-2 w-full"
      :class="large ? 'h-[280px] sm:h-[380px]' : 'h-[200px] sm:h-[248px]'"
      role="img"
      :aria-label="`${dateRange} 日 K 线图`"
    >
      <line
        v-for="(gridY, index) in chart.grid"
        :key="`grid-${index}`"
        x1="0"
        :x2="W"
        :y1="gridY"
        :y2="gridY"
        stroke="var(--color-line)"
        stroke-width="1"
        stroke-dasharray="3 5"
        vector-effect="non-scaling-stroke"
      />
      <line
        x1="0"
        :x2="W"
        :y1="VOL_TOP"
        :y2="VOL_TOP"
        stroke="var(--color-line)"
        stroke-width="1"
        vector-effect="non-scaling-stroke"
      />
      <line
        x1="0"
        :x2="W"
        :y1="chart.lastCloseY"
        :y2="chart.lastCloseY"
        stroke="var(--color-primary)"
        stroke-width="1"
        stroke-dasharray="4 4"
        opacity="0.3"
        vector-effect="non-scaling-stroke"
      />

      <g v-for="(candle, index) in chart.candles" :key="index">
        <line
          :x1="candle.x"
          :x2="candle.x"
          :y1="candle.wickTop"
          :y2="candle.wickBottom"
          :stroke="toneColor(candle.tone)"
          stroke-width="1"
          vector-effect="non-scaling-stroke"
        />
        <rect
          :x="candle.x - candle.width / 2"
          :y="candle.bodyY"
          :width="candle.width"
          :height="candle.bodyH"
          :fill="toneColor(candle.tone)"
        />
        <rect
          :x="candle.x - candle.width / 2"
          :y="candle.volY"
          :width="candle.width"
          :height="candle.volH"
          :fill="toneColor(candle.tone)"
          opacity="0.28"
        />
      </g>
    </svg>

    <div class="mt-1 flex items-center justify-between text-[10px] text-ink-3">
      <span class="tabular-nums">
        区间 {{ chart.min.toFixed(2) }} – {{ chart.max.toFixed(2) }}
      </span>
      <span><span class="text-up">红涨</span> / <span class="text-down">绿跌</span></span>
    </div>
  </div>
</template>
