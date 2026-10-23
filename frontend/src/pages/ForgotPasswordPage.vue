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
import { getErrorMessage } from '@/utils/errors'

const router = useRouter()

const email = ref('')
const code = ref('')
const newPassword = ref('')
const error = ref('')
const notice = ref('')
const submitting = ref(false)
const sending = ref(false)
const done = ref(false)

const { remaining, running, start } = useCountdown()

const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim()))
const canSend = computed(() => emailValid.value && !running.value && !sending.value)

async function sendCode(): Promise<void> {
  if (!canSend.value) return
  error.value = ''
  notice.value = ''
  sending.value = true
  try {
    const { data } = await authApi.sendCode(email.value.trim(), 'reset')
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
  if (newPassword.value.length < 8) {
    error.value = '密码至少 8 位'
    return
  }
  if (!/[a-zA-Z]/.test(newPassword.value) || !/\d/.test(newPassword.value)) {
    error.value = '密码必须同时包含字母和数字'
    return
  }

  submitting.value = true
  try {
    await authApi.resetPassword({
      email: email.value.trim(),
      code: code.value,
      new_password: newPassword.value,
    })
    done.value = true
  } catch (err) {
    error.value = getErrorMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <template v-if="done">
      <div class="rounded-lg border border-line bg-canvas p-6">
        <div
          class="flex size-10 items-center justify-center rounded-md bg-down-soft text-base font-semibold text-down"
        >
          ✓
        </div>
        <h2 class="mt-4 text-[20px] font-semibold text-ink">密码已重置</h2>
        <p class="mt-1.5 text-sm leading-relaxed text-ink-2">
          你的登录密码已更新，此前所有登录会话均已失效，请使用新密码重新登录。
        </p>
        <Button class="mt-6" block @click="router.replace('/login')">返回登录</Button>
      </div>
    </template>

    <template v-else>
      <div>
        <h2 class="text-[22px] font-semibold tracking-tight text-ink">重置密码</h2>
        <p class="mt-1.5 text-sm text-ink-2">通过邮箱验证码设置新密码</p>
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

        <Field label="新密码" for="new-password" hint="至少 8 位，含字母和数字">
          <Input
            id="new-password"
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            placeholder="设置新密码"
          />
        </Field>

        <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
          {{ error }}
        </p>
        <p v-if="notice" class="rounded-md bg-primary-soft px-3 py-2 text-[13px] text-primary-hover">
          {{ notice }}
        </p>

        <Button type="submit" block :loading="submitting">确认重置</Button>
      </form>

      <p class="mt-6 text-[13px] text-ink-2">
        想起来了？
        <router-link to="/login" class="font-medium text-primary underline-offset-2 hover:text-primary-hover hover:underline">
          返回登录
        </router-link>
      </p>
    </template>
  </AuthLayout>
</template>
