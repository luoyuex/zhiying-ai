<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()

const navOpen = ref(false)
const closeButtonRef = ref<HTMLButtonElement | null>(null)

interface NavItem {
  label: string
  to: string
}

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: '概览',
    items: [{ label: '运营总览', to: '/admin' }],
  },
  {
    label: '运营',
    items: [
      { label: '成本日报', to: '/admin/costs' },
      { label: '任务中心', to: '/admin/jobs' },
      { label: '定时执行', to: '/admin/automation' },
      { label: '内容库', to: '/admin/content' },
    ],
  },
  {
    label: '账号',
    items: [{ label: '用户与额度', to: '/admin/users' }],
  },
  {
    label: '系统',
    items: [{ label: '审计日志', to: '/admin/audit' }],
  },
]

const currentTitle = computed(() => {
  const title = route.meta.title
  return typeof title === 'string' && title ? title : '后台管理'
})

const desktopQuery = window.matchMedia('(min-width: 768px)')

function onDesktopChange(event: MediaQueryListEvent): void {
  if (event.matches) closeNav()
}

function isActive(to: string): boolean {
  return to === '/admin' ? route.path === '/admin' : route.path.startsWith(to)
}

function openNav(): void {
  navOpen.value = true
}

function closeNav(): void {
  navOpen.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && navOpen.value) closeNav()
}

watch(navOpen, async (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) {
    await nextTick()
    closeButtonRef.value?.focus()
  }
})

watch(
  () => route.fullPath,
  () => closeNav(),
)

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  desktopQuery.addEventListener('change', onDesktopChange)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  desktopQuery.removeEventListener('change', onDesktopChange)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="min-h-screen bg-surface">
    <div class="mx-auto flex min-h-screen max-w-[1440px]">
      <aside
        class="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-canvas px-3 py-5 md:flex"
      >
        <RouterLink to="/admin" class="flex items-center gap-2.5 px-2">
          <img
            src="/logo-mark-128.png"
            alt=""
            width="28"
            height="28"
            class="size-7 shrink-0"
            aria-hidden="true"
          />
          <div class="leading-tight">
            <div class="text-sm font-semibold text-ink">智盈 AI</div>
            <div class="mt-0.5 text-[11px] text-ink-3">管理后台</div>
          </div>
        </RouterLink>

        <nav class="mt-7 flex-1 space-y-5">
          <div v-for="group in navGroups" :key="group.label">
            <div
              class="px-2 text-[10px] font-medium tracking-[0.14em] text-ink-3"
            >
              {{ group.label }}
            </div>
            <div class="mt-1.5 space-y-0.5">
              <RouterLink
                v-for="item in group.items"
                :key="item.to"
                :to="item.to"
                class="block rounded-md px-2.5 py-2 text-[13px] transition-colors"
                :class="
                  isActive(item.to)
                    ? 'bg-surface-2 font-medium text-ink'
                    : 'text-ink-2 hover:bg-surface hover:text-ink'
                "
              >
                {{ item.label }}
              </RouterLink>
            </div>
          </div>
        </nav>

        <div class="border-t border-line pt-3">
          <div class="px-2">
            <div class="truncate text-[12px] font-medium text-ink">
              {{ auth.user?.nickname || '管理员' }}
            </div>
            <div class="mt-0.5 truncate text-[11px] text-ink-3">
              {{ auth.user?.email }}
            </div>
          </div>
          <RouterLink
            to="/"
            class="mt-2 flex items-center gap-1.5 rounded-md px-2.5 py-2 text-[13px] text-ink-2 transition-colors hover:bg-surface hover:text-ink"
          >
            <svg
              class="size-3.5 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              aria-hidden="true"
            >
              <path d="M14 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            返回工作台
          </RouterLink>
        </div>
      </aside>

      <div class="min-w-0 flex-1">
        <header
          class="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur md:hidden"
        >
          <div class="flex h-14 items-center gap-2 px-3">
            <button
              type="button"
              class="flex min-w-0 items-center gap-2 rounded-md py-1.5 pl-1 pr-2 text-left transition-colors active:bg-surface-2"
              aria-haspopup="dialog"
              :aria-expanded="navOpen"
              @click="openNav"
            >
              <svg
                class="size-5 shrink-0 text-ink-2"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" />
              </svg>
              <span class="min-w-0">
                <span
                  class="block truncate text-[13px] font-semibold leading-tight text-ink"
                >
                  智盈 AI
                </span>
                <span
                  class="mt-0.5 block truncate text-[11px] leading-tight text-ink-3"
                >
                  {{ currentTitle }}
                </span>
              </span>
            </button>
            <RouterLink
              to="/"
              class="ml-auto flex shrink-0 items-center gap-1 rounded-md px-2 py-2 text-xs text-ink-2 transition-colors active:bg-surface-2"
            >
              <svg
                class="size-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="M14 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              工作台
            </RouterLink>
          </div>
        </header>

        <main class="mx-auto max-w-[1200px] px-6 py-6 sm:px-8 sm:py-8">
          <RouterView />
        </main>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="navOpen" class="fixed inset-0 z-50 md:hidden">
        <div class="absolute inset-0 bg-ink/35" @click="closeNav" />
        <div
          id="admin-mobile-nav"
          role="dialog"
          aria-modal="true"
          aria-label="后台导航"
          class="absolute inset-x-0 bottom-0 flex max-h-[85vh] flex-col rounded-t-2xl bg-canvas pb-[env(safe-area-inset-bottom)] shadow-pop"
        >
          <div class="flex items-start justify-between gap-3 px-5 pb-2 pt-4">
            <div class="min-w-0">
              <div class="text-sm font-semibold text-ink">智盈 AI</div>
              <div class="mt-0.5 truncate text-[11px] text-ink-3">
                {{ auth.user?.email }}
              </div>
            </div>
            <button
              ref="closeButtonRef"
              type="button"
              class="flex size-9 shrink-0 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
              aria-label="关闭导航"
              @click="closeNav"
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
          </div>

          <nav class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 pb-3">
            <div v-for="group in navGroups" :key="group.label" class="mt-3">
              <div
                class="px-3 text-[10px] font-medium tracking-[0.14em] text-ink-3"
              >
                {{ group.label }}
              </div>
              <RouterLink
                v-for="item in group.items"
                :key="item.to"
                :to="item.to"
                class="mt-1 flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors"
                :class="
                  isActive(item.to)
                    ? 'bg-surface-2 font-medium text-ink'
                    : 'text-ink-2 active:bg-surface'
                "
                @click="closeNav"
              >
                {{ item.label }}
                <svg
                  v-if="isActive(item.to)"
                  class="size-4 shrink-0 text-ink"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  aria-hidden="true"
                >
                  <path d="M5 12.5l4.5 4.5L19 7" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </RouterLink>
            </div>
          </nav>

          <div class="px-4 pb-3 pt-2">
            <RouterLink
              to="/"
              class="flex items-center justify-center gap-1.5 rounded-lg bg-surface px-4 py-2.5 text-sm text-ink-2 active:bg-surface-2"
            >
              <svg
                class="size-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
                <path d="M14 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              返回工作台
            </RouterLink>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
