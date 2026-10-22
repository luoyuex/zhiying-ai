<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import AccountCenterModal from './AccountCenterModal.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const menuOpen = ref(false)
const accountOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

interface NavItem {
  label: string
  to: string
  active: (path: string) => boolean
}

const NAV_ITEMS: NavItem[] = [
  { label: '首页', to: '/', active: (path) => path === '/' },
  { label: '选股', to: '/screener', active: (path) => path.startsWith('/screener') },
  { label: '自选股', to: '/watchlist', active: (path) => path.startsWith('/watchlist') },
  { label: '历史报告', to: '/reports', active: (path) => path.startsWith('/reports') },
]

function isActive(item: NavItem): boolean {
  return item.active(route.path)
}

const avatarText = computed(() => auth.user?.nickname?.trim().slice(0, 1) || '智')

function closeMenu(): void {
  menuOpen.value = false
}

function openAccount(): void {
  closeMenu()
  accountOpen.value = true
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (!menuOpen.value) return
  const target = event.target as Node | null
  if (target && menuRoot.value && !menuRoot.value.contains(target)) {
    closeMenu()
  }
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') closeMenu()
}

async function handleLogout(): Promise<void> {
  closeMenu()
  await auth.logout()
  await router.replace('/login')
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
})

watch(
  () => route.fullPath,
  () => closeMenu(),
)
</script>

<template>
  <div class="min-h-screen bg-surface">
    <header class="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
      <div class="mx-auto flex h-14 max-w-[1280px] items-center gap-4 px-6 sm:px-8 lg:px-10">
        <RouterLink to="/" class="flex shrink-0 items-center gap-3">
          <div
            class="flex size-8 items-center justify-center rounded-md bg-primary text-sm font-semibold text-white"
          >
            智
          </div>
          <div class="hidden text-left leading-tight sm:block">
            <div class="text-sm font-semibold text-ink">智盈 AI</div>
            <div class="text-[11px] text-ink-3">A 股 AI 分析工作台</div>
          </div>
        </RouterLink>

        <nav class="hidden flex-1 items-center justify-center gap-1 md:flex">
          <RouterLink
            v-for="item in NAV_ITEMS"
            :key="item.to"
            :to="item.to"
            class="relative flex h-14 items-center px-3 text-[13px] transition-colors"
            :class="isActive(item) ? 'font-medium text-ink' : 'text-ink-3 hover:text-ink'"
          >
            {{ item.label }}
            <span
              v-if="isActive(item)"
              class="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-ink"
            />
          </RouterLink>
        </nav>

        <div ref="menuRoot" class="relative ml-auto shrink-0 md:ml-0">
          <button
            type="button"
            class="flex items-center gap-2 rounded-md p-1.5 transition-colors hover:bg-surface"
            aria-haspopup="menu"
            :aria-expanded="menuOpen"
            @click="menuOpen = !menuOpen"
          >
            <span
              class="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[13px] font-semibold text-primary"
            >
              {{ avatarText }}
            </span>
            <span class="hidden text-left leading-tight sm:block">
              <span class="block max-w-36 truncate text-[13px] font-medium text-ink">
                {{ auth.user?.nickname }}
              </span>
              <span class="block max-w-36 truncate text-[11px] text-ink-3">
                {{ auth.user?.email }}
              </span>
            </span>
            <svg
              class="size-3.5 shrink-0 text-ink-3 transition-transform duration-150"
              :class="menuOpen ? 'rotate-180' : ''"
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
              v-if="menuOpen"
              class="absolute right-0 top-[calc(100%+8px)] z-30 w-64 overflow-hidden rounded-lg border border-line bg-canvas shadow-pop"
              role="menu"
              aria-label="用户菜单"
            >
              <div class="flex items-center gap-3 border-b border-line px-4 py-3">
                <span
                  class="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary"
                >
                  {{ avatarText }}
                </span>
                <div class="min-w-0 leading-tight">
                  <div class="truncate text-[13px] font-semibold text-ink">
                    {{ auth.user?.nickname }}
                  </div>
                  <div class="mt-1 truncate text-[11px] text-ink-3">
                    {{ auth.user?.email }}
                  </div>
                </div>
              </div>

              <div class="p-1.5">
                <button
                  type="button"
                  role="menuitem"
                  class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] text-ink-2 transition-colors hover:bg-surface hover:text-ink"
                  @click="openAccount"
                >
                  <svg
                    class="size-4 shrink-0"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    aria-hidden="true"
                  >
                    <circle cx="12" cy="8" r="3.5" />
                    <path d="M5 20a7 7 0 0 1 14 0" stroke-linecap="round" />
                  </svg>
                  个人中心
                </button>

                <RouterLink
                  to="/"
                  role="menuitem"
                  class="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-ink-2 transition-colors hover:bg-surface hover:text-ink"
                  @click="closeMenu"
                >
                  <svg
                    class="size-4 shrink-0"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    aria-hidden="true"
                  >
                    <rect x="3" y="3" width="7" height="7" rx="1.5" />
                    <rect x="14" y="3" width="7" height="7" rx="1.5" />
                    <rect x="3" y="14" width="7" height="7" rx="1.5" />
                    <rect x="14" y="14" width="7" height="7" rx="1.5" />
                  </svg>
                  首页
                </RouterLink>

                <RouterLink
                  to="/reports"
                  role="menuitem"
                  class="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-ink-2 transition-colors hover:bg-surface hover:text-ink"
                  @click="closeMenu"
                >
                  <svg
                    class="size-4 shrink-0"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    aria-hidden="true"
                  >
                    <path
                      d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5a1.5 1.5 0 0 1 1-1.5Z"
                      stroke-linejoin="round"
                    />
                    <path d="M13.5 3.5V8h4.5" stroke-linejoin="round" />
                    <path d="M9 12h6M9 15.5h6M9 19h4" stroke-linecap="round" />
                  </svg>
                  <span class="flex-1">历史报告</span>
                  <span class="text-[11px] text-ink-3">全部</span>
                </RouterLink>
              </div>

              <div class="border-t border-line p-1.5">
                <button
                  type="button"
                  role="menuitem"
                  class="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[13px] text-danger transition-colors hover:bg-danger-soft"
                  @click="handleLogout"
                >
                  <svg
                    class="size-4 shrink-0"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    aria-hidden="true"
                  >
                    <path d="M14 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" stroke-linecap="round" />
                    <path d="M10 8l-4 4 4 4M6 12h9" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                  退出登录
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>

      <nav
        class="flex h-10 items-center gap-5 overflow-x-auto border-t border-line px-6 md:hidden"
      >
        <RouterLink
          v-for="item in NAV_ITEMS"
          :key="item.to"
          :to="item.to"
          class="relative flex h-10 shrink-0 items-center text-[13px] transition-colors"
          :class="isActive(item) ? 'font-medium text-ink' : 'text-ink-3 hover:text-ink'"
        >
          {{ item.label }}
          <span
            v-if="isActive(item)"
            class="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-ink"
          />
        </RouterLink>
      </nav>
    </header>

    <main class="mx-auto max-w-[1280px] px-6 py-6 sm:px-8 sm:py-8 lg:px-10">
      <slot />
    </main>

    <AccountCenterModal v-model="accountOpen" />
  </div>
</template>
