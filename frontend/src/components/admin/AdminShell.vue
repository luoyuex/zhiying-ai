<script setup lang="ts">
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()

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
    label: '用户',
    items: [{ label: '用户与额度', to: '/admin/users' }],
  },
  {
    label: '系统',
    items: [{ label: '审计日志', to: '/admin/audit' }],
  },
]

const flatItems = navGroups.flatMap((group) => group.items)

function isActive(to: string): boolean {
  return to === '/admin' ? route.path === '/admin' : route.path.startsWith(to)
}
</script>

<template>
  <div class="min-h-screen bg-surface">
    <div class="mx-auto flex min-h-screen max-w-[1440px]">
      <aside
        class="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-canvas px-3 py-5 md:flex"
      >
        <RouterLink to="/admin" class="px-2">
          <div class="text-sm font-semibold text-ink">智赢 AI</div>
          <div class="mt-0.5 text-[11px] text-ink-3">管理后台</div>
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
          <div class="truncate px-2 text-[11px] text-ink-3">
            {{ auth.user?.email }}
          </div>
          <RouterLink
            to="/"
            class="mt-2 block rounded-md px-2.5 py-2 text-[13px] text-ink-2 transition-colors hover:bg-surface hover:text-ink"
          >
            ← 返回工作台
          </RouterLink>
        </div>
      </aside>

      <div class="min-w-0 flex-1">
        <header
          class="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur"
        >
          <div class="flex h-14 items-center gap-4 px-6">
            <RouterLink to="/admin" class="text-sm font-semibold text-ink md:hidden">
              后台管理
            </RouterLink>
            <nav
              class="flex flex-1 items-center gap-4 overflow-x-auto text-[13px] md:hidden"
            >
              <RouterLink
                v-for="item in flatItems"
                :key="item.to"
                :to="item.to"
                class="shrink-0 transition-colors"
                :class="
                  isActive(item.to)
                    ? 'font-medium text-ink'
                    : 'text-ink-3 hover:text-ink'
                "
              >
                {{ item.label }}
              </RouterLink>
            </nav>
            <div
              class="ml-auto hidden items-center gap-4 text-[11px] text-ink-3 md:flex"
            >
              <span>{{ auth.user?.nickname }}</span>
              <RouterLink to="/" class="transition-colors hover:text-ink">
                返回工作台
              </RouterLink>
            </div>
          </div>
        </header>

        <main class="mx-auto max-w-[1200px] px-6 py-6 sm:px-8 sm:py-8">
          <RouterView />
        </main>
      </div>
    </div>
  </div>
</template>
