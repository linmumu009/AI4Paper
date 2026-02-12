<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../stores/auth'

const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  error.value = ''
  if (password.value !== confirmPassword.value) {
    error.value = '两次密码输入不一致'
    return
  }
  loading.value = true
  try {
    await register(username.value.trim(), password.value)
    await login(username.value.trim(), password.value)
    const redirect = (route.query.redirect as string) || '/'
    await router.replace(redirect)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-[calc(100vh-56px)] flex items-center justify-center bg-bg px-4">
    <div class="w-full max-w-md bg-bg-elevated border border-border rounded-2xl p-6">
      <h1 class="text-2xl font-bold text-text-primary mb-1">注册</h1>
      <p class="text-sm text-text-muted mb-6">创建账号后可收藏论文并管理知识库</p>

      <form class="space-y-4" @submit.prevent="onSubmit">
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

        <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 rounded-lg border-none text-white font-semibold bg-gradient-to-r from-[#fd267a] to-[#ff6036] cursor-pointer disabled:opacity-60"
        >
          {{ loading ? '注册中...' : '注册并登录' }}
        </button>
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
