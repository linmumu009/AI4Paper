<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import type { KbScope } from '../api'
import { saveCompareResult } from '../api'

const props = defineProps<{
  paperIds: string[]
  /** Short titles keyed by paper_id (for display) */
  paperTitles?: Record<string, string>
  scope?: KbScope
}>()

const emit = defineEmits<{
  close: []
  saved: [resultId: number]
}>()

// Markdown renderer
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

// State
type Phase = 'loading' | 'streaming' | 'done' | 'error'
const phase = ref<Phase>('loading')
const rawMarkdown = ref('')
const errorMsg = ref('')
const contentRef = ref<HTMLElement | null>(null)

// Rendered HTML
const renderedHtml = computed(() => md.render(rawMarkdown.value))

// Copy button state
const copied = ref(false)

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(rawMarkdown.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

// Auto-scroll to bottom during streaming
function scrollToBottom() {
  nextTick(() => {
    if (contentRef.value) {
      contentRef.value.scrollTop = contentRef.value.scrollHeight
    }
  })
}

// SSE streaming logic
let abortController: AbortController | null = null

async function startStreaming() {
  phase.value = 'loading'
  rawMarkdown.value = ''
  errorMsg.value = ''

  abortController = new AbortController()

  try {
    const response = await fetch('/api/kb/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        paper_ids: props.paperIds,
        scope: props.scope || 'kb',
      }),
      signal: abortController.signal,
    })

    if (!response.ok) {
      const text = await response.text()
      errorMsg.value = `请求失败 (${response.status}): ${text}`
      phase.value = 'error'
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      errorMsg.value = '无法读取响应流'
      phase.value = 'error'
      return
    }

    phase.value = 'streaming'
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Process SSE lines
      const lines = buffer.split('\n')
      // Keep the last (possibly incomplete) line in buffer
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()

        if (payload === '[DONE]') {
          phase.value = 'done'
          return
        }

        try {
          // Each payload is a JSON-encoded string chunk
          const text = JSON.parse(payload) as string
          rawMarkdown.value += text
          scrollToBottom()
        } catch {
          // If not valid JSON, treat as raw text
          rawMarkdown.value += payload
          scrollToBottom()
        }
      }
    }

    // If we exited the loop without [DONE], mark as done
    if (phase.value === 'streaming') {
      phase.value = 'done'
    }
  } catch (e: any) {
    if (e.name === 'AbortError') return
    errorMsg.value = e?.message || '请求失败'
    phase.value = 'error'
  }
}

function stopStreaming() {
  abortController?.abort()
  abortController = null
  if (phase.value === 'streaming' || phase.value === 'loading') {
    phase.value = 'done'
  }
}

onMounted(() => {
  startStreaming()
})

onBeforeUnmount(() => {
  stopStreaming()
})

function getPaperTitle(paperId: string): string {
  return props.paperTitles?.[paperId] || paperId
}

// ---- Save to compare library ----
const saved = ref(false)
const saving = ref(false)

async function saveToLibrary() {
  if (saving.value || saved.value || !rawMarkdown.value) return
  saving.value = true
  try {
    // Build a title from paper titles
    const titles = props.paperIds.map(id => getPaperTitle(id))
    const title = titles.length <= 2
      ? titles.join(' vs ')
      : `${titles[0]} 等${titles.length}篇对比`
    const result = await saveCompareResult(title, rawMarkdown.value, props.paperIds)
    saved.value = true
    emit('saved', result.id)
  } catch {
    // 保存失败时不改变状态
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 px-5 py-3 border-b border-border bg-bg-card">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          <h2 class="text-base font-bold text-text-primary">论文对比分析</h2>
          <span
            v-if="phase === 'streaming'"
            class="text-[10px] px-2 py-0.5 rounded-full bg-[#8b5cf6]/20 text-[#8b5cf6] font-medium animate-pulse"
          >分析中...</span>
          <span
            v-else-if="phase === 'done'"
            class="text-[10px] px-2 py-0.5 rounded-full bg-tinder-green/20 text-tinder-green font-medium"
          >已完成</span>
        </div>
        <div class="flex items-center gap-2">
          <!-- Save to compare library -->
          <button
            v-if="phase === 'done' && rawMarkdown"
            class="px-3 py-1 rounded-full text-xs font-medium border cursor-pointer transition-colors flex items-center gap-1"
            :class="saved
              ? 'text-[#8b5cf6] border-[#8b5cf6]/30 bg-[#8b5cf6]/10'
              : 'text-text-muted border-border bg-transparent hover:bg-bg-hover'"
            :disabled="saving || saved"
            @click="saveToLibrary"
          >
            <svg v-if="!saved" xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" />
            </svg>
            {{ saving ? '保存中...' : saved ? '已保存' : '保存到对比库' }}
          </button>
          <!-- Copy -->
          <button
            v-if="phase === 'done' && rawMarkdown"
            class="px-3 py-1 rounded-full text-xs font-medium border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors flex items-center gap-1"
            :class="copied ? 'text-tinder-green border-tinder-green/30' : 'text-text-muted'"
            @click="copyToClipboard"
          >
            <svg v-if="!copied" xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            {{ copied ? '已复制' : '复制' }}
          </button>
          <button
            v-if="phase === 'streaming'"
            class="px-3 py-1 rounded-full text-xs text-tinder-pink border border-tinder-pink/30 bg-transparent cursor-pointer hover:bg-tinder-pink/10 transition-colors"
            @click="stopStreaming"
          >停止</button>
          <button
            class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="emit('close')"
          >关闭</button>
        </div>
      </div>

      <!-- Selected papers tags -->
      <div class="flex flex-wrap gap-1.5">
        <span
          v-for="pid in paperIds"
          :key="pid"
          class="text-[11px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-secondary"
        >
          📄 {{ getPaperTitle(pid) }}
        </span>
      </div>
    </div>

    <!-- Content area -->
    <div ref="contentRef" class="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
      <!-- Loading state -->
      <div v-if="phase === 'loading'" class="flex flex-col items-center justify-center h-full gap-4">
        <div class="relative w-16 h-16 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#6366f1] border-r-[#8b5cf6] animate-spin"></div>
          <div class="absolute inset-2 rounded-full border-2 border-transparent border-b-[#6366f1] border-l-[#8b5cf6] animate-spin" style="animation-direction: reverse; animation-duration: 1.5s;"></div>
          <span class="text-2xl relative z-10">📊</span>
        </div>
        <h3 class="text-sm font-semibold text-text-primary">正在聚合论文数据...</h3>
        <p class="text-xs text-text-muted">AI 正在阅读并对比 {{ paperIds.length }} 篇论文</p>
      </div>

      <!-- Error state -->
      <div v-else-if="phase === 'error'" class="flex flex-col items-center justify-center h-full gap-4">
        <div class="text-4xl">⚠️</div>
        <h3 class="text-sm font-semibold text-tinder-pink">分析失败</h3>
        <p class="text-xs text-text-muted max-w-md text-center">{{ errorMsg }}</p>
        <button
          class="px-4 py-2 rounded-full bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white text-xs font-medium border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="startStreaming"
        >重试</button>
      </div>

      <!-- Markdown content (streaming or done) -->
      <div
        v-else
        class="compare-markdown prose prose-sm max-w-none"
        v-html="renderedHtml"
      ></div>
    </div>
  </div>
</template>

<style scoped>
/* Markdown content styling */
.compare-markdown :deep(h1) {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary, #e8e6e3);
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
}

.compare-markdown :deep(h2) {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-primary, #e8e6e3);
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
}

.compare-markdown :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary, #e8e6e3);
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
}

.compare-markdown :deep(p) {
  color: var(--color-text-secondary, #b0ada8);
  line-height: 1.7;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}

.compare-markdown :deep(ul),
.compare-markdown :deep(ol) {
  color: var(--color-text-secondary, #b0ada8);
  padding-left: 1.5rem;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
}

.compare-markdown :deep(li) {
  margin-bottom: 0.25rem;
  line-height: 1.6;
}

.compare-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1rem;
  font-size: 0.8125rem;
}

.compare-markdown :deep(th) {
  background: var(--color-bg-elevated, #1e1e1e);
  color: var(--color-text-primary, #e8e6e3);
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  border: 1px solid var(--color-border, #2a2a2a);
}

.compare-markdown :deep(td) {
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border, #2a2a2a);
  color: var(--color-text-secondary, #b0ada8);
}

.compare-markdown :deep(tr:nth-child(even)) {
  background: var(--color-bg-elevated, #1e1e1e);
}

.compare-markdown :deep(strong) {
  color: var(--color-text-primary, #e8e6e3);
  font-weight: 600;
}

.compare-markdown :deep(code) {
  background: var(--color-bg-elevated, #1e1e1e);
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  font-size: 0.8125rem;
  color: #c084fc;
}

.compare-markdown :deep(blockquote) {
  border-left: 3px solid #8b5cf6;
  padding-left: 1rem;
  color: var(--color-text-muted, #7a7a7a);
  font-style: italic;
  margin: 0.75rem 0;
}

.compare-markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border, #2a2a2a);
  margin: 1.25rem 0;
}
</style>
