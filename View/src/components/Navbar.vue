<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { useRouter } from 'vue-router'
import { currentUser, ensureAuthInitialized, isAdmin, isAuthenticated, logout } from '../stores/auth'

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
  <nav class="h-14 flex items-center justify-between px-5 bg-bg-sidebar border-b border-border">
    <!-- Logo -->
    <router-link to="/" class="flex items-center gap-2 no-underline">
      <span class="text-xl gradient-text font-bold tracking-tight">AI4Papers</span>
    </router-link>

    <!-- Center nav icons -->
    <div class="flex items-center gap-1">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :title="item.label"
        class="w-10 h-10 flex items-center justify-center rounded-full no-underline text-lg transition-all duration-200"
        :class="route.path === item.to
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        {{ item.icon }}
      </router-link>
    </div>

    <!-- Right auth area -->
    <div class="w-56 flex items-center justify-end gap-2">
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
            <span class="truncate max-w-20">{{ currentUser?.username }}</span>
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
