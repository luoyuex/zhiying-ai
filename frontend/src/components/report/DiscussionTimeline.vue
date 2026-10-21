<script setup lang="ts">
import type { DiscussionTurn, TeamDiscussion } from '@/api/ai'

withDefaults(defineProps<{ discussion: TeamDiscussion; variant?: 'card' | 'flat' }>(), {
  variant: 'card',
})

const STANCE_CLASS: Record<DiscussionTurn['stance'], string> = {
  同意: 'bg-primary-soft text-primary',
  补充: 'bg-surface-2 text-ink-3',
  质疑: 'bg-warn-soft text-warn',
}

const DOT_CLASS: Record<DiscussionTurn['stance'], string> = {
  同意: 'bg-primary',
  补充: 'bg-line-strong',
  质疑: 'bg-warn',
}
</script>

<template>
  <section
    :class="
      variant === 'card'
        ? 'rounded-lg border border-line bg-canvas p-5'
        : 'rounded-md border border-line bg-surface/40 p-3.5'
    "
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <h2 :class="variant === 'card' ? 'text-sm font-semibold' : 'text-xs font-medium'" class="text-ink">
          团队讨论
        </h2>
        <span
          class="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
          :class="
            discussion.source === 'llm'
              ? 'bg-primary-soft text-primary'
              : 'bg-surface-2 text-ink-3'
          "
        >
          {{ discussion.source === 'llm' ? 'LLM 讨论' : '规则汇总' }}
        </span>
      </div>
      <span class="text-[11px] text-ink-3">{{ discussion.turns.length }} 轮发言</span>
    </div>

    <p v-if="discussion.summary" class="mt-2 text-xs leading-relaxed text-ink-2">
      {{ discussion.summary }}
    </p>

    <ol v-if="discussion.turns.length" class="mt-3 space-y-3 border-l border-line pl-4">
      <li v-for="(turn, index) in discussion.turns" :key="index" class="relative">
        <span
          class="absolute -left-5 top-1.5 size-2 rounded-full ring-2 ring-canvas"
          :class="DOT_CLASS[turn.stance]"
        />
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
          <span class="font-medium text-ink">{{ turn.speaker }}</span>
          <template v-if="turn.target">
            <span class="text-ink-3" aria-hidden="true">→</span>
            <span class="text-ink-2">{{ turn.target }}</span>
          </template>
          <span class="rounded-full px-1.5 py-0.5 text-[10px]" :class="STANCE_CLASS[turn.stance]">
            {{ turn.stance }}
          </span>
        </div>
        <p class="mt-1 text-xs leading-relaxed text-ink-2">{{ turn.content }}</p>
      </li>
    </ol>
  </section>
</template>
