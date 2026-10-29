<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from '@/utils/markdown'

const props = withDefaults(
  defineProps<{
    content?: string | null
    emptyText?: string
    size?: 'xs' | 'sm'
  }>(),
  { content: '', emptyText: '暂无内容', size: 'xs' },
)

const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div
    v-if="html"
    class="md-body"
    :class="size === 'sm' ? 'text-[12px]' : 'text-[11px]'"
    v-html="html"
  />
  <p v-else class="text-[11px] text-ink-3">{{ emptyText }}</p>
</template>

<style scoped>
.md-body {
  color: var(--color-ink-2);
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.md-body :deep(> :first-child) {
  margin-top: 0;
}

.md-body :deep(> :last-child) {
  margin-bottom: 0;
}

.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 1.15em 0 0.45em;
  font-weight: 600;
  line-height: 1.4;
  color: var(--color-ink);
}

.md-body :deep(h1) {
  font-size: 1.15em;
}

.md-body :deep(h2) {
  font-size: 1.05em;
}

.md-body :deep(h3) {
  font-size: 1em;
}

.md-body :deep(h4) {
  font-size: 0.95em;
  color: var(--color-ink-2);
}

.md-body :deep(p) {
  margin: 0.55em 0;
}

/* 模型常把整行加粗当作小标题（如「**二、重点个股资金行为分析**」） */
.md-body :deep(p:has(> strong:only-child)) {
  margin-top: 0.95em;
  color: var(--color-ink);
}

.md-body :deep(p:empty) {
  display: none;
}

.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 0;
}

.md-body :deep(ul) {
  list-style: none;
}

.md-body :deep(ul > li) {
  position: relative;
  padding-left: 0.85em;
}

.md-body :deep(ul > li)::before {
  content: '';
  position: absolute;
  top: 0.72em;
  left: 0.18em;
  width: 0.27em;
  height: 0.27em;
  border-radius: 999px;
  background: var(--color-ink-3);
}

.md-body :deep(ol) {
  list-style: decimal;
  padding-left: 1.35em;
}

.md-body :deep(li) {
  margin: 0.32em 0;
}

.md-body :deep(li::marker) {
  color: var(--color-ink-3);
}

.md-body :deep(li > ul),
.md-body :deep(li > ol) {
  margin: 0.25em 0;
  padding-left: 0.9em;
}

.md-body :deep(strong) {
  font-weight: 600;
  color: var(--color-ink);
}

/* 中文斜体观感差，强调只做颜色加深 */
.md-body :deep(em) {
  font-style: normal;
  color: var(--color-ink);
}

.md-body :deep(code) {
  padding: 0.1em 0.3em;
  border-radius: 4px;
  background: var(--color-surface-2);
  font-family: var(--font-mono);
  font-size: 0.94em;
}

.md-body :deep(pre) {
  margin: 0.6em 0;
  padding: 0.7em 0.85em;
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  overflow-x: auto;
}

.md-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.md-body :deep(blockquote) {
  margin: 0.6em 0;
  padding-left: 0.7em;
  border-left: 2px solid var(--color-line-strong);
  color: var(--color-ink-3);
}

.md-body :deep(hr) {
  margin: 0.9em 0;
  border: 0;
  border-top: 1px solid var(--color-line);
}

.md-body :deep(table) {
  width: 100%;
  margin: 0.6em 0;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 0.96em;
}

.md-body :deep(th),
.md-body :deep(td) {
  padding: 0.32em 0.45em;
  border-bottom: 1px solid var(--color-line);
  text-align: left;
  vertical-align: top;
}

.md-body :deep(th) {
  font-weight: 500;
  color: var(--color-ink-3);
}

.md-body :deep(a) {
  color: var(--color-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.md-body :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-sm);
}
</style>
