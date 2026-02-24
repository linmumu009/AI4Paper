import { computed, reactive } from 'vue'
import { authLogin, authLoginSms, authLogout, authMe, authRegister, authSendSms, fetchAuthProfile, updateAuthProfile, setAuthPassword, changeAuthPassword } from '../api'
import type { AuthUser } from '../types/paper'

const state = reactive<{
  initialized: boolean
  loading: boolean
  user: AuthUser | null
  isNewUser: boolean
}>({
  initialized: false,
  loading: false,
  user: null,
  isNewUser: false,
})

export const isAuthenticated = computed(() => !!state.user)
export const currentUser = computed(() => state.user)
export const authLoading = computed(() => state.loading)
export const currentTier = computed(() => state.user?.tier ?? 'free')
export const isAdmin = computed(() => state.user?.role === 'admin' || state.user?.role === 'superadmin')
export const isSuperAdmin = computed(() => state.user?.role === 'superadmin')
export const isNewUser = computed(() => state.isNewUser)
export const isProfileComplete = computed(() => {
  const u = state.user
  if (!u) return false
  return !u.is_phone_auto_created && !!u.nickname
})

export async function fetchMe() {
  state.loading = true
  try {
    const res = await authMe()
    state.user = res.authenticated ? res.user : null
  } catch {
    state.user = null
  } finally {
    state.initialized = true
    state.loading = false
  }
}

export async function ensureAuthInitialized() {
  if (state.initialized) return
  await fetchMe()
}

export async function login(username: string, password: string) {
  state.loading = true
  try {
    const res = await authLogin({ username, password })
    state.user = res.user
    state.initialized = true
    return res.user
  } finally {
    state.loading = false
  }
}

export async function loginBySms(phone: string, code: string) {
  state.loading = true
  try {
    const res = await authLoginSms({ phone, code })
    state.user = res.user
    state.initialized = true
    state.isNewUser = res.is_new_user ?? false
    return res
  } finally {
    state.loading = false
  }
}

export async function sendSms(phone: string) {
  return await authSendSms({ phone })
}

export async function register(username: string, password: string, phone: string, smsCode: string) {
  state.loading = true
  try {
    const res = await authRegister({ username, password, phone, sms_code: smsCode })
    return res.user
  } finally {
    state.loading = false
  }
}

export async function logout() {
  state.loading = true
  try {
    await authLogout()
    state.user = null
    state.initialized = true
    state.isNewUser = false
  } finally {
    state.loading = false
  }
}

export async function refreshProfile() {
  try {
    const res = await fetchAuthProfile()
    if (res.user) {
      state.user = res.user
    }
    return res.user
  } catch {
    return null
  }
}

export async function saveProfile(payload: { nickname?: string; username?: string }) {
  const res = await updateAuthProfile(payload)
  if (res.user) {
    state.user = res.user
    state.isNewUser = false
  }
  return res.user
}

export async function setPassword(password: string) {
  const res = await setAuthPassword({ password })
  if (res.user) state.user = res.user
  return res.user
}

export async function changePassword(oldPassword: string, newPassword: string) {
  const res = await changeAuthPassword({ old_password: oldPassword, new_password: newPassword })
  if (res.user) state.user = res.user
  return res.user
}
