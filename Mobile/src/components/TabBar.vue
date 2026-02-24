<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const currentTab = computed(() => {
  return (route.meta?.tab as string) || ''
})

const tabs = [
  { key: 'recommend', label: '推荐', icon: 'fire' },
  { key: 'idea', label: '灵感', icon: 'bulb' },
  { key: 'knowledge', label: '知识库', icon: 'book' },
  { key: 'profile', label: '我的', icon: 'user' },
] as const

function goTo(tab: string) {
  if (currentTab.value === tab) return
  router.push(`/${tab}`)
}
</script>

<template>
  <nav class="shrink-0 bg-bg-card border-t border-border safe-area-bottom">
    <div class="flex items-stretch h-16">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="flex-1 flex flex-col items-center justify-center gap-1 border-none bg-transparent cursor-pointer transition-colors"
        :class="currentTab === tab.key ? 'text-tinder-pink' : 'text-text-muted'"
        @click="goTo(tab.key)"
      >
        <!-- Fire icon -->
        <svg v-if="tab.icon === 'fire'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>
        </svg>
        <!-- Bulb icon (灵感) -->
        <svg v-if="tab.icon === 'bulb'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/>
          <path d="M9 18h6"/>
          <path d="M10 22h4"/>
        </svg>
        <!-- Book icon -->
        <svg v-if="tab.icon === 'book'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        <!-- User icon -->
        <svg v-if="tab.icon === 'user'" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
        <span class="text-[10px] font-medium leading-none">{{ tab.label }}</span>
      </button>
    </div>
  </nav>
</template>
