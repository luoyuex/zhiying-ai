<script setup lang="ts">
const model = defineModel<string>({ default: '' })

withDefaults(
  defineProps<{
    type?: string
    placeholder?: string
    autocomplete?: string
    invalid?: boolean
    disabled?: boolean
    inputmode?: 'text' | 'numeric' | 'email'
  }>(),
  {
    type: 'text',
    placeholder: '',
    autocomplete: 'off',
    invalid: false,
    disabled: false,
    inputmode: 'text',
  },
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
    class="h-10 w-full min-w-0 rounded-md border bg-canvas px-3 text-sm leading-10 text-ink transition-colors duration-150 placeholder:text-ink-3 focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-2"
    :class="
      invalid
        ? 'border-danger focus:border-danger focus:ring-2 focus:ring-danger/15'
        : 'border-line-strong focus:border-primary focus:ring-2 focus:ring-primary/15'
    "
  />
</template>
