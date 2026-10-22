<script setup lang="ts">
import { computed } from 'vue'

import type { AnalystReport } from '@/api/ai'

export interface RadarSeries {
  label: string
  analysts: AnalystReport[]
}

const props = withDefaults(
  defineProps<{
    series: RadarSeries[]
    size?: number
  }>(),
  { size: 260 },
)

const AXES = [
  { key: 'technical', label: '技术面' },
  { key: 'fundamental', label: '基本面' },
  { key: 'fund_flow', label: '资金面' },
  { key: 'sentiment', label: '情绪' },
  { key: 'risk', label: '风险' },
  { key: 'news', label: '新闻' },
]

const SIZE = 260
const CENTER = SIZE / 2
const RADIUS = 92
const TONE_COLORS = ['var(--color-primary)', 'var(--color-ink-3)']

interface Point {
  x: number
  y: number
}

function axisPoint(index: number, ratio: number): Point {
  const angle = (Math.PI * 2 * index) / AXES.length - Math.PI / 2
  return {
    x: CENTER + Math.cos(angle) * RADIUS * ratio,
    y: CENTER + Math.sin(angle) * RADIUS * ratio,
  }
}

const rings = [0.25, 0.5, 0.75, 1].map((ratio) => ({
  ratio,
  points: AXES.map((_, index) => axisPoint(index, ratio))
    .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
    .join(' '),
}))

const axes = AXES.map((axis, index) => {
  const outer = axisPoint(index, 1)
  const labelPos = {
    x: Number(axisPoint(index, 1.16).x.toFixed(1)),
    y: Number(axisPoint(index, 1.16).y.toFixed(1)),
  }
  return {
    ...axis,
    outer,
    labelPos,
    anchor: labelPos.x < CENTER - 2 ? 'end' : labelPos.x > CENTER + 2 ? 'start' : 'middle',
  }
})

const polygons = computed(() =>
  props.series.map((item, seriesIndex) => {
    const scores = AXES.map((axis) => {
      const analyst = item.analysts.find((entry) => entry.key === axis.key)
      return analyst ? analyst.score : 0
    })
    const available = item.analysts.filter((entry) =>
      AXES.some((axis) => axis.key === entry.key),
    )
    const average = available.length
      ? Math.round(available.reduce((sum, entry) => sum + entry.score, 0) / available.length)
      : 0
    const missing = AXES.filter(
      (axis) => !item.analysts.some((entry) => entry.key === axis.key),
    ).map((axis) => axis.label)

    return {
      label: item.label,
      color: TONE_COLORS[seriesIndex % TONE_COLORS.length],
      points: scores
        .map((score, index) => axisPoint(index, Math.max(0, Math.min(100, score)) / 100))
        .map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)
        .join(' '),
      average,
      missing,
    }
  }),
)
</script>

<template>
  <div class="flex flex-col items-center">
    <svg
      :viewBox="`0 0 ${SIZE} ${SIZE}`"
      class="w-full"
      :style="{ maxWidth: `${size}px` }"
      role="img"
      aria-label="六维分析师评分雷达图"
    >
      <polygon
        v-for="ring in rings"
        :key="ring.ratio"
        :points="ring.points"
        fill="none"
        stroke="var(--color-line)"
        stroke-width="1"
      />
      <line
        v-for="axis in axes"
        :key="`line-${axis.key}`"
        :x1="CENTER"
        :y1="CENTER"
        :x2="axis.outer.x"
        :y2="axis.outer.y"
        stroke="var(--color-line)"
        stroke-width="1"
      />

      <polygon
        v-for="polygon in polygons"
        :key="`polygon-${polygon.label}`"
        :points="polygon.points"
        :fill="polygon.color"
        fill-opacity="0.12"
        :stroke="polygon.color"
        stroke-width="1.5"
      />

      <text
        v-for="axis in axes"
        :key="`label-${axis.key}`"
        :x="axis.labelPos.x"
        :y="axis.labelPos.y + 4"
        :text-anchor="axis.anchor"
        class="text-[11px]"
        :style="{ fill: 'var(--color-ink-3)' }"
      >
        {{ axis.label }}
      </text>

      <text
        :x="CENTER"
        :y="CENTER - 2"
        text-anchor="middle"
        class="text-[20px] font-semibold tabular-nums"
        :style="{ fill: 'var(--color-ink)' }"
      >
        {{ polygons[0]?.average ?? 0 }}
      </text>
      <text
        :x="CENTER"
        :y="CENTER + 14"
        text-anchor="middle"
        class="text-[10px]"
        :style="{ fill: 'var(--color-ink-3)' }"
      >
        {{ polygons.length > 1 ? '本次均分' : '六维均分' }}
      </text>
    </svg>

    <div v-if="polygons.length > 1" class="mt-1 flex flex-wrap justify-center gap-x-4 gap-y-1">
      <span
        v-for="polygon in polygons"
        :key="`legend-${polygon.label}`"
        class="inline-flex items-center gap-1.5 text-[11px] text-ink-3"
      >
        <span class="size-2 rounded-full" :style="{ backgroundColor: polygon.color }" />
        {{ polygon.label }} · 均分 {{ polygon.average }}
      </span>
    </div>

    <p
      v-if="polygons.some((polygon) => polygon.missing.length)"
      class="mt-1 text-center text-[10px] text-warn"
    >
      缺失维度按 0 计：{{ polygons.flatMap((polygon) => polygon.missing).join('、') }}
    </p>
  </div>
</template>
