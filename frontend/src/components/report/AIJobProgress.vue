<script setup lang="ts">
defineProps<{
  phase: string
  elapsed: number
}>()
</script>

<template>
  <div
    class="flex items-center gap-2 rounded-md bg-primary-soft px-3 py-2 text-xs text-primary-hover"
  >
    <span
      class="size-3.5 shrink-0 animate-spin rounded-full border-2 border-primary/30 border-t-primary"
    />
    <span class="min-w-0 leading-relaxed">
      {{ phase || '排队中' }} · 已等待 {{ elapsed }} 秒
    </span>
  </div>
</template>
