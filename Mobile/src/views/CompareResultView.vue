<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchCompareResult } from '../api'
import type { KbCompareResult } from '../types/paper'

defineOptions({ name: 'CompareResultView' })

const route = useRoute()
const router = useRouter()

const result = ref<KbCompareResult | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  const id = Number(route.params.id)
  if (!id) {
    error.value = '无效的对比结果 ID'
    loading.value = false
    return
  }
  try {
    result.value = await fetchCompareResult(id)
  } catch (e: any) {
    error.value = e.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
})

function goBack() {
  router.back()
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-primary">
    <!-- Header -->
    <div class="shrink-0 safe-area-top flex items-center gap-3 px-4 pt-4 pb-3 border-b border-border">
      <button
        class="w-9 h-9 rounded-full bg-bg-elevated flex items-center justify-center text-text-primary border-none"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <h1 class="text-base font-bold text-text-primary truncate flex-1">
        {{ result?.title || '对比结果' }}
      </h1>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 py-4">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-16">
        <svg class="animate-spin h-8 w-8 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center justify-center py-16 text-center">
        <div class="text-4xl mb-4">⚠️</div>
        <p class="text-sm text-tinder-pink">{{ error }}</p>
      </div>

      <!-- Result -->
      <template v-else-if="result">
        <!-- Meta -->
        <div class="flex items-center gap-4 mb-4 text-xs text-text-muted">
          <span>{{ result.paper_ids.length }} 篇论文</span>
          <span>{{ formatDate(result.created_at) }}</span>
        </div>

        <!-- Markdown content -->
        <div class="prose-mobile text-sm text-text-primary leading-relaxed whitespace-pre-wrap break-words">
          {{ result.markdown }}
        </div>
      </template>
    </div>
  </div>
</template>
