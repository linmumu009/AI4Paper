import { ref } from 'vue'

const STORAGE_KEY = 'ai4papers-theme'

function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  return 'dark'
}

export const isDark = ref(true)

function applyTheme(theme: 'dark' | 'light') {
  isDark.value = theme === 'dark'
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(STORAGE_KEY, theme)
}

export function initTheme() {
  applyTheme(getInitialTheme())
}

export function toggleTheme() {
  applyTheme(isDark.value ? 'light' : 'dark')
}
