<script setup lang="ts">
import type { WebSource } from '@/api/ai'

withDefaults(
  defineProps<{
    used: boolean
    sources: WebSource[]
    usedBy?: string[]
    variant?: 'card' | 'flat'
  }>(),
  {
    usedBy: () => [],
    variant: 'card',
  },
)
</script>

<template>
  <section
    :class="
      variant === 'card'
        ? 'rounded-lg border border-line bg-canvas p-5'
        : 'border-t border-line pt-3'
    "
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <h2 :class="variant === 'card' ? 'text-sm font-semibold text-ink' : 'text-xs font-medium text-ink'">
          公开信息
        </h2>
        <span
          class="inline-flex items-center gap-1 rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary"
        >
          <svg
            class="size-3 shrink-0"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" stroke-linecap="round" />
          </svg>
          元宝搜索
        </span>
        <span v-if="used && sources.length" class="text-[11px] text-ink-3">
          已检索 {{ sources.length }} 条
        </span>
        <span v-else class="text-[11px] text-ink-3">本次未收录</span>
      </div>
      <span class="text-[11px] text-ink-3">腾讯元宝 · 公开网页</span>
    </div>

    <p v-if="!used || !sources.length" class="mt-2 text-[11px] leading-relaxed text-ink-3">
      本次报告未包含公开网页信息；新闻/公告相关结论已按数据缺口处理，不臆造事件。公开网页检索由腾讯元宝搜索提供。
    </p>

    <template v-else>
      <p class="mt-2 text-[11px] leading-relaxed text-ink-3">
        以下信息由元宝搜索检索，仅作新闻/事件背景；涉及公告与财务事实时以结构化数据为准。
      </p>
      <p v-if="usedBy.length" class="mt-1 text-[11px] font-medium text-ink-2">
        已用于：{{ usedBy.join('、') }}
      </p>
      <ul class="mt-3 space-y-2">
        <li
          v-for="source in sources"
          :key="source.url"
          class="text-xs leading-relaxed"
        >
          <a
            :href="source.url"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-primary underline-offset-2 hover:text-primary-hover hover:underline"
          >
            {{ source.title }}
          </a>
          <span class="ml-1 text-[11px] text-ink-3">
            {{ [source.site, source.date].filter(Boolean).join(' · ') }}
          </span>
        </li>
      </ul>
    </template>
  </section>
</template>
