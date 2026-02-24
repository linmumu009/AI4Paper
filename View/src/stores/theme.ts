import { ref } from 'vue'

const STORAGE_KEY = 'ai4papers-theme'

/**
 * 'dark' | 'light'
 * 默认跟随系统 prefers-color-scheme，之后以用户选择为准
 */
function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  // 跟随系统
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  return 'dark'
}

export const isDark = ref(true)

/** 应用主题到 <html> 并持久化 */
function applyTheme(theme: 'dark' | 'light') {
  isDark.value = theme === 'dark'
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem(STORAGE_KEY, theme)
}

/** 初始化主题（在 app mount 前调用） */
export function initTheme() {
  applyTheme(getInitialTheme())
}

/** 切换日间/夜间模式 */
export function toggleTheme() {
  applyTheme(isDark.value ? 'light' : 'dark')
}
