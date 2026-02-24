<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { register, login, sendSms } from '../stores/auth'

const router = useRouter()
const route = useRoute()

// 步骤：1=手机验证，2=设置账号
const step = ref<1 | 2>(1)

// Step 1：手机号验证
const phone = ref('')
const smsCode = ref('')
const smsSending = ref(false)
const smsError = ref('')
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// Step 2：账号密码
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')

function startCountdown() {
  countdown.value = 60
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(countdownTimer!)
      countdownTimer = null
    }
  }, 1000)
}

async function handleSendSms() {
  if (!phone.value.trim()) {
    smsError.value = '请输入手机号'
    return
  }
  smsSending.value = true
  smsError.value = ''
  try {
    await sendSms(phone.value.trim())
    startCountdown()
  } catch (e: any) {
    smsError.value = e?.response?.data?.detail || '发送失败，请稍后重试'
  } finally {
    smsSending.value = false
  }
}

function handleNextStep() {
  if (!phone.value.trim()) {
    smsError.value = '请输入手机号'
    return
  }
  if (!smsCode.value.trim()) {
    smsError.value = '请输入验证码'
    return
  }
  smsError.value = ''
  step.value = 2
}

async function handleRegister() {
  if (!username.value || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  if (password.value.length < 8) {
    error.value = '密码至少 8 个字符'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次密码输入不一致'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await register(username.value, password.value, phone.value.trim(), smsCode.value.trim())
    await login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/recommend'
    router.replace(redirect)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    if (detail.includes('手机验证失败') || detail.includes('验证码')) {
      error.value = detail + '，请返回重新验证'
    } else {
      error.value = detail || '注册失败'
    }
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (step.value === 2) {
    step.value = 1
    return
  }
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/recommend')
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Top bar -->
    <div class="shrink-0 flex items-center gap-2 px-4 pt-4 pb-2 safe-area-top">
      <button
        class="w-10 h-10 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-primary"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
    </div>

    <div class="flex-1 flex flex-col items-center justify-center px-8">
      <!-- Logo / Title -->
      <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-[#fd267a] to-[#ff6036] flex items-center justify-center text-white text-3xl font-bold mb-5">
        AP
      </div>
      <h1 class="text-2xl font-bold text-text-primary mb-1">创建账号</h1>
      <p class="text-sm text-text-muted mb-6">注册 ArxivPaper 账号</p>

      <!-- 步骤指示器 -->
      <div class="w-full max-w-[340px] flex items-center gap-2 mb-6">
        <div class="flex items-center gap-1.5">
          <div
            class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
            :class="step === 1 ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white' : 'bg-tinder-pink/20 text-tinder-pink'"
          >1</div>
          <span class="text-xs" :class="step === 1 ? 'text-text-primary font-medium' : 'text-text-muted'">手机验证</span>
        </div>
        <div class="flex-1 h-px bg-border" />
        <div class="flex items-center gap-1.5">
          <div
            class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
            :class="step === 2 ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white' : 'bg-border/60 text-text-muted'"
          >2</div>
          <span class="text-xs" :class="step === 2 ? 'text-text-primary font-medium' : 'text-text-muted'">设置账号</span>
        </div>
      </div>

      <!-- Step 1: 手机号验证 -->
      <div v-if="step === 1" class="w-full max-w-[340px] space-y-3.5">
        <div v-if="smsError" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 text-tinder-pink text-sm text-center">
          {{ smsError }}
        </div>

        <div class="flex gap-2">
          <input
            v-model="phone"
            type="tel"
            maxlength="11"
            placeholder="手机号"
            class="flex-1 px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
          />
          <button
            type="button"
            :disabled="smsSending || countdown > 0"
            class="shrink-0 px-3 py-3.5 rounded-xl bg-bg-elevated border border-border text-sm font-medium text-text-primary disabled:opacity-50 whitespace-nowrap"
            @click="handleSendSms"
          >
            {{ smsSending ? '发送中' : countdown > 0 ? `${countdown}s` : '发送验证码' }}
          </button>
        </div>

        <input
          v-model="smsCode"
          type="text"
          maxlength="8"
          placeholder="短信验证码"
          class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
          @keydown.enter="handleNextStep"
        />

        <button
          class="w-full py-3.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
          @click="handleNextStep"
        >
          下一步
        </button>
      </div>

      <!-- Step 2: 设置账号密码 -->
      <div v-else class="w-full max-w-[340px] space-y-3.5">
        <div v-if="error" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 text-tinder-pink text-sm text-center">
          {{ error }}
        </div>

        <input
          v-model="username"
          type="text"
          placeholder="用户名（至少 3 个字符）"
          autocomplete="username"
          class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
        />
        <input
          v-model="password"
          type="password"
          placeholder="密码（至少 8 个字符）"
          autocomplete="new-password"
          class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
        />
        <input
          v-model="confirmPassword"
          type="password"
          placeholder="确认密码"
          autocomplete="new-password"
          class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
          @keydown.enter="handleRegister"
        />
        <button
          class="w-full py-3.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none disabled:opacity-50"
          :disabled="loading"
          @click="handleRegister"
        >
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </div>

      <!-- Login link -->
      <p class="mt-6 text-sm text-text-muted">
        已有账号？
        <button class="text-tinder-pink font-medium border-none bg-transparent p-0 text-sm" @click="router.push({ path: '/login', query: route.query })">
          去登录
        </button>
      </p>
    </div>
  </div>
</template>
