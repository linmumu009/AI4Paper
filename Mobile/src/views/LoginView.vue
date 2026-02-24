<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, loginBySms, sendSms } from '../stores/auth'

const router = useRouter()
const route = useRoute()

type Tab = 'password' | 'sms'
const activeTab = ref<Tab>('password')

// 用户名密码登录
const username = ref('')
const password = ref('')
const pwdLoading = ref(false)
const pwdError = ref('')

// 手机号验证码登录
const phone = ref('')
const smsCode = ref('')
const smsLoading = ref(false)
const smsSending = ref(false)
const smsError = ref('')
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

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

async function handlePasswordLogin() {
  if (!username.value || !password.value) {
    pwdError.value = '请填写用户名和密码'
    return
  }
  pwdLoading.value = true
  pwdError.value = ''
  try {
    await login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/recommend'
    router.replace(redirect)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || '登录失败'
  } finally {
    pwdLoading.value = false
  }
}

async function handleSmsLogin() {
  if (!phone.value.trim() || !smsCode.value.trim()) {
    smsError.value = '请填写手机号和验证码'
    return
  }
  smsLoading.value = true
  smsError.value = ''
  try {
    const res = await loginBySms(phone.value.trim(), smsCode.value.trim())
    if (res.is_new_user) {
      router.replace({ path: '/profile', query: { welcome: '1' } })
    } else {
      const redirect = (route.query.redirect as string) || '/recommend'
      router.replace(redirect)
    }
  } catch (e: any) {
    smsError.value = e?.response?.data?.detail || '登录失败'
  } finally {
    smsLoading.value = false
  }
}

function goBack() {
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
      <h1 class="text-2xl font-bold text-text-primary mb-1">欢迎回来</h1>
      <p class="text-sm text-text-muted mb-6">登录 ArxivPaper 账号</p>

      <!-- Tab 切换 -->
      <div class="w-full max-w-[340px] flex rounded-xl bg-bg-elevated border border-border mb-5 overflow-hidden">
        <button
          class="flex-1 py-2.5 text-sm font-medium transition-colors"
          :class="activeTab === 'password'
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'
            : 'text-text-muted'"
          @click="activeTab = 'password'"
        >
          用户名密码
        </button>
        <button
          class="flex-1 py-2.5 text-sm font-medium transition-colors"
          :class="activeTab === 'sms'
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'
            : 'text-text-muted'"
          @click="activeTab = 'sms'"
        >
          手机验证码
        </button>
      </div>

      <div class="w-full max-w-[340px]">
        <!-- 用户名密码登录 -->
        <div v-if="activeTab === 'password'" class="space-y-3.5">
          <div v-if="pwdError" class="px-4 py-2.5 rounded-xl bg-tinder-pink/10 text-tinder-pink text-sm text-center">
            {{ pwdError }}
          </div>
          <input
            v-model="username"
            type="text"
            placeholder="用户名"
            autocomplete="username"
            class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
            @keydown.enter="handlePasswordLogin"
          />
          <input
            v-model="password"
            type="password"
            placeholder="密码"
            autocomplete="current-password"
            class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
            @keydown.enter="handlePasswordLogin"
          />
          <button
            class="w-full py-3.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none disabled:opacity-50"
            :disabled="pwdLoading"
            @click="handlePasswordLogin"
          >
            {{ pwdLoading ? '登录中...' : '登录' }}
          </button>
        </div>

        <!-- 手机号验证码登录 -->
        <div v-else class="space-y-3.5">
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
            placeholder="验证码"
            class="w-full px-4 py-3.5 rounded-xl bg-bg-elevated border border-border text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink transition-colors"
            @keydown.enter="handleSmsLogin"
          />
          <button
            class="w-full py-3.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none disabled:opacity-50"
            :disabled="smsLoading"
            @click="handleSmsLogin"
          >
            {{ smsLoading ? '登录中...' : '登录' }}
          </button>
        </div>
      </div>

      <!-- Register link -->
      <p class="mt-6 text-sm text-text-muted text-center">
        手机验证码登录即自动注册 ·
        <button class="text-tinder-pink font-medium border-none bg-transparent p-0 text-sm" @click="router.push({ path: '/register', query: route.query })">
          密码注册
        </button>
      </p>
    </div>
  </div>
</template>
