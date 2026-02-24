<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { isAuthenticated, currentUser, currentTier, isAdmin, logout, saveProfile, setPassword, changePassword } from '../stores/auth'
import { isDark, toggleTheme } from '../stores/theme'
import { checkUsername } from '../api'


defineOptions({ name: 'ProfileView' })

const router = useRouter()
const route = useRoute()

const tierLabel = computed(() => {
  const t = currentTier.value
  if (t === 'pro_plus') return 'Pro+'
  if (t === 'pro') return 'Pro'
  return 'Free'
})

const tierColor = computed(() => {
  const t = currentTier.value
  if (t === 'pro_plus') return 'text-tinder-gold'
  if (t === 'pro') return 'text-tinder-purple'
  return 'text-text-muted'
})

const initials = computed(() => {
  const name = currentUser.value?.nickname || currentUser.value?.username || '?'
  return name.slice(0, 2).toUpperCase()
})

async function handleLogout() {
  await logout()
  router.push('/recommend')
}

// ---------------------------------------------------------------------------
// Profile edit state
// ---------------------------------------------------------------------------

const showWelcomeBanner = ref(false)
const showProfileEdit = ref(false)

const profileNickname = ref('')
const profileUsername = ref('')
const profileSaving = ref(false)
const profileSaveSuccess = ref(false)
const profileSaveError = ref('')

const pwdOld = ref('')
const pwdNew = ref('')
const pwdConfirm = ref('')
const pwdSaving = ref(false)
const pwdSuccess = ref(false)
const pwdError = ref('')

// ---------------------------------------------------------------------------
// 实时校验：用户名可用性
// ---------------------------------------------------------------------------
type CheckStatus = 'idle' | 'checking' | 'ok' | 'error'
const usernameCheckStatus = ref<CheckStatus>('idle')
const usernameCheckMsg = ref('')

let _usernameDebounceTimer: ReturnType<typeof setTimeout> | null = null

watch(profileUsername, (val) => {
  if (_usernameDebounceTimer) clearTimeout(_usernameDebounceTimer)
  const trimmed = val.trim()
  if (trimmed === (currentUser.value?.username || '')) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length === 0) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length < 3) {
    usernameCheckStatus.value = 'error'
    usernameCheckMsg.value = '至少 3 位'
    return
  }
  usernameCheckStatus.value = 'checking'
  usernameCheckMsg.value = ''
  _usernameDebounceTimer = setTimeout(async () => {
    try {
      const res = await checkUsername(trimmed, currentUser.value?.id)
      if (profileUsername.value.trim() !== trimmed) return
      usernameCheckStatus.value = res.available ? 'ok' : 'error'
      usernameCheckMsg.value = res.available ? '' : res.message
    } catch {
      usernameCheckStatus.value = 'idle'
    }
  }, 300)
})

// ---------------------------------------------------------------------------
// 实时校验：密码
// ---------------------------------------------------------------------------
const pwdNewStatus = computed<CheckStatus>(() => {
  if (!pwdNew.value) return 'idle'
  return pwdNew.value.length >= 8 ? 'ok' : 'error'
})
const pwdNewMsg = computed(() => pwdNew.value && pwdNew.value.length < 8 ? '至少 8 位' : '')

const pwdConfirmStatus = computed<CheckStatus>(() => {
  if (!pwdConfirm.value) return 'idle'
  return pwdConfirm.value === pwdNew.value ? 'ok' : 'error'
})
const pwdConfirmMsg = computed(() => pwdConfirm.value && pwdConfirm.value !== pwdNew.value ? '两次密码不一致' : '')

function openProfileEdit() {
  profileNickname.value = currentUser.value?.nickname || ''
  profileUsername.value = currentUser.value?.username || ''
  profileSaveError.value = ''
  profileSaveSuccess.value = false
  pwdOld.value = ''
  pwdNew.value = ''
  pwdConfirm.value = ''
  pwdError.value = ''
  pwdSuccess.value = false
  usernameCheckStatus.value = 'idle'
  usernameCheckMsg.value = ''
  showProfileEdit.value = true
}

async function handleSaveProfile() {
  profileSaving.value = true
  profileSaveError.value = ''
  profileSaveSuccess.value = false
  try {
    await saveProfile({
      nickname: profileNickname.value.trim() || undefined,
      username: profileUsername.value.trim() || undefined,
    })
    profileSaveSuccess.value = true
    setTimeout(() => { profileSaveSuccess.value = false }, 2000)
  } catch (e: any) {
    profileSaveError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally {
    profileSaving.value = false
  }
}

async function handleSetPassword() {
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次密码不一致'; return }
  pwdSaving.value = true; pwdError.value = ''; pwdSuccess.value = false
  try {
    await setPassword(pwdNew.value)
    pwdNew.value = ''; pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2000)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '设置失败'
  } finally {
    pwdSaving.value = false
  }
}

async function handleChangePassword() {
  if (!pwdOld.value) { pwdError.value = '请输入旧密码'; return }
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '新密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次密码不一致'; return }
  pwdSaving.value = true; pwdError.value = ''; pwdSuccess.value = false
  try {
    await changePassword(pwdOld.value, pwdNew.value)
    pwdOld.value = ''; pwdNew.value = ''; pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2000)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '修改失败'
  } finally {
    pwdSaving.value = false
  }
}

onMounted(() => {
  if (route.query.welcome === '1') {
    showWelcomeBanner.value = true
    showProfileEdit.value = true
  }
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="shrink-0 safe-area-top">
      <div class="px-5 pt-4 pb-2">
        <h1 class="text-xl font-bold gradient-text">我的</h1>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto">
      <!-- Logged-in state -->
      <template v-if="isAuthenticated && currentUser">

        <!-- Welcome banner -->
        <Transition enter-active-class="transition duration-300 ease-out" enter-from-class="opacity-0 -translate-y-2" enter-to-class="opacity-100 translate-y-0">
          <div v-if="showWelcomeBanner" class="mx-4 mt-3 rounded-2xl bg-gradient-to-r from-[#fd267a]/10 to-[#ff6036]/10 border border-[#fd267a]/20 px-4 py-3 flex items-start gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#fd267a] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <div class="flex-1 min-w-0">
              <p class="text-sm font-semibold text-text-primary">欢迎加入！</p>
              <p class="text-xs text-text-muted mt-0.5">建议设置昵称和密码，方便后续使用。</p>
            </div>
            <button class="text-text-muted p-0.5" @click="showWelcomeBanner = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </Transition>

        <!-- User card -->
        <div class="mx-4 mt-3 p-5 rounded-2xl bg-bg-card border border-border">
          <div class="flex items-center gap-4">
            <!-- Avatar -->
            <div class="w-16 h-16 rounded-full bg-gradient-to-br from-[#fd267a] to-[#ff6036] flex items-center justify-center text-white text-xl font-bold">
              {{ initials }}
            </div>
            <div class="flex-1 min-w-0">
              <h2 class="text-lg font-bold text-text-primary truncate">{{ currentUser.nickname || currentUser.username }}</h2>
              <p v-if="currentUser.nickname" class="text-xs text-text-muted truncate">@{{ currentUser.username }}</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-sm font-semibold px-2.5 py-0.5 rounded-full bg-bg-elevated" :class="tierColor">
                  {{ tierLabel }}
                </span>
                <span class="text-xs text-text-muted">
                  {{ currentUser.role === 'superadmin' ? '超级管理员' : currentUser.role === 'admin' ? '管理员' : '用户' }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Profile edit panel (inline) -->
        <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 translate-y-2" enter-to-class="opacity-100 translate-y-0" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 translate-y-2">
          <div v-if="showProfileEdit" class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
            <div class="flex items-center justify-between px-4 py-3 border-b border-border bg-bg-elevated/50">
              <span class="text-sm font-semibold text-text-primary">资料设置</span>
              <button class="text-text-muted p-1 rounded-lg active:bg-bg-hover" @click="showProfileEdit = false">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>

            <div class="p-4 space-y-3">
              <!-- Nickname -->
              <div>
                <label class="block text-xs text-text-secondary mb-1">昵称</label>
                <input v-model="profileNickname" type="text" maxlength="64" placeholder="设置昵称" class="w-full px-3 py-2.5 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
              </div>
              <!-- Username -->
              <div>
                <label class="block text-xs text-text-secondary mb-1">
                  用户名
                  <span v-if="currentUser.is_phone_auto_created" class="text-tinder-pink ml-1 text-[10px]">建议修改</span>
                </label>
                <div class="relative">
                  <input
                    v-model="profileUsername"
                    type="text"
                    minlength="3"
                    maxlength="32"
                    placeholder="3-32 位字母/数字"
                    class="w-full px-3 py-2.5 pr-9 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors"
                    :class="usernameCheckStatus === 'error' ? 'border-red-400/60' : usernameCheckStatus === 'ok' ? 'border-green-400/60' : ''"
                  />
                  <span v-if="usernameCheckStatus === 'checking'" class="absolute right-3 top-1/2 -translate-y-1/2">
                    <svg class="w-4 h-4 text-text-muted animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
                    </svg>
                  </span>
                  <span v-else-if="usernameCheckStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                    <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  </span>
                  <span v-else-if="usernameCheckStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                    <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </span>
                </div>
                <p v-if="usernameCheckStatus === 'error' && usernameCheckMsg" class="text-[11px] text-red-400 mt-1">{{ usernameCheckMsg }}</p>
              </div>
              <!-- Phone -->
              <div>
                <label class="block text-xs text-text-secondary mb-1">绑定手机号</label>
                <div class="flex items-center gap-2 px-3 py-2.5 rounded-xl bg-bg border border-border text-sm text-text-muted">
                  {{ currentUser.phone || '未绑定' }}
                  <span v-if="currentUser.phone_verified" class="ml-auto text-[10px] text-green-500">已验证</span>
                </div>
              </div>

              <!-- Save profile -->
              <div class="flex items-center gap-2 pt-1">
                <button class="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none disabled:opacity-50" :disabled="profileSaving" @click="handleSaveProfile">
                  {{ profileSaving ? '保存中...' : '保存资料' }}
                </button>
                <span v-if="profileSaveSuccess" class="text-xs text-green-500">已保存</span>
                <span v-else-if="profileSaveError" class="text-xs text-tinder-pink">{{ profileSaveError }}</span>
              </div>

              <!-- Divider -->
              <div class="border-t border-border pt-3 mt-1">
                <p class="text-xs font-semibold text-text-secondary mb-3">{{ currentUser.has_password ? '修改密码' : '设置密码' }}</p>

                <div class="space-y-2.5">
                  <input v-if="currentUser.has_password" v-model="pwdOld" type="password" maxlength="128" placeholder="旧密码" class="w-full px-3 py-2.5 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors" />
                  <div class="relative">
                    <input
                      v-model="pwdNew"
                      type="password"
                      maxlength="128"
                      :placeholder="currentUser.has_password ? '新密码（至少 8 位）' : '密码（至少 8 位）'"
                      class="w-full px-3 py-2.5 pr-9 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors"
                      :class="pwdNewStatus === 'error' ? 'border-red-400/60' : pwdNewStatus === 'ok' ? 'border-green-400/60' : ''"
                    />
                    <span v-if="pwdNewStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                      <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    </span>
                    <span v-else-if="pwdNewStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                      <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </span>
                  </div>
                  <p v-if="pwdNewMsg" class="text-[11px] text-red-400 -mt-0.5">{{ pwdNewMsg }}</p>
                  <div class="relative">
                    <input
                      v-model="pwdConfirm"
                      type="password"
                      maxlength="128"
                      placeholder="确认密码"
                      class="w-full px-3 py-2.5 pr-9 rounded-xl bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-tinder-pink transition-colors"
                      :class="pwdConfirmStatus === 'error' ? 'border-red-400/60' : pwdConfirmStatus === 'ok' ? 'border-green-400/60' : ''"
                    />
                    <span v-if="pwdConfirmStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                      <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    </span>
                    <span v-else-if="pwdConfirmStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                      <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </span>
                  </div>
                  <p v-if="pwdConfirmMsg" class="text-[11px] text-red-400 -mt-0.5">{{ pwdConfirmMsg }}</p>
                  <div class="flex items-center gap-2">
                    <button class="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none disabled:opacity-50" :disabled="pwdSaving" @click="currentUser.has_password ? handleChangePassword() : handleSetPassword()">
                      {{ pwdSaving ? '保存中...' : (currentUser.has_password ? '修改密码' : '设置密码') }}
                    </button>
                    <span v-if="pwdSuccess" class="text-xs text-green-500">已{{ currentUser.has_password ? '修改' : '设置' }}</span>
                    <span v-else-if="pwdError" class="text-xs text-tinder-pink">{{ pwdError }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Transition>

        <!-- Feature settings list -->
        <div class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <!-- Profile edit entry -->
          <button class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors" @click="openProfileEdit">
            <div class="w-10 h-10 rounded-full bg-[#fd267a]/10 flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-[#fd267a]">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">资料设置</span>
            <span v-if="currentUser.is_phone_auto_created" class="text-xs text-[#fd267a] mr-1">建议完善</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>

          <div class="h-px bg-border mx-4"></div>
          <!-- Workbench -->
          <button
            class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
            @click="router.push('/workbench')"
          >
            <div class="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-[#8b5cf6]">
                <path d="M9 3h6"/><path d="M10 3v5l-3.5 6A2 2 0 0 0 8 17h8a2 2 0 0 0 1.5-3L14 8V3"/>
                <line x1="8.5" y1="13" x2="15.5" y2="13"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">灵感工作台</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>

          <div class="h-px bg-border mx-4"></div>

          <!-- Idea Generate Settings -->
          <button
            class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
            @click="router.push('/settings/idea-generate')"
          >
            <div class="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-[#f97316]">
                <path d="M9 18h6"/><path d="M10 22h4"/>
                <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">灵感生成配置</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>

          <div class="h-px bg-border mx-4"></div>
        </div>

        <!-- Admin settings (only visible to admin/superadmin) -->
        <template v-if="isAdmin">
          <div class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
            <!-- Section header -->
            <div class="px-4 py-2.5 border-b border-border bg-bg-elevated/60 flex items-center gap-2">
              <span class="text-xs font-semibold text-text-muted uppercase tracking-wider">⚙ 系统配置（管理员）</span>
            </div>

            <!-- Paper recommend config -->
            <button
              class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
              @click="router.push('/admin/recommend-config')"
            >
              <div class="w-10 h-10 rounded-full bg-blue-500/15 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-blue-400">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
              </div>
              <div class="flex-1 min-w-0">
                <span class="block text-base text-text-primary">论文推荐配置</span>
                <span class="text-xs text-text-muted">模型与提示词系统配置</span>
              </div>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>

            <div class="h-px bg-border mx-4"></div>

            <!-- Idea system config -->
            <button
              class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
              @click="router.push('/admin/idea-system-config')"
            >
              <div class="w-10 h-10 rounded-full bg-orange-500/15 flex items-center justify-center">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-orange-400">
                  <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
                  <path d="M15.54 8.46a5 5 0 0 1 0 7.07M8.46 8.46a5 5 0 0 0 0 7.07"/>
                </svg>
              </div>
              <div class="flex-1 min-w-0">
                <span class="block text-base text-text-primary">灵感生成系统配置</span>
                <span class="text-xs text-text-muted">各阶段模型与提示词系统级配置</span>
              </div>
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted shrink-0">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>
        </template>

        <!-- Settings list -->
        <div class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <!-- Theme toggle -->
          <button
            class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
            @click="toggleTheme"
          >
            <div class="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-gold">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-gold">
                <circle cx="12" cy="12" r="5"/>
                <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">外观模式</span>
            <span class="text-sm text-text-muted">{{ isDark ? '深色' : '浅色' }}</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-muted">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </button>

          <div class="h-px bg-border mx-4"></div>

          <!-- About -->
          <div class="w-full flex items-center gap-3 px-4 py-4">
            <div class="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-blue">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">关于</span>
            <span class="text-sm text-text-muted">ArxivPaper4 Mobile</span>
          </div>
        </div>

        <!-- Logout -->
        <div class="mx-4 mt-4 mb-8">
          <button
            class="w-full py-3.5 rounded-2xl bg-bg-card border border-border text-tinder-pink text-base font-semibold active:bg-bg-hover transition-colors"
            @click="handleLogout"
          >
            退出登录
          </button>
        </div>
      </template>

      <!-- Not logged in -->
      <template v-else>
        <div class="flex flex-col items-center justify-center py-16 px-8 text-center">
          <div class="w-24 h-24 rounded-full bg-gradient-to-br from-[#fd267a] to-[#ff6036] flex items-center justify-center text-white mb-5">
            <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
          </div>
          <h2 class="text-xl font-bold text-text-primary mb-2">登录以解锁更多功能</h2>
          <p class="text-sm text-text-muted mb-6 leading-relaxed max-w-[280px]">
            登录后可使用知识库、收藏论文、浏览更多推荐内容
          </p>
          <button
            class="w-full max-w-[280px] py-3.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none mb-3"
            @click="router.push('/login')"
          >
            登录
          </button>
          <button
            class="w-full max-w-[280px] py-3.5 rounded-full bg-bg-card border border-border text-text-primary text-base font-semibold"
            @click="router.push('/register')"
          >
            注册
          </button>
        </div>

        <!-- Theme toggle even if not logged in -->
        <div class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <button
            class="w-full flex items-center gap-3 px-4 py-4 bg-transparent border-none text-left active:bg-bg-hover transition-colors"
            @click="toggleTheme"
          >
            <div class="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center">
              <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-gold">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-tinder-gold">
                <circle cx="12" cy="12" r="5"/>
                <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
            </div>
            <span class="flex-1 text-base text-text-primary">外观模式</span>
            <span class="text-sm text-text-muted">{{ isDark ? '深色' : '浅色' }}</span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
