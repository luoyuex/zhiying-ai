<script setup lang="ts">
defineProps<{
  restoring: boolean
  phase: string
  elapsed: number
}>()
</script>

<template>
  <div class="rounded-lg border border-line bg-canvas px-4 py-12 text-center">
    <span
      class="mx-auto mb-3 block size-5 animate-spin rounded-full border-2 border-ink-3/25 border-t-ink-3"
    />
    <div class="text-xs font-medium text-ink-2">
      {{ restoring ? '正在恢复上次选股结果…' : phase || '正在发起 AI 选股…' }}
    </div>
    <p v-if="!restoring" class="mt-1 text-[11px] leading-relaxed text-ink-3">
      三位分析师整体分析，随后由资深研究员精选。
    </p>
    <p v-if="!restoring && elapsed > 0" class="mt-1 text-[10px] text-ink-3">
      已用时 {{ elapsed }} 秒 · 刷新页面后会自动续上进度
    </p>
  </div>
</template>
