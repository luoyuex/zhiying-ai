<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import { SITE_INFO, DONATE_QR } from '@/config/site'

const open = defineModel<boolean>({ required: true })

const closeButtonRef = ref<HTMLButtonElement | null>(null)
const qrReady = reactive({ wechat: false, alipay: false })

function close(): void {
  open.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) close()
}

watch(open, async (value) => {
  document.body.style.overflow = value ? 'hidden' : ''
  if (!value) return

  qrReady.wechat = false
  qrReady.alipay = false
  await nextTick()
  closeButtonRef.value?.focus()
})

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-ink/35" @click="close" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-dialog-title"
        class="relative flex max-h-[min(720px,92vh)] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-canvas shadow-pop"
      >
        <header class="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <p class="text-[10px] tracking-[0.14em] text-ink-3">ABOUT &amp; SUPPORT</p>
            <h2
              id="about-dialog-title"
              class="mt-1 text-xl font-semibold tracking-tight text-ink"
            >
              关于我们
            </h2>
            <p class="mt-1 text-[11px] text-ink-3">个人项目 · 非商业运营 · 自愿支持</p>
          </div>
          <button
            ref="closeButtonRef"
            type="button"
            class="flex size-8 shrink-0 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
            aria-label="关闭关于我们"
            @click="close"
          >
            <svg
              class="size-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              aria-hidden="true"
            >
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
            </svg>
          </button>
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div class="grid gap-6 sm:grid-cols-[minmax(0,1fr)_300px]">
            <div class="min-w-0">
              <p class="text-[13px] leading-[1.85] text-ink-2">
                智盈 AI 是我在业余时间维护的个人项目。没有公司主体，没有融资，也没有广告、会员或付费课程。站点以个人名义备案，功能免费开放，所有输出只作为研究参考。
              </p>

              <dl class="mt-5 grid grid-cols-2 gap-x-5 gap-y-3 border-t border-line pt-4">
                <div>
                  <dt class="text-[10px] text-ink-3">运营方式</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">个人业余维护</dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">站点性质</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">非商业 · 个人备案</dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">费用去向</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">服务器 · 数据接口 · 模型调用</dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">功能政策</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">全部免费，不设付费墙</dd>
                </div>
              </dl>

              <dl class="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 border-t border-line pt-4">
                <div>
                  <dt class="text-[10px] text-ink-3">备案信息</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">
                    <a
                      :href="SITE_INFO.icpUrl"
                      target="_blank"
                      rel="noopener"
                      class="underline decoration-line-strong underline-offset-2 hover:decoration-ink"
                    >
                      {{ SITE_INFO.icp }}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">联系邮箱</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">
                    <a
                      :href="`mailto:${SITE_INFO.email}`"
                      class="underline decoration-line-strong underline-offset-2 hover:decoration-ink"
                    >
                      {{ SITE_INFO.email }}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">数据来源</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">腾讯 · 新浪 · 东方财富</dd>
                </div>
                <div>
                  <dt class="text-[10px] text-ink-3">内容边界</dt>
                  <dd class="mt-0.5 text-[12px] text-ink">研究参考，不构成投资建议</dd>
                </div>
              </dl>
            </div>

            <aside class="rounded-lg bg-surface p-4" aria-labelledby="about-donate-title">
              <p class="text-[10px] tracking-[0.12em] text-ink-3">VOLUNTARY SUPPORT</p>
              <h3 id="about-donate-title" class="mt-1.5 text-[16px] font-semibold text-ink">
                让服务器继续跑下去
              </h3>
              <p class="mt-1.5 text-[11.5px] leading-relaxed text-ink-2">
                捐赠全部用于覆盖站点的固定开销，金额随意。它不购买服务，也不换取任何权益。
              </p>

              <ul class="mt-3 border-t border-line">
                <li
                  class="flex justify-between gap-3 border-b border-line py-1.5 text-[11px]"
                >
                  <span class="text-ink">服务器与带宽</span>
                  <span class="text-ink-3">固定月度开销</span>
                </li>
                <li
                  class="flex justify-between gap-3 border-b border-line py-1.5 text-[11px]"
                >
                  <span class="text-ink">行情与财务数据</span>
                  <span class="text-ink-3">按接口调用</span>
                </li>
                <li
                  class="flex justify-between gap-3 border-b border-line py-1.5 text-[11px]"
                >
                  <span class="text-ink">AI 模型调用</span>
                  <span class="text-ink-3">随分析次数增长</span>
                </li>
              </ul>

              <div class="mt-3 grid grid-cols-2 gap-2">
                <figure>
                  <div
                    class="relative grid aspect-square place-items-center overflow-hidden rounded-md bg-canvas"
                  >
                    <img
                      :src="DONATE_QR.wechat"
                      alt="微信赞赏码"
                      width="320"
                      height="320"
                      class="size-full object-contain"
                      :class="qrReady.wechat ? 'block' : 'hidden'"
                      @load="qrReady.wechat = true"
                      @error="qrReady.wechat = false"
                    />
                    <span
                      v-if="!qrReady.wechat"
                      class="flex flex-col items-center gap-1.5 px-2 text-center text-[10.5px] leading-snug text-ink-3"
                    >
                      <svg
                        class="size-5 opacity-55"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.5"
                        aria-hidden="true"
                      >
                        <rect x="3.5" y="3.5" width="6" height="6" rx="1" />
                        <rect x="14.5" y="3.5" width="6" height="6" rx="1" />
                        <rect x="3.5" y="14.5" width="6" height="6" rx="1" />
                        <path
                          d="M14.5 14.5h2.5v2.5h-2.5zM19 19h1.5v1.5H19zM14.5 20.5H17M20.5 14.5V17"
                          stroke-linecap="round"
                        />
                      </svg>
                      赞赏码准备中
                    </span>
                  </div>
                  <figcaption class="mt-1.5 text-center text-[10.5px] text-ink-2">
                    微信
                  </figcaption>
                </figure>

                <figure>
                  <div
                    class="relative grid aspect-square place-items-center overflow-hidden rounded-md bg-canvas"
                  >
                    <img
                      :src="DONATE_QR.alipay"
                      alt="支付宝收款码"
                      width="320"
                      height="320"
                      class="size-full object-contain"
                      :class="qrReady.alipay ? 'block' : 'hidden'"
                      @load="qrReady.alipay = true"
                      @error="qrReady.alipay = false"
                    />
                    <span
                      v-if="!qrReady.alipay"
                      class="flex flex-col items-center gap-1.5 px-2 text-center text-[10.5px] leading-snug text-ink-3"
                    >
                      <svg
                        class="size-5 opacity-55"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.5"
                        aria-hidden="true"
                      >
                        <rect x="3.5" y="3.5" width="6" height="6" rx="1" />
                        <rect x="14.5" y="3.5" width="6" height="6" rx="1" />
                        <rect x="3.5" y="14.5" width="6" height="6" rx="1" />
                        <path
                          d="M14.5 14.5h2.5v2.5h-2.5zM19 19h1.5v1.5H19zM14.5 20.5H17M20.5 14.5V17"
                          stroke-linecap="round"
                        />
                      </svg>
                      收款码准备中
                    </span>
                  </div>
                  <figcaption class="mt-1.5 text-center text-[10.5px] text-ink-2">
                    支付宝
                  </figcaption>
                </figure>
              </div>

              <p class="mt-2 text-[10px] leading-relaxed text-ink-3">
                扫码或长按识别。个人收款，不开具发票，也不构成任何服务承诺。
              </p>
            </aside>
          </div>

          <div
            class="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3"
          >
            <p class="max-w-[62ch] text-[10.5px] leading-relaxed text-ink-3">
              所有输出仅用于技术研究与学习参考，不构成投资建议。捐赠为自愿行为，不购买服务、不换取权益、不开具发票。
            </p>
            <a
              href="/#about"
              class="shrink-0 text-[11px] text-ink-3 underline decoration-line-strong underline-offset-2 transition-colors hover:text-ink"
            >
              查看官网介绍 ↗
            </a>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
