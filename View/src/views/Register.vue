<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register, sendSms } from '../stores/auth'

// 把原始错误格式化为用户可读的文字
function formatError(e: any, fallback: string): string {
  if (e?.response?.data?.detail) return e.response.data.detail
  if (e?.response?.status) return `服务器错误 (HTTP ${e.response.status})`
  if (e?.message) return `网络错误: ${e.message}`
  return fallback
}

const router = useRouter()
const route = useRoute()

// 步骤：1=手机验证，2=设置账号
const step = ref<1 | 2>(1)

// Step 1：手机号验证
const phone = ref('')
const smsCode = ref('')
const smsSending = ref(false)
const smsError = ref('')
const smsVerified = ref(false)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// Step 2：账号密码
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const submitLoading = ref(false)
const submitError = ref('')

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
    smsError.value = formatError(e, '发送失败，请稍后重试')
  } finally {
    smsSending.value = false
  }
}

function handleVerifyAndNext() {
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
  submitError.value = ''
  if (!username.value.trim()) {
    submitError.value = '请输入用户名'
    return
  }
  if (password.value.length < 8) {
    submitError.value = '密码至少 8 位'
    return
  }
  if (password.value !== confirmPassword.value) {
    submitError.value = '两次密码输入不一致'
    return
  }
  submitLoading.value = true
  try {
    await register(username.value.trim(), password.value, phone.value.trim(), smsCode.value.trim())
    await login(username.value.trim(), password.value)
    const redirect = (route.query.redirect as string) || '/'
    await router.replace(redirect)
  } catch (e: any) {
    const detail = formatError(e, '注册失败，请稍后重试')
    if (detail.includes('手机验证失败') || detail.includes('验证码')) {
      submitError.value = detail + '，请返回重新验证'
    } else {
      submitError.value = detail
    }
  } finally {
    submitLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-[calc(100vh-56px)] flex items-center justify-center bg-bg px-4">
    <div class="w-full max-w-md bg-bg-elevated border border-border rounded-2xl p-6">
      <h1 class="text-2xl font-bold text-text-primary mb-1">注册</h1>
      <p class="text-sm text-text-muted mb-5">创建账号后可收藏论文并管理知识库</p>

      <!-- 步骤指示器 -->
      <div class="flex items-center gap-2 mb-6">
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
            :class="step === 2 ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white' : 'bg-border text-text-muted'"
          >2</div>
          <span class="text-xs" :class="step === 2 ? 'text-text-primary font-medium' : 'text-text-muted'">设置账号</span>
        </div>
      </div>

      <!-- Step 1: 手机号验证 -->
      <form v-if="step === 1" class="space-y-4" @submit.prevent="handleVerifyAndNext">
        <div>
          <label class="block text-sm text-text-secondary mb-1">手机号 <span class="text-red-400">*</span></label>
          <div class="flex gap-2">
            <input
              v-model="phone"
              type="tel"
              maxlength="11"
              required
              class="flex-1 px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
              placeholder="请输入中国大陆手机号"
            />
            <button
              type="button"
              :disabled="smsSending || countdown > 0"
              class="shrink-0 px-3 py-2 rounded-lg border border-border text-sm font-medium text-text-primary bg-bg disabled:opacity-50 hover:border-tinder-pink/60 transition-colors whitespace-nowrap"
              @click="handleSendSms"
            >
              {{ smsSending ? '发送中...' : countdown > 0 ? `${countdown}s` : '发送验证码' }}
            </button>
          </div>
        </div>
        <div>
          <label class="block text-sm text-text-secondary mb-1">短信验证码 <span class="text-red-400">*</span></label>
          <input
            v-model="smsCode"
            type="text"
            maxlength="8"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="请输入短信验证码"
          />
        </div>
        <p v-if="smsError" class="text-sm text-red-500">{{ smsError }}</p>
        <button
          type="submit"
          class="w-full py-2.5 rounded-lg border-none text-white font-semibold bg-gradient-to-r from-[#fd267a] to-[#ff6036] cursor-pointer"
        >
          下一步
        </button>
      </form>

      <!-- Step 2: 设置账号密码 -->
      <form v-else class="space-y-4" @submit.prevent="handleRegister">
        <div>
          <label class="block text-sm text-text-secondary mb-1">用户名</label>
          <input
            v-model="username"
            type="text"
            minlength="3"
            maxlength="32"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="3-32 位字母/数字/._-"
          />
        </div>
        <div>
          <label class="block text-sm text-text-secondary mb-1">密码</label>
          <input
            v-model="password"
            type="password"
            minlength="8"
            maxlength="128"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="至少 8 位"
          />
        </div>
        <div>
          <label class="block text-sm text-text-secondary mb-1">确认密码</label>
          <input
            v-model="confirmPassword"
            type="password"
            minlength="8"
            maxlength="128"
            required
            class="w-full px-3 py-2 rounded-lg border border-border bg-bg text-text-primary focus:outline-none focus:border-tinder-pink/60"
            placeholder="请再次输入密码"
          />
        </div>
        <p v-if="submitError" class="text-sm text-red-500">{{ submitError }}</p>
        <div class="flex gap-2">
          <button
            type="button"
            class="flex-1 py-2.5 rounded-lg border border-border text-text-primary font-medium bg-bg hover:bg-bg-elevated transition-colors"
            @click="step = 1"
          >
            上一步
          </button>
          <button
            type="submit"
            :disabled="submitLoading"
            class="flex-1 py-2.5 rounded-lg border-none text-white font-semibold bg-gradient-to-r from-[#fd267a] to-[#ff6036] cursor-pointer disabled:opacity-60"
          >
            {{ submitLoading ? '注册中...' : '注册并登录' }}
          </button>
        </div>
      </form>

      <p class="text-sm text-text-muted mt-5">
        已有账号？
        <router-link
          class="text-tinder-pink no-underline hover:underline"
          :to="{ path: '/login', query: { redirect: (route.query.redirect as string) || '/' } }"
        >
          去登录
        </router-link>
      </p>
    </div>
  </div>
</template>
