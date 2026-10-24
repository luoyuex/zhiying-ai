<script setup lang="ts">
import { computed } from 'vue'

import Button from '@/components/ui/Button.vue'

const props = defineProps<{
  page: number
  pageSize: number
  total: number
}>()

const emit = defineEmits<{
  (event: 'update:page', value: number): void
  (event: 'update:pageSize', value: number): void
}>()

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

function onSizeChange(event: Event): void {
  const value = Number((event.target as HTMLSelectElement).value)
  emit('update:pageSize', value)
  emit('update:page', 1)
}
</script>

<template>
  <div
    class="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-[11px] text-ink-3"
  >
    <span class="tabular-nums">
      共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页
    </span>
    <div class="flex items-center gap-2">
      <select
        :value="pageSize"
        aria-label="每页条数"
        class="h-8 rounded-md border border-line bg-canvas px-2 text-xs text-ink focus:outline-none"
        @change="onSizeChange"
      >
        <option :value="20">20 / 页</option>
        <option :value="50">50 / 页</option>
        <option :value="100">100 / 页</option>
      </select>
      <Button
        variant="secondary"
        size="sm"
        :disabled="page <= 1"
        @click="emit('update:page', page - 1)"
      >
        上一页
      </Button>
      <Button
        variant="secondary"
        size="sm"
        :disabled="page >= pages"
        @click="emit('update:page', page + 1)"
      >
        下一页
      </Button>
    </div>
  </div>
</template>
