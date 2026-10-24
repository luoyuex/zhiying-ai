<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    hint?: string
    tone?: 'default' | 'warn' | 'danger'
  }>(),
  {
    hint: '',
    tone: 'default',
  },
)

const valueClass = computed(() => {
  if (props.tone === 'danger') return 'text-danger'
  if (props.tone === 'warn') return 'text-warn'
  return 'text-ink'
})
</script>

<template>
  <div class="rounded-lg border border-line bg-canvas p-5">
    <div class="text-xs text-ink-3">{{ label }}</div>
    <div
      class="mt-2 text-[28px] font-semibold leading-none tracking-tight tabular-nums"
      :class="valueClass"
    >
      {{ value }}
    </div>
    <div v-if="hint" class="mt-2 text-[11px] text-ink-3">{{ hint }}</div>
  </div>
</template>
