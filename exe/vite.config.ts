import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Tauri dev host (set by Tauri CLI in mobile dev)
const host = process.env.TAURI_DEV_HOST

// ---------------------------------------------------------------------------
// Build-time helper: normalise VITE_API_BASE so the proxy target is always clean
// (strips trailing slashes and accidental /api suffix — mirrors runtime logic in
// View/src/api/index.ts so dev and production behave identically).
// ---------------------------------------------------------------------------
function normaliseApiBase(raw: string): string {
  let s = (raw || '').trim().replace(/\/+$/, '')
  if (s.toLowerCase().endsWith('/api')) s = s.slice(0, -4)
  return s
}

export default defineConfig(({ mode }) => {
  // Load .env so VITE_API_BASE is available for the proxy target
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  // Guard: emit a clear warning when building a production bundle without
  // VITE_API_BASE.  The app will start but every API call will silently fail
  // inside Tauri because there is no server-side proxy.
  if (mode === 'production') {
    const raw = env.VITE_API_BASE || ''
    if (!raw) {
      console.warn(
        '\n⚠️  [Tauri build] VITE_API_BASE is not set in exe/.env.production!\n' +
        '   Without it every API request will fail in the packaged desktop app.\n' +
        '   Create exe/.env.production with:\n' +
        '     VITE_API_BASE=https://your-server.com\n',
      )
    } else {
      const normalised = normaliseApiBase(raw)
      if (normalised !== raw) {
        console.warn(
          `\n⚠️  [Tauri build] VITE_API_BASE="${raw}" was normalised to "${normalised}".\n` +
          '   Update exe/.env.production to avoid this automatic correction.\n',
        )
      }
    }
  }

  const apiTarget = normaliseApiBase(env.VITE_API_BASE) || 'http://127.0.0.1:8000'

  return {
    plugins: [
      vue(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@view': path.resolve(__dirname, '../View/src'),
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      host: host || 'localhost',
      port: 1420,
      strictPort: true,
      hmr: host
        ? {
            protocol: 'ws',
            host,
            port: 1421,
          }
        : undefined,
      // Always proxy in dev mode — avoids CORS.
      // VITE_API_BASE from .env controls the target; falls back to localhost.
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/static': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    envPrefix: ['VITE_', 'TAURI_'],
    build: {
      target: process.env.TAURI_ENV_PLATFORM === 'windows'
        ? 'chrome105'
        : process.env.TAURI_ENV_PLATFORM === 'macos'
          ? 'safari13'
          : 'chrome105',
      minify: process.env.TAURI_ENV_DEBUG ? false : 'esbuild',
      sourcemap: !!process.env.TAURI_ENV_DEBUG,
    },
  }
})
