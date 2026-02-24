<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import IdeaCard from '../components/idea/IdeaCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import {
  fetchIdeaCandidates,
  fetchIdeaStats,
  createIdeaFeedback,
} from '../api'
import type { IdeaCandidate } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const router = useRouter()

// Data
const candidates = ref<IdeaCandidate[]>([])
const loading = ref(false)
const error = ref('')
const statsData = ref<Record<string, any> | null>(null)

// Filters
const statusFilter = ref<string>('')
const searchQuery = ref('')

// Tabs
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

// Computed filtered list
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

// Tab counts
const tabCounts = computed(() => {
  const counts: Record<string, number> = { all: candidates.value.length }
  for (const c of candidates.value) {
    counts[c.status] = (counts[c.status] || 0) + 1
  }
  return counts
})

// Card navigation
const currentIndex = ref(0)
const cardAnimClass = ref('card-enter')
const history = ref<number[]>([])

const currentCandidate = computed(() => filteredCandidates.value[currentIndex.value] ?? null)
const remaining = computed(() => filteredCandidates.value.length - currentIndex.value)
const allSwiped = computed(() => filteredCandidates.value.length > 0 && currentIndex.value >= filteredCandidates.value.length)

// Reset index when tab or search changes
watch([activeTab, searchQuery], () => {
  currentIndex.value = 0
  history.value = []
  cardAnimClass.value = 'card-enter'
})

// Load data
async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidates({ limit: 500 })
    candidates.value = res.candidates
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
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
    currentIndex.value = 0
    history.value = []
  }
})

// Actions
function openCandidate(id: number) {
  router.push(`/idea/candidates/${id}`)
}

async function collectCandidate(id: number) {
  try {
    await createIdeaFeedback({ candidate_id: id, action: 'collect' })
  } catch {}
}

async function discardCandidate(id: number) {
  try {
    await createIdeaFeedback({ candidate_id: id, action: 'discard' })
    // Remove from list immediately for better UX
    const idx = candidates.value.findIndex((c) => c.id === id)
    if (idx !== -1) {
      candidates.value.splice(idx, 1)
      // Adjust currentIndex if needed
      if (currentIndex.value > 0 && currentIndex.value >= candidates.value.length) {
        currentIndex.value = Math.max(0, candidates.value.length - 1)
      }
    }
  } catch {}
}

// Card navigation
function next(direction: 'left' | 'right') {
  if (!currentCandidate.value) return
  cardAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  history.value.push(currentIndex.value)
  setTimeout(() => {
    currentIndex.value++
    cardAnimClass.value = 'card-enter'
  }, 300)
}

function skip() {
  const candidate = currentCandidate.value
  next('left')
  // Discard in background
  if (candidate) {
    discardCandidate(candidate.id).catch(() => {})
  }
}

function like() {
  const candidate = currentCandidate.value
  if (!candidate) return
  // Animate card immediately
  next('right')
  // Collect in background
  collectCandidate(candidate.id).catch(() => {})
}

function undo() {
  if (history.value.length === 0) return
  const prevIdx = history.value.pop()!
  currentIndex.value = prevIdx
  cardAnimClass.value = 'card-enter'
}

function detail() {
  if (currentCandidate.value) {
    openCandidate(currentCandidate.value.id)
  }
}

function resetCards() {
  currentIndex.value = 0
  history.value = []
  cardAnimClass.value = 'card-enter'
}

// Refresh data
async function handleRefresh() {
  await loadCandidates()
  await loadStats()
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 px-4 sm:px-6 pt-4 sm:pt-6 pb-4 border-b border-border bg-bg">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-bold text-text-primary flex items-center gap-2">
            <span class="text-2xl">🧪</span> 灵感工作台
          </h1>
          <span class="text-xs text-text-muted bg-bg-elevated px-2.5 py-1 rounded-full border border-border">
            v2
          </span>
        </div>
        <div class="flex items-center gap-2">
          <!-- Refresh button -->
          <button
            class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2 disabled:opacity-50"
            :disabled="loading || !isAuthenticated"
            @click="handleRefresh"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
            </svg>
            刷新灵感
          </button>
        </div>
      </div>

      <!-- Stats bar -->
      <div v-if="statsData" class="flex items-center gap-4 mb-4">
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
        <div class="w-px h-3 bg-border" />
        <div class="flex items-center gap-1.5 text-xs text-text-muted">
          <span class="text-purple-400 font-semibold">{{ statsData.total_exemplars || 0 }}</span> 范例
        </div>
      </div>

      <!-- Tabs + Search -->
      <div class="flex flex-col sm:flex-row sm:items-center gap-3">
        <div class="flex items-center gap-1 overflow-x-auto no-scrollbar">
          <button
            v-for="tab in tabItems"
            :key="tab.key"
            class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
            :class="activeTab === tab.key
              ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
              : 'bg-transparent text-text-muted border-transparent hover:text-text-secondary hover:bg-bg-hover'"
            @click="activeTab = tab.key"
          >
            {{ tab.icon }} {{ tab.label }}
            <span v-if="tabCounts[tab.key]" class="ml-1 text-[10px] opacity-60">{{ tabCounts[tab.key] }}</span>
          </button>
        </div>
        <div class="flex-1 min-w-0">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索灵感..."
            class="w-full sm:w-64 px-3 py-1.5 text-xs rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light transition-colors"
          />
        </div>
      </div>
    </div>

    <!-- Content area -->
    <div class="flex-1 flex flex-col items-center justify-center relative overflow-hidden">
      <!-- Not authenticated -->
      <div v-if="!isAuthenticated" class="flex-1 flex items-center justify-center min-h-[300px]">
        <div class="flex flex-col items-center gap-4 text-center">
          <div class="w-16 h-16 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-3xl">🔒</div>
          <h3 class="text-base font-semibold text-text-primary">登录后使用灵感工作台</h3>
          <p class="text-xs text-text-muted">灵感生成、评审、收藏等功能需要登录</p>
          <button
            class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="router.push('/login')"
          >
            去登录
          </button>
        </div>
      </div>

      <!-- Loading -->
      <div v-else-if="loading" class="flex items-center justify-center min-h-[300px]">
        <div class="flex flex-col items-center gap-4">
          <div class="relative w-16 h-16 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
            <span class="text-2xl">🧪</span>
          </div>
          <p class="text-sm text-text-muted">加载中...</p>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="flex items-center justify-center min-h-[300px]">
        <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
          {{ error }}
        </div>
      </div>

      <!-- Empty -->
      <div v-else-if="filteredCandidates.length === 0" class="flex items-center justify-center min-h-[300px]">
        <div class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
          <div class="relative w-28 h-28 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse" />
            <span class="text-6xl relative z-10">💡</span>
          </div>
          <h2 class="text-lg font-bold text-text-primary">
            {{ candidates.length === 0 ? '还没有灵感' : '没有匹配的灵感' }}
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            {{ candidates.length === 0
              ? '点击「生成灵感」，AI 将从论文库中提取灵感原子并组合生成研究想法。'
              : '尝试调整筛选条件或搜索关键词。'
            }}
          </p>
          <button
            v-if="candidates.length === 0"
            class="mt-2 px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2 shadow-lg shadow-[#fd267a]/20"
            @click="handleRefresh"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
            </svg>
            刷新灵感
          </button>
        </div>
      </div>

      <!-- All swiped -->
      <div v-else-if="allSwiped" class="flex flex-col items-center gap-4 text-center px-8">
        <div class="text-5xl mb-2">🎉</div>
        <h2 class="text-xl font-bold text-text-primary">今日灵感已全部浏览</h2>
        <p class="text-sm text-text-muted">
          共浏览 {{ filteredCandidates.length }} 条灵感
        </p>
        <button
          class="px-6 py-2.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
          @click="resetCards"
        >
          重新浏览
        </button>
      </div>

      <!-- Card view -->
      <template v-else-if="currentCandidate">
        <!-- Counter -->
        <div class="absolute top-4 left-1/2 -translate-x-1/2 text-xs text-text-muted z-20">
          {{ currentIndex + 1 }} / {{ filteredCandidates.length }}
        </div>

        <!-- The card — responsive width/height -->
        <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(480px, calc(100dvh - 210px), 620px)">
          <IdeaCard
            :key="currentCandidate.id"
            :candidate="currentCandidate"
            :anim-class="cardAnimClass"
            @collect="like"
            @discard="skip"
          />
        </div>

        <!-- Action buttons -->
        <ActionButtons
          @undo="undo"
          @skip="skip"
          @like="like"
          @detail="detail"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
