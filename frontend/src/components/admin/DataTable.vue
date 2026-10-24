<script setup lang="ts">
defineProps<{
  columns: {
    key: string
    label: string
    align?: 'left' | 'right'
    width?: string
  }[]
}>()
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full min-w-[760px] text-left text-[13px]">
      <thead>
        <tr class="border-b border-line bg-surface/60 text-[11px] text-ink-3">
          <th
            v-for="column in columns"
            :key="column.key"
            class="px-4 py-2.5 font-medium"
            :class="column.align === 'right' ? 'text-right' : 'text-left'"
            :style="column.width ? { width: column.width } : undefined"
          >
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-line">
        <slot />
      </tbody>
    </table>
  </div>
</template>
