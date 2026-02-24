<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchIdeaBenchmarks, createIdeaBenchmark, deleteIdeaBenchmark } from '../api'
import type { IdeaEvalBenchmark } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const router = useRouter()

const benchmarks = ref<IdeaEvalBenchmark[]>([])
const loading = ref(false)
const error = ref('')

// New benchmark form
const showForm = ref(false)
const newName = ref('')
const newDesc = ref('')

async function loadBenchmarks() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaBenchmarks({ limit: 500 })
    benchmarks.value = res.benchmarks
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) await loadBenchmarks()
})

watch(() => isAuthenticated.value, (authed) => {
  if (authed) loadBenchmarks()
  else benchmarks.value = []
})

async function handleCreate() {
  if (!newName.value.trim()) return
  try {
    await createIdeaBenchmark({ name: newName.value.trim(), description: newDesc.value.trim() || undefined })
    newName.value = ''
    newDesc.value = ''
    showForm.value = false
    await loadBenchmarks()
  } catch {}
}

async function handleDelete(id: number) {
  try {
    await deleteIdeaBenchmark(id)
    benchmarks.value = benchmarks.value.filter((b) => b.id !== id)
  } catch {}
}

const expandedId = ref<number | null>(null)
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 px-4 sm:px-6 pt-4 sm:pt-6 pb-4 border-b border-border bg-bg">
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <button
            class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors flex items-center gap-1.5"
            @click="router.push('/idea')"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            返回
          </button>
          <h1 class="text-xl font-bold text-text-primary flex items-center gap-2">
            <span class="text-2xl">📊</span> 评测回放
          </h1>
        </div>
        <button
          class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
          @click="showForm = !showForm"
        >
          + 新建基准
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 sm:p-6">
      <!-- Create form -->
      <div v-if="showForm" class="bg-bg-card border border-border rounded-lg p-4 mb-4 space-y-3">
        <input v-model="newName" type="text" placeholder="基准名称" class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light" />
        <textarea v-model="newDesc" rows="2" placeholder="描述（可选）" class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light resize-none" />
        <div class="flex justify-end gap-2">
          <button class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:bg-bg-hover" @click="showForm = false">取消</button>
          <button class="text-xs px-3 py-1.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white border-none cursor-pointer hover:opacity-90" @click="handleCreate">创建</button>
        </div>
      </div>

      <div v-if="loading" class="flex items-center justify-center min-h-[200px]">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">📊</span>
        </div>
      </div>

      <div v-else-if="error" class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>

      <div v-else-if="benchmarks.length === 0" class="flex items-center justify-center min-h-[200px]">
        <div class="text-center">
          <p class="text-3xl mb-3">📊</p>
          <p class="text-sm text-text-muted">还没有评测基准。创建一个基准来跟踪模型升级带来的收益。</p>
        </div>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="bm in benchmarks"
          :key="bm.id"
          class="bg-bg-card border border-border rounded-lg overflow-hidden hover:border-border-light transition-colors"
        >
          <div class="p-4 cursor-pointer" @click="expandedId = expandedId === bm.id ? null : bm.id">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="text-sm font-semibold text-text-primary">{{ bm.name }}</h3>
                <p v-if="bm.model_version" class="text-[10px] text-text-muted mt-0.5">模型: {{ bm.model_version }}</p>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-[10px] text-text-muted">{{ bm.question_ids?.length || 0 }} 题</span>
                <button
                  class="text-[10px] px-2 py-0.5 rounded border border-border bg-transparent text-text-muted cursor-pointer hover:text-red-400 hover:border-red-500/30 transition-colors"
                  @click.stop="handleDelete(bm.id)"
                >
                  删除
                </button>
              </div>
            </div>
          </div>

          <div v-if="expandedId === bm.id" class="px-4 pb-4 border-t border-border/50 pt-3">
            <div v-if="bm.results && Object.keys(bm.results).length" class="space-y-2">
              <div v-for="(result, version) in bm.results" :key="String(version)" class="bg-bg-elevated rounded-lg p-3">
                <div class="text-xs font-semibold text-text-secondary mb-1">{{ version }}</div>
                <pre class="text-[10px] text-text-muted whitespace-pre-wrap">{{ JSON.stringify(result, null, 2) }}</pre>
              </div>
            </div>
            <p v-else class="text-xs text-text-muted">暂无评测结果。运行复利层后，结果会在此显示。</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
