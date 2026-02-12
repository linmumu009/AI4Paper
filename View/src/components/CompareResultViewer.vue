<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import { fetchCompareResult } from '../api'
import type { KbCompareResult } from '../types/paper'

const props = defineProps<{
  resultId: number
  paperTitles?: Record<string, string>
}>()

const emit = defineEmits<{
  close: []
}>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

const loading = ref(true)
const error = ref('')
const result = ref<KbCompareResult | null>(null)

const renderedHtml = computed(() => {
  if (!result.value) return ''
  return md.render(result.value.markdown)
})

const copied = ref(false)

async function copyToClipboard() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value.markdown)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

async function loadResult() {
  loading.value = true
  error.value = ''
  try {
    result.value = await fetchCompareResult(props.resultId)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function getPaperTitle(paperId: string): string {
  return props.paperTitles?.[paperId] || paperId
}

onMounted(loadResult)
watch(() => props.resultId, loadResult)
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
          <h2 class="text-base font-bold text-text-primary truncate">{{ result?.title || '对比结果' }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <button
            v-if="result"
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
            class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="emit('close')"
          >关闭</button>
        </div>
      </div>
      <!-- Paper tags -->
      <div v-if="result" class="flex flex-wrap gap-1.5">
        <span
          v-for="pid in result.paper_ids"
          :key="pid"
          class="text-[11px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-secondary"
        >
          📄 {{ getPaperTitle(pid) }}
        </span>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
      <!-- Loading -->
      <div v-if="loading" class="flex flex-col items-center justify-center h-full gap-4">
        <svg class="animate-spin h-8 w-8 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <span class="text-sm text-text-muted">加载对比结果...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex flex-col items-center justify-center h-full gap-4">
        <div class="text-4xl">⚠️</div>
        <h3 class="text-sm font-semibold text-tinder-pink">加载失败</h3>
        <p class="text-xs text-text-muted">{{ error }}</p>
        <button
          class="px-4 py-2 rounded-full bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white text-xs font-medium border-none cursor-pointer hover:opacity-90 transition-opacity"
          @click="loadResult"
        >重试</button>
      </div>

      <!-- Markdown -->
      <div
        v-else-if="result"
        class="compare-markdown prose prose-sm max-w-none"
        v-html="renderedHtml"
      ></div>
    </div>
  </div>
</template>

<style scoped>
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
