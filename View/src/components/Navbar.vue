<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useRouter } from 'vue-router'
import { currentUser, ensureAuthInitialized, isAdmin, isAuthenticated, logout } from '../stores/auth'
import { isDark, toggleTheme } from '../stores/theme'

const route = useRoute()
const router = useRouter()

const navItems = [
  { to: '/', icon: '🔥', label: '发现' },
  { to: '/inspiration', icon: '💡', label: '灵感' },
]

// Dropdown state
const showDropdown = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

function toggleDropdown() {
  showDropdown.value = !showDropdown.value
}

function closeDropdown() {
  showDropdown.value = false
}

function goProfile() {
  closeDropdown()
  router.push('/profile')
}

function handleClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    closeDropdown()
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})

async function goLogin() {
  await router.push({ path: '/login', query: { redirect: route.fullPath } })
}

async function doLogout() {
  closeDropdown()
  await logout()
  if (route.name === 'note-editor' || route.name === 'profile') {
    await router.replace('/')
  }
}
</script>

<template>
  <nav class="h-12 sm:h-14 flex items-center justify-between px-3 sm:px-5 bg-bg-sidebar border-b border-border">
    <!-- Logo -->
    <router-link to="/" class="flex items-center gap-1.5 no-underline shrink-0">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"
           class="w-7 h-7 sm:w-8 sm:h-8 flex-shrink-0" aria-hidden="true">
        <defs>
          <linearGradient id="nav-fg" x1="256" y1="273" x2="256" y2="88" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stop-color="#fd267a"/>
            <stop offset="100%" stop-color="#ff6036"/>
          </linearGradient>
          <linearGradient id="nav-ig" x1="256" y1="268" x2="256" y2="133" gradientUnits="userSpaceOnUse">
            <stop offset="0%"   stop-color="#ff8c00" stop-opacity="0.9"/>
            <stop offset="100%" stop-color="#ffe066" stop-opacity="0.55"/>
          </linearGradient>
        </defs>
        <path d="M148,260 L320,260 L364,304 L364,426 L148,426 Z"
              fill="rgba(255,255,255,0.12)" stroke="rgba(255,255,255,0.25)" stroke-width="4"/>
        <path d="M320,260 L364,260 L364,304 Z"
              fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" stroke-width="3"/>
        <rect x="172" y="320" width="114" height="10" rx="5" fill="rgba(255,255,255,0.20)"/>
        <rect x="172" y="346" width="152" height="10" rx="5" fill="rgba(255,255,255,0.14)"/>
        <rect x="172" y="372" width="96"  height="10" rx="5" fill="rgba(255,255,255,0.11)"/>
        <path d="M170,273 C150,243 145,206 158,170 C166,146 182,133 192,146
                 C200,156 197,174 206,168 C214,161 212,140 221,123
                 C230,105 246,96 256,88 C266,96 282,105 291,123
                 C300,140 298,161 306,168 C315,174 312,156 320,146
                 C330,133 346,146 354,170 C367,206 362,243 342,273 Z"
              fill="url(#nav-fg)"/>
        <path d="M210,268 C198,244 195,214 206,188 C213,170 227,162 233,174
                 C237,183 234,197 241,193 C248,188 245,170 253,154
                 C256,145 256,136 256,133 C256,136 256,145 259,154
                 C267,170 264,188 271,193 C278,197 275,183 279,174
                 C285,162 299,170 306,188 C317,214 314,244 302,268 Z"
              fill="url(#nav-ig)" opacity="0.65"/>
      </svg>
      <span class="text-lg sm:text-xl gradient-text font-bold tracking-tight">AI4Papers</span>
    </router-link>

    <!-- Center nav icons -->
    <div class="flex items-center gap-1">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :title="item.label"
        class="w-9 h-9 sm:w-10 sm:h-10 flex items-center justify-center rounded-full no-underline text-base sm:text-lg transition-all duration-200"
        :class="(item.to === '/' ? route.path === '/' : route.path.startsWith(item.to))
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        {{ item.icon }}
      </router-link>
    </div>

    <!-- Right auth area -->
    <div class="flex items-center justify-end gap-2 shrink-0">
      <!-- Download installer button -->
      <a
        href="/api/download/latest-installer"
        download
        title="下载客户端安装包"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 no-underline text-text-muted hover:text-text-secondary hover:bg-bg-hover"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
      </a>

      <!-- Workbench entry button -->
      <router-link
        to="/workbench"
        title="工作台"
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full transition-all duration-200 no-underline"
        :class="route.path.startsWith('/workbench') || route.path.startsWith('/idea')
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="20" height="14" rx="2"/><polyline points="8 21 12 17 16 21"/>
        </svg>
      </router-link>

      <!-- Theme toggle -->
      <button
        class="w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center rounded-full text-text-muted hover:text-text-primary hover:bg-bg-hover transition-all duration-200 cursor-pointer bg-transparent border-none"
        :title="isDark ? '切换到日间模式' : '切换到夜间模式'"
        @click="toggleTheme"
      >
        <!-- Sun icon (shown in dark mode → click to go light) -->
        <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px] transition-transform duration-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
        <!-- Moon icon (shown in light mode → click to go dark) -->
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 sm:w-[18px] sm:h-[18px] transition-transform duration-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      </button>

      <template v-if="isAuthenticated">
        <!-- User dropdown -->
        <div ref="dropdownRef" class="relative">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click.stop="toggleDropdown"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
            </svg>
            <span class="truncate max-w-[4rem] hidden sm:inline">{{ currentUser?.username }}</span>
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 transition-transform" :class="showDropdown ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>

          <!-- Dropdown menu -->
          <Transition
            enter-active-class="transition duration-150 ease-out"
            enter-from-class="opacity-0 -translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition duration-100 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 -translate-y-1"
          >
            <div
              v-if="showDropdown"
              class="absolute right-0 top-full mt-1.5 w-40 py-1 bg-bg-card border border-border rounded-lg shadow-xl z-50"
            >
              <button
                class="w-full px-4 py-2 text-left text-xs text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors flex items-center gap-2"
                @click="goProfile"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                个人中心
              </button>
              <div class="mx-2 my-1 border-t border-border"></div>
              <button
                class="w-full px-4 py-2 text-left text-xs text-text-muted hover:bg-bg-hover hover:text-tinder-pink transition-colors flex items-center gap-2"
                @click="doLogout"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                退出登录
              </button>
            </div>
          </Transition>
        </div>
      </template>
      <template v-else>
        <button
          class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="goLogin"
        >
          登录
        </button>
      </template>
    </div>
  </nav>
</template>
