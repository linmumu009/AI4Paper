/**
 * Tauri Desktop App Entry Point
 *
 * Thin wrapper around the View/ frontend.
 * Differences from View/src/main.ts:
 *   1. VITE_API_BASE env var drives API_ORIGIN inside View/src/api/index.ts,
 *      so all requests reach the remote server without a proxy.
 *   2. No mobile redirect script.
 *   3. Tauri global-shortcut is registered here after app mounts.
 */

// ── Vue app bootstrap (reusing View/ codebase) ───────────────────────────────
import { createApp } from 'vue'
import App from '@view/App.vue'
import router from '@view/router/index'
import { initTheme } from '@view/stores/theme'
// Tailwind + View theme — exe-local wrapper adds @source for View components
import './app.css'

initTheme()

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const app = createApp(App as any)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
app.use(router as any)
app.mount('#app')

// ── Tauri global shortcut (Ctrl+Shift+A = show/focus window) ─────────────────
// The import is lazy so this file still works in a plain browser dev session
// (e.g. `npm run vite:dev` without Tauri wrapper).
async function registerGlobalShortcut() {
  try {
    const { register } = await import('@tauri-apps/plugin-global-shortcut')
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    await register('CommandOrControl+Shift+A', async () => {
      const win = getCurrentWindow()
      const visible = await win.isVisible()
      if (visible) {
        await win.setFocus()
      } else {
        await win.show()
        await win.setFocus()
      }
    })
  } catch {
    // Running in plain browser — skip
  }
}

registerGlobalShortcut()
