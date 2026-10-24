<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: string
  label?: string
}>()

const LABELS: Record<string, string> = {
  active: '正常',
  banned: '已封禁',
  admin: '管理员',
  user: '普通用户',
  succeeded: '成功',
  failed: '失败',
  queued: '排队中',
  running: '运行中',
  manual: '手动',
  scheduled: '定时',
  revoked: '已撤销',
  expired: '已过期',
}

const text = computed(() => props.label ?? LABELS[props.value] ?? props.value)

const tone = computed(() => {
  if (props.value === 'banned' || props.value === 'failed') {
    return 'bg-danger-soft text-danger'
  }
  if (props.value === 'admin') return 'bg-primary-soft text-primary'
  if (props.value === 'active' || props.value === 'succeeded') {
    return 'bg-surface-2 text-ink'
  }
  return 'bg-surface-2 text-ink-3'
})
</script>

<template>
  <span
    class="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium"
    :class="tone"
  >
    {{ text }}
  </span>
</template>
