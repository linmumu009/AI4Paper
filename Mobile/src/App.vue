<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TabBar from './components/TabBar.vue'

const route = useRoute()
const router = useRouter()

// Only show TabBar on tab pages (not on detail/login/register)
const showTabBar = computed(() => {
  const tab = route.meta?.tab
  return !!tab
})

function handleAuthRequired() {
  if (route.path === '/login' || route.path === '/register') return
  router.push({
    path: '/login',
    query: { redirect: route.fullPath },
  })
}

onMounted(() => {
  window.addEventListener('auth-required', handleAuthRequired)
})

onBeforeUnmount(() => {
  window.removeEventListener('auth-required', handleAuthRequired)
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Main content -->
    <main class="flex-1 overflow-hidden relative">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['RecommendView', 'KnowledgeView', 'ProfileView']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <!-- Bottom TabBar -->
    <TabBar v-if="showTabBar" />
  </div>
</template>
