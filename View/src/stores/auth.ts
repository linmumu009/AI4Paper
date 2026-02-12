import { computed, reactive } from 'vue'
import { authLogin, authLogout, authMe, authRegister } from '../api'
import type { AuthUser } from '../types/paper'

const state = reactive<{
  initialized: boolean
  loading: boolean
  user: AuthUser | null
}>({
  initialized: false,
  loading: false,
  user: null,
})

export const isAuthenticated = computed(() => !!state.user)
export const currentUser = computed(() => state.user)
export const authLoading = computed(() => state.loading)
export const currentTier = computed(() => state.user?.tier ?? 'free')
export const isAdmin = computed(() => state.user?.role === 'admin' || state.user?.role === 'superadmin')
export const isSuperAdmin = computed(() => state.user?.role === 'superadmin')

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

export async function register(username: string, password: string) {
  state.loading = true
  try {
    const res = await authRegister({ username, password })
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
  } finally {
    state.loading = false
  }
}
