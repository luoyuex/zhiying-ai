<script setup lang="ts">
import { ref, watch } from 'vue'

const model = defineModel<string>({ default: '' })

const inputs = ref<HTMLInputElement[]>([])
const digits = ref<string[]>(['', '', '', '', '', ''])

watch(
  () => model.value,
  (value) => {
    const normalized = value
      .replace(/\D/g, '')
      .slice(0, 6)
      .padEnd(6, ' ')
      .split('')
      .map((char) => (char === ' ' ? '' : char))
    if (normalized.join('') !== digits.value.join('')) {
      digits.value = normalized
    }
  },
  { immediate: true },
)

function setInput(el: Element | null, index: number): void {
  if (el instanceof HTMLInputElement) {
    inputs.value[index] = el
  }
}

function sync(): void {
  model.value = digits.value.join('')
}

function focusAt(index: number): void {
  const el = inputs.value[index]
  if (el) {
    el.focus()
    el.select()
  }
}

function onInput(index: number, event: Event): void {
  const el = event.target as HTMLInputElement
  const chars = el.value.replace(/\D/g, '')

  if (!chars) {
    digits.value[index] = ''
    sync()
    return
  }

  let cursor = index
  for (const char of chars) {
    if (cursor > 5) break
    digits.value[cursor] = char
    cursor += 1
  }
  sync()
  focusAt(Math.min(cursor, 5))
}

function onKeydown(index: number, event: KeyboardEvent): void {
  if (event.key === 'Backspace') {
    if (digits.value[index]) {
      digits.value[index] = ''
      sync()
      return
    }
    event.preventDefault()
    if (index > 0) {
      digits.value[index - 1] = ''
      sync()
      focusAt(index - 1)
    }
    return
  }
  if (event.key === 'ArrowLeft' && index > 0) focusAt(index - 1)
  if (event.key === 'ArrowRight' && index < 5) focusAt(index + 1)
}
</script>

<template>
  <div
    class="flex h-10 w-full divide-x divide-line overflow-hidden rounded-md border border-line-strong bg-canvas transition-colors duration-150 focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/15"
  >
    <input
      v-for="(digit, index) in digits"
      :key="index"
      :ref="(el) => setInput(el as Element | null, index)"
      :value="digit"
      :aria-label="`验证码第 ${index + 1} 位`"
      type="text"
      inputmode="numeric"
      maxlength="6"
      autocomplete="one-time-code"
      class="h-full w-full min-w-0 bg-transparent text-center text-[17px] font-semibold leading-10 tabular-nums text-ink caret-primary outline-none transition-colors duration-150 focus:bg-primary-soft/70"
      @input="onInput(index, $event)"
      @keydown="onKeydown(index, $event)"
      @focus="($event.target as HTMLInputElement).select()"
    />
  </div>
</template>
