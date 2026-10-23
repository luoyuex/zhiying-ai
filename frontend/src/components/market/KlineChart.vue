<script setup lang="ts">
import {
  LineType,
  dispose,
  init,
  type Chart,
  type KLineData,
} from 'klinecharts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { KlineBar } from '@/api/market'
import { readToken } from '@/utils/theme'

const props = defineProps<{
  bars: KlineBar[]
}>()

const container = ref<HTMLDivElement | null>(null)
let chart: Chart | null = null
let observer: ResizeObserver | null = null

function toTimestamp(time: string): number {
  const text = time.trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return new Date(`${text}T00:00:00+08:00`).getTime()
  }
  const value = new Date(text).getTime()
  return Number.isNaN(value) ? 0 : value
}

function toKLineData(bars: KlineBar[]): KLineData[] {
  return bars
    .map((bar) => ({
      timestamp: toTimestamp(bar.time),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
      turnover: bar.amount ?? undefined,
    }))
    .filter((item) => item.timestamp > 0)
}

function buildStyles() {
  const up = readToken('--color-up') || '#e0424a'
  const down = readToken('--color-down') || '#1ba672'
  const flat = readToken('--color-flat') || '#8a9099'
  const line = readToken('--color-line') || '#e6e8eb'
  const ink2 = readToken('--color-ink-2') || '#5a6069'
  const ink3 = readToken('--color-ink-3') || '#8a9099'
  const primary = readToken('--color-chart-line') || '#16181d'
  const warn = readToken('--color-warn') || '#c08a2e'
  const surface = readToken('--color-surface') || '#f7f8fa'

  return {
    grid: {
      horizontal: {
        color: line,
        size: 1,
        style: LineType.Dashed,
        dashedValue: [3, 5],
      },
      vertical: {
        color: line,
        size: 1,
        style: LineType.Dashed,
        dashedValue: [3, 5],
      },
    },
    candle: {
      bar: {
        upColor: up,
        downColor: down,
        noChangeColor: flat,
        upBorderColor: up,
        downBorderColor: down,
        noChangeBorderColor: flat,
        upWickColor: up,
        downWickColor: down,
        noChangeWickColor: flat,
      },
      priceMark: {
        last: {
          upColor: up,
          downColor: down,
          noChangeColor: flat,
        },
      },
      tooltip: {
        text: { color: ink2, size: 12 },
        rect: { color: surface, borderColor: line },
      },
    },
    indicator: {
      tooltip: { text: { color: ink2, size: 12 } },
      bars: [{ upColor: up, downColor: down, noChangeColor: flat }],
    },
    xAxis: {
      axisLine: { color: line },
      tickLine: { color: line },
      tickText: { color: ink3, size: 11 },
    },
    yAxis: {
      axisLine: { color: line },
      tickLine: { color: line },
      tickText: { color: ink3, size: 11 },
    },
    separator: { color: line },
    crosshair: {
      horizontal: {
        line: {
          color: ink3,
          size: 1,
          style: LineType.Dashed,
          dashedValue: [4, 4],
        },
        text: { color: '#ffffff', backgroundColor: ink2, borderColor: ink2 },
      },
      vertical: {
        line: {
          color: ink3,
          size: 1,
          style: LineType.Dashed,
          dashedValue: [4, 4],
        },
        text: { color: '#ffffff', backgroundColor: ink2, borderColor: ink2 },
      },
    },
    _colors: { primary, warn, ink2, ink3 },
  }
}

function indicatorLine(color: string, dashed = false) {
  return {
    color,
    size: 1,
    style: dashed ? LineType.Dashed : LineType.Solid,
    smooth: false,
    dashedValue: [4, 4],
  }
}

function applyData(): void {
  chart?.applyNewData(toKLineData(props.bars))
}

function setupChart(): void {
  if (!container.value) return
  const styles = buildStyles()
  const { _colors, ...chartStyles } = styles
  chart = init(container.value, {
    locale: 'zh-CN',
    timezone: 'Asia/Shanghai',
    styles: chartStyles,
  })
  if (!chart) return

  chart.createIndicator('MA', false, { id: 'candle_pane' })
  chart.overrideIndicator(
    {
      name: 'MA',
      styles: {
        lines: [
          indicatorLine(_colors.primary),
          indicatorLine(_colors.warn),
          indicatorLine(_colors.ink3),
          indicatorLine(_colors.ink2),
        ],
      },
    },
    'candle_pane',
  )

  chart.createIndicator('BOLL', false, { id: 'candle_pane' })
  chart.overrideIndicator(
    {
      name: 'BOLL',
      styles: {
        lines: [
          indicatorLine(_colors.ink3, true),
          indicatorLine(_colors.primary),
          indicatorLine(_colors.ink3, true),
        ],
      },
    },
    'candle_pane',
  )

  chart.createIndicator('VOL', false, { id: 'pane_vol', height: 72, minHeight: 40 })
  chart.createIndicator('MACD', false, { id: 'pane_macd', height: 88, minHeight: 40 })
  chart.overrideIndicator(
    {
      name: 'MACD',
      styles: {
        lines: [indicatorLine(_colors.primary), indicatorLine(_colors.warn)],
      },
    },
    'pane_macd',
  )

  applyData()
}

watch(
  () => props.bars,
  () => applyData(),
)

onMounted(() => {
  setupChart()
  if (container.value) {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(container.value)
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  if (chart) {
    dispose(chart)
    chart = null
  }
})
</script>

<template>
  <div ref="container" class="w-full" role="img" aria-label="K 线图" />
</template>
