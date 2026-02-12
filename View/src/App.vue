<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import Navbar from './components/Navbar.vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

function goToDigest() {
  // 通知当前页面（如 DailyDigest）执行自动保存/删除逻辑并回到推荐视图
  window.dispatchEvent(new CustomEvent('go-to-digest-click'))
  // 若不在推荐路由，则切换到推荐路由
  if (route.name !== 'digest') {
    router.push({ name: 'digest' })
  }
}

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
  <div class="h-screen flex flex-col bg-bg">
    <!-- Top nav bar -->
    <Navbar />
    <!-- Main content -->
    <main class="flex-1 overflow-hidden relative">
      <router-view />
      <!-- 全局“回到推荐”按钮 -->
      <button
        class="fixed bottom-8 right-8 z-50 px-4 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white shadow-lg border-none cursor-pointer hover:opacity-90 transition-opacity"
        @click="goToDigest"
      >
        回到推荐
      </button>
    </main>
  </div>
</template>
