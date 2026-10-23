<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { aiApi, type AIConfig } from '@/api/ai'
import { authApi } from '@/api/auth'
import { reportsApi } from '@/api/reports'
import { watchlistApi } from '@/api/watchlist'
import AutomationSettingsView from '@/components/account/AutomationSettingsView.vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import { useAuthStore } from '@/stores/auth'
import type { User } from '@/types/auth'
import { getErrorMessage } from '@/utils/errors'

const open = defineModel<boolean>({ required: true })

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

type AccountView = 'overview' | 'profile' | 'security' | 'automation'

const profile = ref<User | null>(auth.user)
const aiConfig = ref<AIConfig | null>(null)
const reportCount = ref<number | null>(null)
const reportCapped = ref(false)
const watchlistCount = ref<number | null>(null)
const loading = ref(false)
const closeButtonRef = ref<HTMLButtonElement | null>(null)

const activeView = ref<AccountView>('overview')
const nicknameDraft = ref(auth.user?.nickname ?? '')
const profileSaving = ref(false)
const profileError = ref('')
const profileSuccess = ref('')

const passwordCurrent = ref('')
const passwordNew = ref('')
const passwordConfirm = ref('')
const passwordSaving = ref(false)
const passwordError = ref('')
const passwordSuccess = ref('')

const PASSWORD_RULE = '密码至少 8 位，且必须同时包含字母和数字'

let logoutTimer: ReturnType<typeof setTimeout> | null = null

const avatarText = computed(
  () => profile.value?.nickname?.trim().slice(0, 1) || '智',
)

const roleLabel = computed(() =>
  profile.value?.role === 'admin' ? '管理员' : '普通用户',
)

const statusLabel = computed(() =>
  profile.value?.status === 'active' ? '正常' : '受限',
)

const quotaPercent = computed(() => {
  if (!aiConfig.value || aiConfig.value.daily_quota <= 0) return 0
  return Math.min(
    100,
    Math.round((aiConfig.value.quota_used / aiConfig.value.daily_quota) * 100),
  )
})

const reportLabel = computed(() => {
  if (reportCount.value === null) return '—'
  return reportCapped.value ? '50+' : String(reportCount.value)
})

const viewMeta = computed(() => {
  if (activeView.value === 'profile') {
    return {
      eyebrow: 'PROFILE SETTINGS',
      title: '资料设置',
      desc: '修改昵称与账号资料',
    }
  }
  if (activeView.value === 'security') {
    return {
      eyebrow: 'ACCOUNT SECURITY',
      title: '修改密码',
      desc: '修改后需要重新登录',
    }
  }
  if (activeView.value === 'automation') {
    return {
      eyebrow: 'AUTOMATION',
      title: '定时任务',
      desc: '每日自动选股与自动分析自选股',
    }
  }
  return {
    eyebrow: 'ACCOUNT OVERVIEW',
    title: '个人概览',
    desc: '账号、额度与使用情况',
  }
})

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function close(): void {
  open.value = false
}

async function loadProfile(): Promise<void> {
  try {
    const { data } = await authApi.me()
    profile.value = data
  } catch {
    // 保留本地会话中的用户信息
  }
}

async function loadStats(): Promise<void> {
  const [aiResult, reportsResult, watchlistResult] = await Promise.allSettled([
    aiApi.config(),
    reportsApi.list(undefined, 50),
    watchlistApi.list(),
  ])
  if (aiResult.status === 'fulfilled') aiConfig.value = aiResult.value.data
  if (reportsResult.status === 'fulfilled') {
    reportCount.value = reportsResult.value.data.length
    reportCapped.value = reportsResult.value.data.length >= 50
  }
  if (watchlistResult.status === 'fulfilled') {
    watchlistCount.value = watchlistResult.value.data.length
  }
}

async function loadAll(): Promise<void> {
  loading.value = true
  await loadProfile()
  await loadStats()
  loading.value = false
}

function setView(view: AccountView): void {
  activeView.value = view
  profileError.value = ''
  profileSuccess.value = ''
  passwordError.value = ''
  passwordSuccess.value = ''
  if (view === 'profile') {
    nicknameDraft.value = profile.value?.nickname ?? ''
  }
}

async function saveProfile(): Promise<void> {
  const nickname = nicknameDraft.value.trim()
  if (nickname.length < 2 || nickname.length > 20) {
    profileError.value = '昵称需为 2–20 个字符'
    return
  }
  profileSaving.value = true
  profileError.value = ''
  profileSuccess.value = ''
  try {
    const { data } = await authApi.updateProfile({ nickname })
    profile.value = data
    auth.setUser(data)
    nicknameDraft.value = data.nickname
    profileSuccess.value = '资料已保存'
  } catch (err) {
    profileError.value = getErrorMessage(err, '资料保存失败，请稍后重试')
  } finally {
    profileSaving.value = false
  }
}

async function changePassword(): Promise<void> {
  if (!passwordCurrent.value) {
    passwordError.value = '请输入当前密码'
    return
  }
  if (
    passwordNew.value.length < 8 ||
    !/[A-Za-z]/.test(passwordNew.value) ||
    !/\d/.test(passwordNew.value)
  ) {
    passwordError.value = PASSWORD_RULE
    return
  }
  if (passwordNew.value === passwordCurrent.value) {
    passwordError.value = '新密码不能与当前密码相同'
    return
  }
  if (passwordNew.value !== passwordConfirm.value) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  passwordSaving.value = true
  passwordError.value = ''
  passwordSuccess.value = ''
  try {
    const { data } = await authApi.changePassword({
      current_password: passwordCurrent.value,
      new_password: passwordNew.value,
    })
    passwordSuccess.value = data.message || '密码已修改，请重新登录'
    passwordCurrent.value = ''
    passwordNew.value = ''
    passwordConfirm.value = ''
    if (logoutTimer) clearTimeout(logoutTimer)
    logoutTimer = setTimeout(() => {
      void (async () => {
        await auth.logout()
        close()
        await router.replace('/login')
      })()
    }, 1500)
  } catch (err) {
    passwordError.value = getErrorMessage(err, '密码修改失败，请稍后重试')
  } finally {
    passwordSaving.value = false
  }
}

async function handleLogout(): Promise<void> {
  if (logoutTimer) {
    clearTimeout(logoutTimer)
    logoutTimer = null
  }
  close()
  await auth.logout()
  await router.replace('/login')
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) close()
}

function go(path: string): void {
  close()
  void router.push(path)
}

watch(profile, (value) => {
  if (value) nicknameDraft.value = value.nickname
})

watch(open, async (value) => {
  document.body.style.overflow = value ? 'hidden' : ''
  if (value) {
    activeView.value = 'overview'
    profileError.value = ''
    profileSuccess.value = ''
    passwordError.value = ''
    passwordSuccess.value = ''
    nicknameDraft.value = profile.value?.nickname || auth.user?.nickname || ''
    await nextTick()
    closeButtonRef.value?.focus()
    void loadAll()
  }
})

watch(
  () => route.fullPath,
  () => {
    if (open.value) close()
  },
)

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
        aria-label="个人中心"
        class="relative flex h-[min(760px,90vh)] w-full max-w-4xl overflow-hidden rounded-xl bg-canvas shadow-pop"
      >
        <aside class="hidden w-56 shrink-0 flex-col bg-surface p-5 sm:flex">
          <div class="text-sm font-semibold text-ink">个人中心</div>
          <div class="mt-7 text-[10px] font-medium tracking-wide text-ink-3">账户</div>
          <button
            type="button"
            class="mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] transition-colors"
            :class="
              activeView === 'overview'
                ? 'bg-canvas font-medium text-ink'
                : 'text-ink-2 hover:bg-canvas/70 hover:text-ink'
            "
            @click="setView('overview')"
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
            个人概览
          </button>
          <button
            type="button"
            class="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] transition-colors"
            :class="
              activeView === 'profile'
                ? 'bg-canvas font-medium text-ink'
                : 'text-ink-2 hover:bg-canvas/70 hover:text-ink'
            "
            @click="setView('profile')"
          >
            <svg
              class="size-4 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              aria-hidden="true"
            >
              <path d="M4 7h9M18 7h2M4 17h2M11 17h9" stroke-linecap="round" />
              <circle cx="15.5" cy="7" r="2" />
              <circle cx="7.5" cy="17" r="2" />
            </svg>
            资料设置
          </button>
          <button
            type="button"
            class="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] transition-colors"
            :class="
              activeView === 'automation'
                ? 'bg-canvas font-medium text-ink'
                : 'text-ink-2 hover:bg-canvas/70 hover:text-ink'
            "
            @click="setView('automation')"
          >
            <svg
              class="size-4 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="8.5" />
              <path d="M12 7.5V12l3 2" stroke-linecap="round" />
            </svg>
            定时任务
          </button>
          <div class="mt-6 text-[10px] font-medium tracking-wide text-ink-3">安全</div>
          <button
            type="button"
            class="mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] transition-colors"
            :class="
              activeView === 'security'
                ? 'bg-canvas font-medium text-ink'
                : 'text-ink-2 hover:bg-canvas/70 hover:text-ink'
            "
            @click="setView('security')"
          >
            <svg
              class="size-4 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.7"
              aria-hidden="true"
            >
              <rect x="5" y="10" width="14" height="10" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke-linecap="round" />
            </svg>
            修改密码
          </button>
          <button
            type="button"
            class="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] text-ink-2 transition-colors hover:bg-canvas/70 hover:text-ink"
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
          <div class="mt-auto text-[10px] text-ink-3">智盈 AI</div>
        </aside>

        <div class="flex min-w-0 flex-1 flex-col">
          <header class="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
            <div>
              <p class="text-[10px] tracking-[0.14em] text-ink-3">
                {{ viewMeta.eyebrow }}
              </p>
              <h2 class="mt-1 text-xl font-semibold tracking-tight text-ink">
                {{ viewMeta.title }}
              </h2>
              <p class="mt-1 text-[11px] text-ink-3">{{ viewMeta.desc }}</p>
            </div>
            <button
              ref="closeButtonRef"
              type="button"
              class="flex size-8 shrink-0 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
              aria-label="关闭个人中心"
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

          <div class="flex gap-1 border-b border-line px-6 py-2 sm:hidden">
            <button
              type="button"
              class="rounded-md px-2.5 py-1.5 text-xs transition-colors"
              :class="
                activeView === 'overview'
                  ? 'bg-surface-2 font-medium text-ink'
                  : 'text-ink-3 hover:text-ink'
              "
              @click="setView('overview')"
            >
              概览
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1.5 text-xs transition-colors"
              :class="
                activeView === 'profile'
                  ? 'bg-surface-2 font-medium text-ink'
                  : 'text-ink-3 hover:text-ink'
              "
              @click="setView('profile')"
            >
              资料设置
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1.5 text-xs transition-colors"
              :class="
                activeView === 'automation'
                  ? 'bg-surface-2 font-medium text-ink'
                  : 'text-ink-3 hover:text-ink'
              "
              @click="setView('automation')"
            >
              定时任务
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1.5 text-xs transition-colors"
              :class="
                activeView === 'security'
                  ? 'bg-surface-2 font-medium text-ink'
                  : 'text-ink-3 hover:text-ink'
              "
              @click="setView('security')"
            >
              修改密码
            </button>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto px-6 py-6">
            <div class="flex items-center gap-4">
              <span
                class="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xl font-semibold text-primary"
              >
                {{ avatarText }}
              </span>
              <div class="min-w-0">
                <div class="truncate text-[18px] font-semibold text-ink">
                  {{ profile?.nickname || '未登录用户' }}
                </div>
                <div class="mt-1 truncate text-xs text-ink-3">
                  {{ profile?.email || '—' }}
                </div>
                <div class="mt-1 text-[11px] text-ink-3">
                  {{ roleLabel }} · {{ statusLabel }} · 加入于
                  {{ formatDate(profile?.created_at) }}
                </div>
              </div>
            </div>

            <template v-if="activeView === 'overview'">
              <dl
                class="mt-7 grid grid-cols-2 gap-5 border-t border-line pt-5 text-xs sm:grid-cols-3"
              >
              <div>
                <dt class="text-[11px] text-ink-3">邮箱验证</dt>
                <dd class="mt-1 text-[13px] text-ink">
                  {{ profile?.email_verified_at ? '已验证' : '未验证' }}
                </dd>
              </div>
              <div>
                <dt class="text-[11px] text-ink-3">账号角色</dt>
                <dd class="mt-1 text-[13px] text-ink">{{ roleLabel }}</dd>
              </div>
              <div>
                <dt class="text-[11px] text-ink-3">账号状态</dt>
                <dd class="mt-1 text-[13px] text-ink">{{ statusLabel }}</dd>
              </div>
            </dl>

            <div class="mt-6 rounded-lg bg-surface p-5">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div class="text-[11px] text-ink-3">今日分析额度</div>
                  <div class="mt-2 flex items-baseline gap-1.5">
                    <span class="text-[30px] font-semibold leading-none tabular-nums text-ink">
                      {{ aiConfig?.quota_used ?? '—' }}
                    </span>
                    <span class="text-sm text-ink-3">/ {{ aiConfig?.daily_quota ?? '—' }}</span>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-6 text-right">
                  <div>
                    <div class="text-[11px] text-ink-3">近期报告</div>
                    <div class="mt-1 text-lg font-semibold tabular-nums text-ink">
                      {{ reportLabel }}
                    </div>
                  </div>
                  <div>
                    <div class="text-[11px] text-ink-3">自选股</div>
                    <div class="mt-1 text-lg font-semibold tabular-nums text-ink">
                      {{ watchlistCount ?? '—' }}
                    </div>
                  </div>
                </div>
              </div>
              <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div
                  class="h-full rounded-full bg-primary transition-[width] duration-300"
                  :style="{ width: `${quotaPercent}%` }"
                />
              </div>
              <p class="mt-2 text-[11px] text-ink-3">
                <template v-if="aiConfig">
                  剩余
                  {{ Math.max(0, aiConfig.daily_quota - aiConfig.quota_used) }}
                  次 · 每日 0 点重置
                </template>
                <template v-else>{{ loading ? '正在读取额度…' : '额度信息暂不可用' }}</template>
              </p>
            </div>

            <div class="mt-6">
              <h3 class="text-[13px] font-semibold text-ink">快捷入口</h3>
              <div class="mt-2 overflow-hidden rounded-lg bg-canvas">
                <button
                  type="button"
                  class="flex w-full items-center gap-4 border-b border-line px-4 py-3.5 text-left transition-colors hover:bg-surface"
                  @click="go('/screener')"
                >
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-ink">AI 选股</div>
                    <div class="mt-0.5 text-[11px] text-ink-3">
                      五条策略，查看最新结果与历史记录
                    </div>
                  </div>
                  <span class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
                </button>
                <button
                  type="button"
                  class="flex w-full items-center gap-4 border-b border-line px-4 py-3.5 text-left transition-colors hover:bg-surface"
                  @click="go('/watchlist')"
                >
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-ink">自选股</div>
                    <div class="mt-0.5 text-[11px] text-ink-3">
                      管理持仓与查看最新 AI 诊断
                    </div>
                  </div>
                  <span class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
                </button>
                <button
                  type="button"
                  class="flex w-full items-center gap-4 px-4 py-3.5 text-left transition-colors hover:bg-surface"
                  @click="go('/reports')"
                >
                  <div class="min-w-0 flex-1">
                    <div class="text-[13px] font-medium text-ink">历史报告</div>
                    <div class="mt-0.5 text-[11px] text-ink-3">
                      查看全部个股 AI 分析记录
                    </div>
                  </div>
                  <span class="shrink-0 text-sm text-ink-3" aria-hidden="true">→</span>
                </button>
              </div>
            </div>
            </template>

            <form
              v-else-if="activeView === 'profile'"
              class="mt-7 max-w-md space-y-5"
              @submit.prevent="saveProfile"
            >
              <div class="space-y-1.5">
                <label class="text-[13px] font-medium text-ink">昵称</label>
                <Input
                  v-model="nicknameDraft"
                  :invalid="!!profileError"
                  maxlength="20"
                  placeholder="2–20 个字符"
                />
                <p class="text-[11px] text-ink-3">2–20 个字符</p>
              </div>
              <div class="space-y-1.5">
                <label class="text-[13px] font-medium text-ink">邮箱</label>
                <Input :model-value="profile?.email || ''" disabled />
                <p class="text-[11px] text-ink-3">邮箱作为登录账号，暂不支持修改</p>
              </div>
              <p v-if="profileError" class="text-xs text-danger">{{ profileError }}</p>
              <p v-if="profileSuccess" class="text-xs text-down">{{ profileSuccess }}</p>
              <Button type="submit" size="sm" :loading="profileSaving">保存资料</Button>
            </form>

            <AutomationSettingsView v-else-if="activeView === 'automation'" />

            <form
              v-else
              class="mt-7 max-w-md space-y-4"
              @submit.prevent="changePassword"
            >
              <div class="space-y-1.5">
                <label class="text-[13px] font-medium text-ink">当前密码</label>
                <Input
                  v-model="passwordCurrent"
                  type="password"
                  autocomplete="current-password"
                  :disabled="!!passwordSuccess"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-[13px] font-medium text-ink">新密码</label>
                <Input
                  v-model="passwordNew"
                  type="password"
                  autocomplete="new-password"
                  :disabled="!!passwordSuccess"
                />
                <p class="text-[11px] text-ink-3">
                  密码至少 8 位，且必须同时包含字母和数字
                </p>
              </div>
              <div class="space-y-1.5">
                <label class="text-[13px] font-medium text-ink">确认新密码</label>
                <Input
                  v-model="passwordConfirm"
                  type="password"
                  autocomplete="new-password"
                  :disabled="!!passwordSuccess"
                />
              </div>
              <p v-if="passwordError" class="text-xs text-danger">{{ passwordError }}</p>
              <p v-if="passwordSuccess" class="text-xs text-down">{{ passwordSuccess }}</p>
              <Button
                type="submit"
                size="sm"
                :loading="passwordSaving"
                :disabled="!!passwordSuccess"
              >
                修改密码
              </Button>
            </form>

            <button
              type="button"
              class="mt-5 flex w-full items-center justify-center gap-2 rounded-md border border-line-strong px-3 py-2.5 text-xs text-ink-2 transition-colors hover:bg-surface hover:text-ink sm:hidden"
              @click="handleLogout"
            >
              退出登录
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
