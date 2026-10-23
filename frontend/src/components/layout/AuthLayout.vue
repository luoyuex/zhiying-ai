<template>
  <div class="min-h-screen bg-canvas lg:grid lg:grid-cols-[minmax(0,1fr)_480px]">
    <!-- 品牌区 -->
    <aside
      class="relative hidden overflow-hidden border-r border-line bg-surface lg:flex lg:flex-col lg:justify-between lg:px-14 lg:py-12"
    >
      <div class="brand-grid pointer-events-none absolute inset-0" />

      <div class="relative">
        <a href="/" class="inline-flex flex-col gap-2.5" aria-label="返回智盈 AI 官网">
          <img
            src="/logo-wordmark-480.png"
            alt="智盈 AI"
            width="480"
            height="165"
            class="h-12 w-auto"
          />
          <span class="text-xs text-ink-3">A 股 AI 分析工作台</span>
        </a>
      </div>

      <div class="relative max-w-[420px]">
        <h1 class="text-[28px] font-semibold leading-[1.25] tracking-tight text-ink">
          把一只股票，<br />交给六个分析师一起看。
        </h1>
        <p class="mt-4 text-sm leading-relaxed text-ink-2">
          技术面、基本面、资金面、情绪、新闻与风险，六个视角并行分析，再由首席策略官汇总成一份可执行的结论。
        </p>

        <ul class="mt-10 space-y-4">
          <li v-for="item in features" :key="item.title" class="flex gap-3">
            <span
              class="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-sm bg-primary-soft text-[11px] font-semibold text-primary"
            >
              {{ item.index }}
            </span>
            <div>
              <div class="text-[13px] font-medium text-ink">{{ item.title }}</div>
              <div class="mt-0.5 text-xs leading-relaxed text-ink-3">{{ item.desc }}</div>
            </div>
          </li>
        </ul>
      </div>

      <p class="relative text-xs leading-relaxed text-ink-3">
        本工具输出仅为研究参考，不构成任何投资建议。
      </p>
    </aside>

    <!-- 表单区 -->
    <main class="flex min-h-screen flex-col justify-center px-6 py-10 sm:px-10">
      <div class="mx-auto w-full max-w-[400px]">
        <a href="/" class="mb-8 flex items-center gap-2.5 lg:hidden" aria-label="返回智盈 AI 官网">
          <img
            src="/logo-mark-128.png"
            alt=""
            width="32"
            height="32"
            class="size-8 shrink-0"
            aria-hidden="true"
          />
          <span class="text-sm font-semibold text-ink">智盈 AI</span>
        </a>
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
const features = [
  { index: '01', title: '多智能体协作', desc: '六个分析师并行出报告，再开会讨论、下结论' },
  { index: '02', title: '结论可追溯', desc: '每个数字都带来源与时间戳，AI 结论可回溯' },
  { index: '03', title: '价格由代码算', desc: '入场、止盈、止损不交给模型猜，规则统一可复现' },
]
</script>
