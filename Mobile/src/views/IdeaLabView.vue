<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchIdeaCandidates,
  fetchIdeaStats,
  createIdeaFeedback,
} from '../api'
import type { IdeaCandidate } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

defineOptions({ name: 'IdeaLabView' })

const router = useRouter()

const candidates = ref<IdeaCandidate[]>([])
const loading = ref(false)
const error = ref('')
const statsData = ref<Record<string, any> | null>(null)

const searchQuery = ref('')

type Tab = 'all' | 'draft' | 'review' | 'approved' | 'archived' | 'implemented'
const activeTab = ref<Tab>('all')

const tabItems: { key: Tab; label: string; icon: string }[] = [
  { key: 'all', label: '全部', icon: '📋' },
  { key: 'draft', label: '草稿', icon: '✏️' },
  { key: 'review', label: '评审中', icon: '🔍' },
  { key: 'approved', label: '已通过', icon: '✅' },
  { key: 'archived', label: '已归档', icon: '📦' },
  { key: 'implemented', label: '已落地', icon: '🚀' },
]

const filteredCandidates = computed(() => {
  let list = candidates.value
  if (activeTab.value !== 'all') {
    list = list.filter((c) => c.status === activeTab.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(
      (c) =>
        c.title.toLowerCase().includes(q) ||
        c.goal.toLowerCase().includes(q) ||
        c.mechanism?.toLowerCase().includes(q) ||
        c.tags?.some((t) => t.toLowerCase().includes(q)),
    )
  }
  return list
})

const tabCounts = computed(() => {
  const counts: Record<string, number> = { all: candidates.value.length }
  for (const c of candidates.value) {
    counts[c.status] = (counts[c.status] || 0) + 1
  }
  return counts
})

async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidates({ limit: 500 })
    candidates.value = res.candidates
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    const res = await fetchIdeaStats()
    statsData.value = res.stats
  } catch {}
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) {
    await Promise.all([loadCandidates(), loadStats()])
  }
})

watch(() => isAuthenticated.value, (authed) => {
  if (authed) {
    loadCandidates()
    loadStats()
  } else {
    candidates.value = []
    statsData.value = null
  }
})

function openCandidate(id: number) {
  router.push(`/idea/${id}`)
}

const statusLabel: Record<string, string> = {
  draft: '草稿',
  review: '评审中',
  approved: '已通过',
  archived: '已归档',
  implemented: '已落地',
}

const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/15 text-yellow-400',
  review: 'bg-blue-500/15 text-blue-400',
  approved: 'bg-green-500/15 text-green-400',
  archived: 'bg-gray-500/15 text-gray-400',
  implemented: 'bg-purple-500/15 text-purple-400',
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Stats bar -->
    <div v-if="statsData" class="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-border bg-bg-elevated">
      <div class="flex items-center gap-1.5 text-xs text-text-muted">
        <span class="text-text-secondary font-semibold">{{ statsData.total_atoms || 0 }}</span> 原子
      </div>
      <div class="w-px h-3 bg-border" />
      <div class="flex items-center gap-1.5 text-xs text-text-muted">
        <span class="text-text-secondary font-semibold">{{ statsData.total_candidates || 0 }}</span> 灵感
      </div>
      <div class="w-px h-3 bg-border" />
      <div class="flex items-center gap-1.5 text-xs text-text-muted">
        <span class="text-green-400 font-semibold">{{ statsData.total_approved || 0 }}</span> 已通过
      </div>
    </div>

    <!-- Tabs + Search -->
    <div class="shrink-0 px-4 py-2 border-b border-border bg-bg">
      <div class="flex items-center gap-1 overflow-x-auto no-scrollbar mb-2">
        <button
          v-for="tab in tabItems"
          :key="tab.key"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors border-none"
          :class="activeTab === tab.key
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white font-semibold'
            : 'bg-bg-elevated text-text-muted active:bg-bg-hover'"
          @click="activeTab = tab.key"
        >
          {{ tab.icon }} {{ tab.label }}
          <span v-if="tabCounts[tab.key]" class="ml-1 text-[10px] opacity-80">{{ tabCounts[tab.key] }}</span>
        </button>
      </div>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索灵感..."
        class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink"
      />
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- Not authenticated -->
      <div v-if="!isAuthenticated" class="flex items-center justify-center min-h-[300px] px-8">
        <div class="flex flex-col items-center gap-4 text-center">
          <div class="w-16 h-16 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-3xl">🔒</div>
          <h3 class="text-base font-semibold text-text-primary">登录后使用灵感工作台</h3>
          <p class="text-xs text-text-muted">灵感生成、评审、收藏等功能需要登录</p>
          <button
            class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white border-none"
            @click="router.push('/login')"
          >
            去登录
          </button>
        </div>
      </div>

      <!-- Loading -->
      <div v-else-if="loading" class="flex items-center justify-center min-h-[300px]">
        <div class="flex flex-col items-center gap-4">
          <div class="relative w-12 h-12 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
            <span class="text-2xl">🧪</span>
          </div>
          <p class="text-sm text-text-muted">加载中...</p>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex items-center justify-center min-h-[300px] px-8">
        <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
          {{ error }}
        </div>
      </div>

      <!-- Empty -->
      <div v-else-if="filteredCandidates.length === 0" class="flex items-center justify-center min-h-[300px] px-8">
        <div class="flex flex-col items-center gap-5 text-center">
          <div class="relative w-20 h-20 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse" />
            <span class="text-5xl relative z-10">💡</span>
          </div>
          <h2 class="text-lg font-bold text-text-primary">
            {{ candidates.length === 0 ? '还没有灵感' : '没有匹配的灵感' }}
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            {{ candidates.length === 0
              ? '运行灵感流水线后，灵感会在此出现。'
              : '尝试调整筛选条件或搜索关键词。'
            }}
          </p>
        </div>
      </div>

      <!-- Candidate list -->
      <div v-else class="space-y-2 p-4">
        <div
          v-for="candidate in filteredCandidates"
          :key="candidate.id"
          class="bg-bg-card border border-border rounded-xl p-4 active:bg-bg-hover transition-colors"
          @click="openCandidate(candidate.id)"
        >
          <div class="flex items-start justify-between gap-3 mb-2">
            <h3 class="text-base font-semibold text-text-primary flex-1 line-clamp-2">{{ candidate.title }}</h3>
            <span
              class="text-[10px] px-2 py-0.5 rounded-full border shrink-0"
              :class="statusColor[candidate.status] || 'bg-bg-elevated text-text-muted border-border'"
            >
              {{ statusLabel[candidate.status] || candidate.status }}
            </span>
          </div>
          <p class="text-sm text-text-secondary line-clamp-2 mb-2">{{ candidate.goal }}</p>
          <div class="flex items-center gap-2 flex-wrap">
            <span v-if="candidate.scores?.overall" class="text-xs text-text-muted">
              评分: <span class="font-semibold" :class="candidate.scores.overall >= 7 ? 'text-green-400' : candidate.scores.overall >= 5 ? 'text-yellow-400' : 'text-red-400'">{{ candidate.scores.overall.toFixed(1) }}</span>
            </span>
            <span v-if="candidate.input_atom_ids?.length" class="text-xs text-text-muted">
              {{ candidate.input_atom_ids.length }} 个原子
            </span>
            <span v-if="candidate.tags?.length" class="text-xs text-text-muted">
              {{ candidate.tags.slice(0, 3).join(', ') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
