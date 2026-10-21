<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost'
    size?: 'sm' | 'md'
    loading?: boolean
    disabled?: boolean
    type?: 'button' | 'submit'
    block?: boolean
  }>(),
  {
    variant: 'primary',
    size: 'md',
    loading: false,
    disabled: false,
    type: 'button',
    block: false,
  },
)

const variantClass = computed(() => {
  if (props.variant === 'secondary') {
    return 'border border-line-strong bg-canvas text-ink hover:border-ink-3 hover:bg-surface'
  }
  if (props.variant === 'ghost') {
    return 'text-ink-2 hover:bg-surface-2 hover:text-ink'
  }
  return 'bg-primary text-white hover:bg-primary-hover'
})

const sizeClass = computed(() =>
  props.size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-10 px-4 text-sm',
)
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="inline-flex select-none items-center justify-center gap-2 rounded-md font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50"
    :class="[variantClass, sizeClass, block ? 'w-full' : '']"
  >
    <span
      v-if="loading"
      class="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-80"
    />
    <slot />
  </button>
</template>
