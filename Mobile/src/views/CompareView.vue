<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchCompareStream, saveCompareResult } from '../api'
import type { KbScope } from '../api'

defineOptions({ name: 'CompareView' })

const route = useRoute()
const router = useRouter()

const paperIds = ref<string[]>([])
const markdown = ref('')
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const saveTitle = ref('')
const showSave = ref(false)

const scope = ref<KbScope>('kb')

onMounted(async () => {
  // Parse paper IDs from query
  const raw = route.query.ids as string || ''
  paperIds.value = raw.split(',').filter(Boolean)
  if (route.query.scope) scope.value = route.query.scope as KbScope

  if (paperIds.value.length < 2) {
    error.value = '至少需要选择2篇论文进行对比'
    loading.value = false
    return
  }

  try {
    const resp = await fetchCompareStream(paperIds.value, scope.value)
    if (!resp.ok) {
      error.value = '对比请求失败'
      loading.value = false
      return
    }

    const reader = resp.body?.getReader()
    if (!reader) {
      error.value = '无法读取流'
      loading.value = false
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''
    loading.value = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Parse SSE events
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6)
          if (payload === '[DONE]') continue
          try {
            const evt = JSON.parse(payload)
            if (evt.type === 'text' || evt.type === 'chunk') {
              markdown.value += evt.content || evt.text || ''
            } else if (evt.type === 'error') {
              error.value = evt.message || '对比出错'
            }
          } catch {
            // If not JSON, treat as raw text
            markdown.value += payload
          }
        }
      }
    }
  } catch (e: any) {
    error.value = e.message || '对比请求失败'
    loading.value = false
  }
})

function goBack() {
  router.back()
}

function openSaveDialog() {
  saveTitle.value = `对比分析 (${paperIds.value.length}篇)`
  showSave.value = true
}

async function handleSave() {
  if (!saveTitle.value.trim()) return
  saving.value = true
  try {
    await saveCompareResult(saveTitle.value.trim(), markdown.value, paperIds.value)
    showSave.value = false
    // Optional: go back or stay
  } catch {}
  saving.value = false
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-primary">
    <!-- Header -->
    <div class="shrink-0 safe-area-top flex items-center justify-between px-4 pt-4 pb-3 border-b border-border">
      <button
        class="w-9 h-9 rounded-full bg-bg-elevated flex items-center justify-center text-text-primary border-none"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <h1 class="text-base font-bold text-text-primary">对比分析</h1>
      <button
        v-if="markdown"
        class="px-3 py-1.5 rounded-full bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white text-sm font-semibold border-none"
        @click="openSaveDialog"
      >保存</button>
      <div v-else class="w-16"></div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-4 py-4">
      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center justify-center py-16">
        <svg class="animate-spin h-10 w-10 text-[#8b5cf6] mb-4" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <p class="text-sm text-text-muted">正在分析 {{ paperIds.length }} 篇论文...</p>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center justify-center py-16 text-center">
        <div class="text-4xl mb-4">⚠️</div>
        <p class="text-sm text-tinder-pink">{{ error }}</p>
        <button
          class="mt-4 px-4 py-2 rounded-xl border border-border text-sm text-text-primary bg-transparent"
          @click="goBack"
        >返回</button>
      </div>

      <!-- Markdown content -->
      <div v-else class="prose-mobile text-sm text-text-primary leading-relaxed whitespace-pre-wrap break-words">
        {{ markdown }}
        <span v-if="loading === false && !markdown && !error" class="text-text-muted">等待响应中...</span>
      </div>
    </div>

    <!-- Save dialog -->
    <Teleport to="body">
      <div v-if="showSave" class="fixed inset-0 z-[9998] bg-black/50 flex items-center justify-center" @click.self="showSave = false">
        <div class="w-[85vw] max-w-[320px] bg-bg-card rounded-2xl overflow-hidden">
          <div class="px-5 py-4 border-b border-border">
            <h3 class="text-base font-semibold text-text-primary">保存对比结果</h3>
          </div>
          <div class="px-5 py-4">
            <input
              v-model="saveTitle"
              placeholder="输入标题"
              class="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-[#8b5cf6]"
              autofocus
              @keydown.enter="handleSave"
            />
          </div>
          <div class="flex border-t border-border">
            <button
              class="flex-1 py-3.5 text-base text-text-muted bg-transparent border-none border-r border-border"
              @click="showSave = false"
            >取消</button>
            <button
              :disabled="saving"
              class="flex-1 py-3.5 text-base font-semibold text-[#8b5cf6] bg-transparent border-none"
              @click="handleSave"
            >{{ saving ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
