<script setup lang="ts">
import { computed } from 'vue'

const model = defineModel<string>({ default: '' })

const props = withDefaults(
  defineProps<{
    type?: string
    placeholder?: string
    autocomplete?: string
    invalid?: boolean
    disabled?: boolean
    inputmode?: 'text' | 'numeric' | 'email'
    size?: 'sm' | 'md'
  }>(),
  {
    type: 'text',
    placeholder: '',
    autocomplete: 'off',
    invalid: false,
    disabled: false,
    inputmode: 'text',
    size: 'md',
  },
)

const sizeClass = computed(() =>
  props.size === 'sm' ? 'h-8 text-[13px] leading-8' : 'h-10 text-sm leading-10',
)
</script>

<template>
  <input
    v-model="model"
    :type="type"
    :placeholder="placeholder"
    :autocomplete="autocomplete"
    :disabled="disabled"
    :inputmode="inputmode"
    class="w-full min-w-0 rounded-md border bg-canvas px-3 text-ink transition-colors duration-150 placeholder:text-ink-3 focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
    :class="[
      sizeClass,
      invalid
        ? 'border-danger focus:border-danger focus:ring-2 focus:ring-danger/15'
        : 'border-line-strong focus:border-primary focus:ring-2 focus:ring-primary/15',
    ]"
  />
</template>
