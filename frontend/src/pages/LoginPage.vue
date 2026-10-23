<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api/auth'
import AuthLayout from '@/components/layout/AuthLayout.vue'
import Button from '@/components/ui/Button.vue'
import Field from '@/components/ui/Field.vue'
import Input from '@/components/ui/Input.vue'
import OtpInput from '@/components/ui/OtpInput.vue'
import { useCountdown } from '@/composables/useCountdown'
import { useAuthStore } from '@/stores/auth'
import { getErrorMessage } from '@/utils/errors'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const mode = ref<'password' | 'code'>('password')
const email = ref('')
const password = ref('')
const code = ref('')
const error = ref('')
const notice = ref('')
const submitting = ref(false)
const sending = ref(false)

const { remaining, running, start } = useCountdown()

const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim()))
const canSend = computed(() => emailValid.value && !running.value && !sending.value)

async function sendCode(): Promise<void> {
  if (!canSend.value) return
  error.value = ''
  notice.value = ''
  sending.value = true
  try {
    const { data } = await authApi.sendCode(email.value.trim(), 'login')
    start(data.cooldown)
    notice.value = `验证码已发送至 ${email.value.trim()}，5 分钟内有效`
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    sending.value = false
  }
}

async function submit(): Promise<void> {
  if (submitting.value) return
  error.value = ''
  notice.value = ''

  if (!emailValid.value) {
    error.value = '请输入有效的邮箱地址'
    return
  }
  if (mode.value === 'password' && !password.value) {
    error.value = '请输入密码'
    return
  }
  if (mode.value === 'code' && code.value.length !== 6) {
    error.value = '请输入 6 位验证码'
    return
  }

  submitting.value = true
  try {
    if (mode.value === 'password') {
      await auth.loginWithPassword(email.value.trim(), password.value)
    } else {
      await auth.loginWithCode(email.value.trim(), code.value)
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    submitting.value = false
  }
}

function switchMode(next: 'password' | 'code'): void {
  mode.value = next
  error.value = ''
  notice.value = ''
}
</script>

<template>
  <AuthLayout>
    <div>
      <h2 class="text-[22px] font-semibold tracking-tight text-ink">欢迎回来</h2>
      <p class="mt-1.5 text-sm text-ink-2">登录后开始你的 AI 分析</p>
    </div>

    <div class="mt-6 grid grid-cols-2 gap-1 rounded-md bg-surface-2 p-1">
      <button
        type="button"
        class="h-8 rounded-sm text-[13px] font-medium transition-colors duration-150"
        :class="mode === 'password' ? 'bg-canvas text-ink shadow-card' : 'text-ink-2 hover:text-ink'"
        @click="switchMode('password')"
      >
        密码登录
      </button>
      <button
        type="button"
        class="h-8 rounded-sm text-[13px] font-medium transition-colors duration-150"
        :class="mode === 'code' ? 'bg-canvas text-ink shadow-card' : 'text-ink-2 hover:text-ink'"
        @click="switchMode('code')"
      >
        验证码登录
      </button>
    </div>

    <form class="mt-6 space-y-4" @submit.prevent="submit">
      <Field label="邮箱" for="email">
        <Input
          id="email"
          v-model="email"
          type="email"
          inputmode="email"
          autocomplete="email"
          placeholder="you@example.com"
        />
      </Field>

      <Field v-if="mode === 'password'" label="密码" for="password">
        <Input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
        />
      </Field>

      <Field v-else label="验证码" hint="6 位数字">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
          <OtpInput v-model="code" class="min-w-0 flex-1" />
          <Button
            variant="secondary"
            class="h-10 shrink-0 whitespace-nowrap"
            :loading="sending"
            :disabled="!canSend"
            @click="sendCode"
          >
            {{ running ? `${remaining}s` : '获取验证码' }}
          </Button>
        </div>
      </Field>

      <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
        {{ error }}
      </p>
      <p v-if="notice" class="rounded-md bg-primary-soft px-3 py-2 text-[13px] text-primary-hover">
        {{ notice }}
      </p>

      <Button type="submit" block :loading="submitting">
        {{ mode === 'password' ? '登录' : '验证并登录' }}
      </Button>
    </form>

    <div class="mt-6 flex items-center justify-between text-[13px]">
      <router-link to="/register" class="font-medium text-primary underline-offset-2 hover:text-primary-hover hover:underline">
        注册新账号
      </router-link>
      <router-link to="/forgot-password" class="text-ink-2 hover:text-ink">
        忘记密码？
      </router-link>
    </div>
  </AuthLayout>
</template>
