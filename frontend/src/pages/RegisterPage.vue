<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

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

const email = ref('')
const code = ref('')
const nickname = ref('')
const password = ref('')
const error = ref('')
const notice = ref('')
const submitting = ref(false)
const sending = ref(false)

const { remaining, running, start } = useCountdown()

const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim()))
const canSend = computed(() => emailValid.value && !running.value && !sending.value)

const strength = computed(() => {
  const value = password.value
  let score = 0
  if (value.length >= 8) score += 1
  if (value.length >= 12) score += 1
  if (/[a-zA-Z]/.test(value) && /\d/.test(value)) score += 1
  if (/[^a-zA-Z0-9]/.test(value)) score += 1
  return Math.min(score, 4)
})

const strengthLabel = computed(() => ['太弱', '偏弱', '一般', '较强', '很强'][strength.value])
const strengthColor = computed(() => {
  if (strength.value <= 1) return 'bg-danger'
  if (strength.value === 2) return 'bg-warn'
  return 'bg-down'
})

async function sendCode(): Promise<void> {
  if (!canSend.value) return
  error.value = ''
  notice.value = ''
  sending.value = true
  try {
    const { data } = await authApi.sendCode(email.value.trim(), 'register')
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
  if (code.value.length !== 6) {
    error.value = '请输入 6 位验证码'
    return
  }
  if (nickname.value.trim().length < 2) {
    error.value = '昵称至少 2 个字符'
    return
  }
  if (password.value.length < 8) {
    error.value = '密码至少 8 位'
    return
  }
  if (!/[a-zA-Z]/.test(password.value) || !/\d/.test(password.value)) {
    error.value = '密码必须同时包含字母和数字'
    return
  }

  submitting.value = true
  try {
    await auth.register({
      email: email.value.trim(),
      code: code.value,
      password: password.value,
      nickname: nickname.value.trim(),
    })
    await router.replace('/')
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <div>
      <h2 class="text-[22px] font-semibold tracking-tight text-ink">创建账号</h2>
      <p class="mt-1.5 text-sm text-ink-2">使用邮箱验证，一分钟完成注册</p>
    </div>

    <form class="mt-6 space-y-4" @submit.prevent="submit">
      <Field label="邮箱" for="email" hint="用于接收验证码">
        <Input
          id="email"
          v-model="email"
          type="email"
          inputmode="email"
          autocomplete="email"
          placeholder="you@example.com"
        />
      </Field>

      <Field label="验证码" hint="6 位数字">
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

      <Field label="昵称" for="nickname" hint="2-20 个字符">
        <Input
          id="nickname"
          v-model="nickname"
          autocomplete="nickname"
          placeholder="怎么称呼你"
        />
      </Field>

      <Field label="密码" for="password" hint="至少 8 位，含字母和数字">
        <Input
          id="password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          placeholder="设置登录密码"
        />
        <div v-if="password" class="mt-2 flex items-center gap-2">
          <div class="flex flex-1 gap-1">
            <span
              v-for="index in 4"
              :key="index"
              class="h-1 flex-1 rounded-full transition-colors duration-150"
              :class="index <= strength ? strengthColor : 'bg-surface-2'"
            />
          </div>
          <span class="w-8 text-right text-[11px] text-ink-3">{{ strengthLabel }}</span>
        </div>
      </Field>

      <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
        {{ error }}
      </p>
      <p v-if="notice" class="rounded-md bg-primary-soft px-3 py-2 text-[13px] text-primary-hover">
        {{ notice }}
      </p>

      <Button type="submit" block :loading="submitting">注册并登录</Button>
    </form>

    <p class="mt-6 text-[13px] text-ink-2">
      已有账号？
      <router-link to="/login" class="font-medium text-primary hover:text-primary-hover">
        直接登录
      </router-link>
    </p>
  </AuthLayout>
</template>
