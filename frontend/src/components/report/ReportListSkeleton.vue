<script setup lang="ts">
withDefaults(defineProps<{ rows?: number }>(), { rows: 5 })
</script>

<template>
  <div class="divide-y divide-line">
    <div v-for="index in rows" :key="index" class="flex items-center gap-3 px-4 py-4">
      <div class="h-6 w-12 animate-pulse rounded bg-surface-2" />
      <div class="flex-1 space-y-2">
        <div class="h-4 w-40 animate-pulse rounded bg-surface-2" />
        <div class="h-3 w-56 animate-pulse rounded bg-surface-2" />
      </div>
      <div class="h-6 w-10 animate-pulse rounded bg-surface-2" />
    </div>
  </div>
</template>
