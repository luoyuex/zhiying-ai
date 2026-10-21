<script setup lang="ts">
defineProps<{
  label: string
  for?: string
  hint?: string
  error?: string
}>()
</script>

<template>
  <div class="space-y-1.5">
    <div class="flex items-baseline justify-between gap-3">
      <label :for="$props.for" class="text-[13px] font-medium text-ink">{{ label }}</label>
      <span v-if="hint" class="text-xs text-ink-3">{{ hint }}</span>
    </div>
    <slot />
    <p v-if="error" class="text-xs text-danger">{{ error }}</p>
  </div>
</template>
