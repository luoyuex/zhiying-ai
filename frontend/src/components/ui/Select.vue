<script setup lang="ts" generic="T extends string | number">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'

interface SelectOption<T> {
  label: string
  value: T
}

const model = defineModel<T>({ required: true })

const props = withDefaults(
  defineProps<{
    options: SelectOption<T>[]
    size?: 'sm' | 'md' | 'lg'
    placeholder?: string
    disabled?: boolean
  }>(),
  {
    size: 'md',
    placeholder: '',
    disabled: false,
  },
)

const open = ref(false)
const activeIndex = ref(-1)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const listRef = ref<HTMLElement | null>(null)
const listId = useId()

const selectedIndex = computed(() =>
  props.options.findIndex((option) => option.value === model.value),
)
const selectedLabel = computed(
  () => props.options[selectedIndex.value]?.label ?? props.placeholder,
)

function scrollActiveIntoView(): void {
  const el = listRef.value?.children[activeIndex.value] as HTMLElement | undefined
  el?.scrollIntoView({ block: 'nearest' })
}

function openList(): void {
  if (props.disabled || open.value) return
  open.value = true
  activeIndex.value = selectedIndex.value >= 0 ? selectedIndex.value : 0
  nextTick(scrollActiveIntoView)
}

function closeList(refocus = false): void {
  if (!open.value) return
  open.value = false
  if (refocus) triggerRef.value?.focus()
}

function toggle(): void {
  if (open.value) closeList()
  else openList()
}

function selectAt(index: number): void {
  const option = props.options[index]
  if (!option) return
  model.value = option.value
  closeList(true)
}

function moveActive(delta: number): void {
  const count = props.options.length
  if (!count) return
  if (!open.value) {
    openList()
    return
  }
  const base = activeIndex.value < 0 ? (delta > 0 ? -1 : 0) : activeIndex.value
  activeIndex.value = (base + delta + count) % count
  nextTick(scrollActiveIntoView)
}

function moveTo(index: number): void {
  if (!open.value) return
  activeIndex.value = index
  nextTick(scrollActiveIntoView)
}

function onKeydown(event: KeyboardEvent): void {
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      moveActive(1)
      break
    case 'ArrowUp':
      event.preventDefault()
      moveActive(-1)
      break
    case 'Home':
      if (open.value) {
        event.preventDefault()
        moveTo(0)
      }
      break
    case 'End':
      if (open.value) {
        event.preventDefault()
        moveTo(props.options.length - 1)
      }
      break
    case 'Enter':
    case ' ':
      event.preventDefault()
      if (open.value) selectAt(activeIndex.value)
      else openList()
      break
    case 'Escape':
      if (open.value) {
        event.preventDefault()
        closeList()
      }
      break
    case 'Tab':
      closeList()
      break
  }
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (!open.value) return
  const target = event.target as Node | null
  if (target && rootRef.value && !rootRef.value.contains(target)) closeList()
}

watch(open, (isOpen) => {
  if (!isOpen) activeIndex.value = selectedIndex.value
})

onMounted(() => document.addEventListener('pointerdown', onDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointerDown))
</script>

<template>
  <div ref="rootRef" class="relative inline-block">
    <button
      ref="triggerRef"
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="open ? listId : undefined"
      :aria-activedescendant="
        open && activeIndex >= 0 ? `${listId}-option-${activeIndex}` : undefined
      "
      :disabled="disabled"
      class="inline-flex w-full items-center justify-between gap-2 rounded-md border border-line bg-canvas text-left text-xs text-ink transition-colors duration-150 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/15 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-ink-3"
      :class="
        size === 'sm'
          ? 'h-8 px-2'
          : size === 'lg'
            ? 'h-10 px-3 text-sm'
            : 'h-9 px-2.5'
      "
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="truncate">{{ selectedLabel }}</span>
      <svg
        class="size-3.5 shrink-0 text-ink-3 transition-transform duration-150"
        :class="open ? 'rotate-180' : ''"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        aria-hidden="true"
      >
        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Transition name="fade-slide">
      <div
        v-if="open"
        :id="listId"
        ref="listRef"
        role="listbox"
        class="absolute left-0 top-[calc(100%+4px)] z-30 max-h-60 min-w-full overflow-y-auto rounded-md border border-line bg-canvas p-1 shadow-pop"
      >
        <button
          v-for="(option, index) in options"
          :id="`${listId}-option-${index}`"
          :key="option.value"
          type="button"
          role="option"
          :aria-selected="option.value === model"
          class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs whitespace-nowrap transition-colors duration-100"
          :class="
            index === activeIndex
              ? 'bg-primary-soft text-primary'
              : 'text-ink-2 hover:bg-surface hover:text-ink'
          "
          @mouseenter="activeIndex = index"
          @click="selectAt(index)"
        >
          <span>{{ option.label }}</span>
          <svg
            v-if="option.value === model"
            class="ml-auto size-3.5 shrink-0"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="m5 12 5 5L20 7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
    </Transition>
  </div>
</template>
