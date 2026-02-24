<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import SwipeCard from '../components/SwipeCard.vue'
import ActionBar from '../components/ActionBar.vue'
import DateSelector from '../components/DateSelector.vue'
import {
  fetchDates, fetchDigest, addKbPaper, dismissPaper,
  fetchIdeaDigest, createIdeaFeedback,
} from '../api'
import type { PaperSummary, IdeaCandidate } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'

defineOptions({ name: 'RecommendView' })

const router = useRouter()
const route = useRoute()

// Top-level mode: 'paper' | 'idea'
type Mode = 'paper' | 'idea'
const activeMode = ref<Mode>('paper')

// ---------------------------------------------------------------------------
// Paper state
// ---------------------------------------------------------------------------
const dates = ref<string[]>([])
const selectedDate = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)
const error = ref('')
const totalAvailable = ref(0)
const quotaLimit = ref<number | null>(null)
const responseTier = ref<string>('anonymous')

const currentIndex = ref(0)
const history = ref<number[]>([])

const currentPaper = computed(() => papers.value[currentIndex.value] ?? null)
const allSwiped = computed(() => papers.value.length > 0 && currentIndex.value >= papers.value.length)

const isQuotaExceeded = computed(() => {
  if (loading.value) return false
  const limit = quotaLimit.value
  const count = papers.value.length
  if (limit === null || count === 0) return false
  return currentIndex.value >= count && count >= limit
})

const isActuallyLimited = computed(() => {
  if (quotaLimit.value === null) return false
  return totalAvailable.value > papers.value.length
})

const quotaMessage = computed(() => {
  const tier = responseTier.value
  const limit = quotaLimit.value
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') return `Pro 账号上限（${limit ?? 15} 条）`
  if (tier === 'anonymous') return `未登录上限（${limit ?? 3} 条）`
  return `普通账号上限（${limit ?? 3} 条）`
})

// ---------------------------------------------------------------------------
// Idea state
// ---------------------------------------------------------------------------
const ideaCandidates = ref<IdeaCandidate[]>([])
const ideaLoading = ref(false)
const ideaError = ref('')
const ideaTotalAvailable = ref(0)
const ideaQuotaLimit = ref<number | null>(null)
const ideaIndex = ref(0)
const ideaHistory = ref<number[]>([])

const currentIdea = computed(() => ideaCandidates.value[ideaIndex.value] ?? null)
const allIdeasSwiped = computed(() => ideaCandidates.value.length > 0 && ideaIndex.value >= ideaCandidates.value.length)

const isIdeaQuotaExceeded = computed(() => {
  if (ideaLoading.value) return false
  const limit = ideaQuotaLimit.value
  const count = ideaCandidates.value.length
  if (limit === null || count === 0) return false
  return ideaIndex.value >= count && count >= limit
})

const isIdeaActuallyLimited = computed(() => {
  if (ideaQuotaLimit.value === null) return false
  return ideaTotalAvailable.value > ideaCandidates.value.length
})

// Status badge helpers
const statusLabel: Record<string, string> = {
  draft: '草稿', review: '评审中', approved: '已通过', archived: '已归档', implemented: '已落地',
}
const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/20 text-yellow-400',
  review: 'bg-blue-500/20 text-blue-400',
  approved: 'bg-green-500/20 text-green-400',
  archived: 'bg-gray-500/20 text-gray-400',
  implemented: 'bg-purple-500/20 text-purple-400',
}

// ---------------------------------------------------------------------------
// Init & load
// ---------------------------------------------------------------------------
onMounted(async () => {
  await ensureAuthInitialized()
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch {
    error.value = '获取日期失败'
  }
})

async function loadDigest(date: string) {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchDigest(date)
    papers.value = Array.isArray(res.papers) ? res.papers : []
    totalAvailable.value = res.total_available ?? papers.value.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (isAuthenticated.value ? currentTier.value : 'anonymous')
    currentIndex.value = 0
    history.value = []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    papers.value = []
  } finally {
    loading.value = false
  }
}

async function loadIdeaDigest(date: string) {
  if (!isAuthenticated.value) return
  ideaLoading.value = true
  ideaError.value = ''
  try {
    const res = await fetchIdeaDigest(date)
    ideaCandidates.value = Array.isArray(res.candidates) ? res.candidates : []
    ideaTotalAvailable.value = res.total_available ?? ideaCandidates.value.length
    ideaQuotaLimit.value = res.quota_limit ?? null
    ideaIndex.value = 0
    ideaHistory.value = []
  } catch (e: any) {
    ideaError.value = e?.message || '加载失败'
    ideaCandidates.value = []
  } finally {
    ideaLoading.value = false
  }
}

watch(selectedDate, (date) => {
  if (date) {
    loadDigest(date)
    if (activeMode.value === 'idea') loadIdeaDigest(date)
  }
})

watch(isAuthenticated, () => {
  if (selectedDate.value) {
    loadDigest(selectedDate.value)
    if (activeMode.value === 'idea') loadIdeaDigest(selectedDate.value)
  }
})

watch(activeMode, (mode) => {
  if (mode === 'idea' && selectedDate.value && ideaCandidates.value.length === 0 && !ideaLoading.value) {
    loadIdeaDigest(selectedDate.value)
  }
})

// ---------------------------------------------------------------------------
// Paper actions
// ---------------------------------------------------------------------------
function handleSwipeLeft() {
  const paper = currentPaper.value
  history.value.push(currentIndex.value)
  currentIndex.value++
  if (paper && isAuthenticated.value) {
    dismissPaper(paper.paper_id).catch(() => {})
  }
}

function handleSwipeRight() {
  const paper = currentPaper.value
  if (!paper) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  history.value.push(currentIndex.value)
  currentIndex.value++
  addKbPaper(paper.paper_id, paper).catch(() => {})
}

function handleSwipeUp() {
  if (currentPaper.value) router.push(`/paper/${currentPaper.value.paper_id}`)
}

function skip() { handleSwipeLeft() }
function like() { handleSwipeRight() }
function undo() {
  if (history.value.length === 0) return
  currentIndex.value = history.value.pop()!
}
function openDetail() {
  if (currentPaper.value) router.push(`/paper/${currentPaper.value.paper_id}`)
}
function resetCards() { currentIndex.value = 0; history.value = [] }

// ---------------------------------------------------------------------------
// Idea actions
// ---------------------------------------------------------------------------
function skipIdea() {
  const idea = currentIdea.value
  ideaHistory.value.push(ideaIndex.value)
  ideaIndex.value++
  if (idea && isAuthenticated.value) {
    createIdeaFeedback({ candidate_id: idea.id, action: 'skip' }).catch(() => {})
  }
}

function collectIdea() {
  const idea = currentIdea.value
  if (!idea) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  ideaHistory.value.push(ideaIndex.value)
  ideaIndex.value++
  createIdeaFeedback({ candidate_id: idea.id, action: 'collect' }).catch(() => {})
}

function openIdeaDetail() {
  if (currentIdea.value) router.push(`/idea/${currentIdea.value.id}`)
}

function undoIdea() {
  if (ideaHistory.value.length === 0) return
  ideaIndex.value = ideaHistory.value.pop()!
}

function resetIdeas() { ideaIndex.value = 0; ideaHistory.value = [] }
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center justify-between px-5 pt-4 pb-1">
        <h1 class="text-xl font-bold gradient-text shrink-0">推荐</h1>
        <!-- Date selector -->
        <DateSelector
          v-if="dates.length > 0"
          :dates="dates"
          v-model="selectedDate"
        />
        <!-- Counter -->
        <div v-if="activeMode === 'paper' && papers.length > 0 && currentPaper" class="text-sm text-text-muted shrink-0 tabular-nums">
          {{ currentIndex + 1 }}/{{ papers.length }}
        </div>
        <div v-else-if="activeMode === 'idea' && ideaCandidates.length > 0 && currentIdea" class="text-sm text-text-muted shrink-0 tabular-nums">
          {{ ideaIndex + 1 }}/{{ ideaCandidates.length }}
        </div>
        <div v-else class="w-8"></div>
      </div>

      <!-- Mode tabs -->
      <div class="flex items-center gap-2 px-5 pb-2">
        <button
          class="flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-all border-none"
          :class="activeMode === 'paper'
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'
            : 'bg-bg-elevated text-text-muted active:bg-bg-hover'"
          @click="activeMode = 'paper'"
        >
          <span>📰</span> 论文
        </button>
        <button
          class="flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-all border-none"
          :class="activeMode === 'idea'
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'
            : 'bg-bg-elevated text-text-muted active:bg-bg-hover'"
          @click="activeMode = 'idea'"
        >
          <span>💡</span> 灵感
        </button>
      </div>
    </div>

    <!-- ===== PAPER MODE ===== -->
    <template v-if="activeMode === 'paper'">
      <div class="flex-1 relative overflow-hidden">
        <div v-if="loading" class="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <svg class="animate-spin h-10 w-10 text-tinder-pink" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
          </svg>
          <span class="text-text-muted text-base">加载论文中...</span>
        </div>

        <div v-else-if="error" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8">
          <span class="text-tinder-pink text-lg">{{ error }}</span>
          <button class="px-6 py-2.5 rounded-full bg-tinder-pink text-white text-base font-medium border-none" @click="loadDigest(selectedDate)">
            重试
          </button>
        </div>

        <div v-else-if="isQuotaExceeded && isActuallyLimited && quotaMessage" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="text-6xl">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">查看限制</h2>
          <p class="text-base text-text-secondary">{{ quotaMessage }}</p>
          <template v-if="!isAuthenticated">
            <p class="text-sm text-text-muted">登录后即可继续浏览</p>
            <button
              class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
              @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
            >立即登录</button>
          </template>
          <template v-else>
            <p class="text-sm text-text-muted">升级账号可查看更多论文</p>
          </template>
        </div>

        <div v-else-if="allSwiped" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="text-6xl">🎉</div>
          <h2 class="text-xl font-bold text-text-primary">今日论文已全部浏览</h2>
          <p class="text-sm text-text-muted">共浏览 {{ papers.length }} 篇</p>
          <button class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none" @click="resetCards">
            重新浏览
          </button>
        </div>

        <div v-else-if="currentPaper" class="absolute inset-0 mx-4 my-3">
          <SwipeCard
            :key="currentPaper.paper_id"
            :paper="currentPaper"
            @swipe-left="handleSwipeLeft"
            @swipe-right="handleSwipeRight"
            @swipe-up="handleSwipeUp"
          />
        </div>

        <div v-else-if="!loading && selectedDate" class="absolute inset-0 flex items-center justify-center text-text-muted text-base">
          该日期暂无论文
        </div>
      </div>

      <div class="shrink-0" v-if="currentPaper && !loading">
        <ActionBar @undo="undo" @skip="skip" @like="like" @detail="openDetail" />
      </div>
    </template>

    <!-- ===== IDEA MODE ===== -->
    <template v-else-if="activeMode === 'idea'">
      <div class="flex-1 relative overflow-hidden">
        <!-- Not authenticated -->
        <div v-if="!isAuthenticated" class="absolute inset-0 flex flex-col items-center justify-center gap-5 px-8 text-center">
          <div class="text-6xl">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">登录后查看灵感推荐</h2>
          <p class="text-sm text-text-muted leading-relaxed">灵感推荐功能需要登录才能使用</p>
          <button
            class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
            @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
          >立即登录</button>
        </div>

        <!-- Loading -->
        <div v-else-if="ideaLoading" class="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <div class="relative w-12 h-12 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
            <span class="text-2xl">💡</span>
          </div>
          <span class="text-text-muted text-base">加载灵感中...</span>
        </div>

        <!-- Error -->
        <div v-else-if="ideaError" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8">
          <span class="text-tinder-pink text-lg">{{ ideaError }}</span>
          <button class="px-6 py-2.5 rounded-full bg-tinder-pink text-white text-base font-medium border-none" @click="loadIdeaDigest(selectedDate)">
            重试
          </button>
        </div>

        <!-- Quota exceeded -->
        <div v-else-if="isIdeaQuotaExceeded && isIdeaActuallyLimited" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="text-6xl">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">灵感查看限制</h2>
          <p class="text-sm text-text-muted">升级账号可查看更多灵感推荐</p>
        </div>

        <!-- All swiped -->
        <div v-else-if="allIdeasSwiped" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="text-6xl">✨</div>
          <h2 class="text-xl font-bold text-text-primary">今日灵感已全部浏览</h2>
          <p class="text-sm text-text-muted">共浏览 {{ ideaCandidates.length }} 个灵感</p>
          <button class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none" @click="resetIdeas">
            重新浏览
          </button>
        </div>

        <!-- Idea card -->
        <div v-else-if="currentIdea" class="absolute inset-0 mx-4 my-3 overflow-y-auto">
          <div class="min-h-full rounded-2xl bg-bg-card border border-border shadow-xl overflow-hidden flex flex-col">
            <!-- Card header gradient -->
            <div class="h-2 bg-gradient-to-r from-[#fd267a] to-[#ff6036] shrink-0"></div>

            <div class="flex-1 p-5 flex flex-col gap-4">
              <!-- Status + scores -->
              <div class="flex items-center gap-2 flex-wrap">
                <span
                  class="text-xs px-2.5 py-1 rounded-full font-medium"
                  :class="statusColor[currentIdea.status] || 'bg-bg-elevated text-text-muted'"
                >
                  {{ statusLabel[currentIdea.status] || currentIdea.status }}
                </span>
                <template v-if="currentIdea.scores">
                  <span class="text-xs text-text-muted">
                    新颖 <span class="font-semibold" :class="currentIdea.scores.novelty >= 7 ? 'text-green-400' : currentIdea.scores.novelty >= 5 ? 'text-yellow-400' : 'text-red-400'">{{ currentIdea.scores.novelty?.toFixed(1) }}</span>
                  </span>
                  <span class="text-xs text-text-muted">
                    可行 <span class="font-semibold" :class="currentIdea.scores.feasibility >= 7 ? 'text-green-400' : currentIdea.scores.feasibility >= 5 ? 'text-yellow-400' : 'text-red-400'">{{ currentIdea.scores.feasibility?.toFixed(1) }}</span>
                  </span>
                  <span class="text-xs text-text-muted">
                    影响 <span class="font-semibold" :class="currentIdea.scores.impact >= 7 ? 'text-green-400' : currentIdea.scores.impact >= 5 ? 'text-yellow-400' : 'text-red-400'">{{ currentIdea.scores.impact?.toFixed(1) }}</span>
                  </span>
                </template>
              </div>

              <!-- Title -->
              <h2 class="text-lg font-bold text-text-primary leading-snug">{{ currentIdea.title }}</h2>

              <!-- Goal -->
              <div>
                <p class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">🎯 目标</p>
                <p class="text-sm text-text-secondary leading-relaxed">{{ currentIdea.goal }}</p>
              </div>

              <!-- Mechanism -->
              <div v-if="currentIdea.mechanism">
                <p class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1.5">⚙️ 核心机制</p>
                <p class="text-sm text-text-secondary leading-relaxed line-clamp-4">{{ currentIdea.mechanism }}</p>
              </div>

              <!-- Tags -->
              <div v-if="currentIdea.tags?.length" class="flex flex-wrap gap-1.5">
                <span
                  v-for="t in currentIdea.tags"
                  :key="t"
                  class="text-xs px-2 py-0.5 rounded-full bg-bg-elevated text-text-muted border border-border"
                >{{ t }}</span>
              </div>

              <!-- Source atoms count -->
              <div v-if="currentIdea.input_atom_ids?.length" class="text-xs text-text-muted mt-auto pt-2 border-t border-border">
                基于 {{ currentIdea.input_atom_ids.length }} 个灵感原子
              </div>
            </div>

            <!-- Tap to detail hint -->
            <button
              class="w-full py-3 text-sm text-text-muted bg-bg-elevated border-t border-border active:bg-bg-hover transition-colors flex items-center justify-center gap-2"
              @click="openIdeaDetail"
            >
              查看详情
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- No data -->
        <div v-else-if="!ideaLoading && selectedDate" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center">
          <div class="text-5xl">💡</div>
          <p class="text-base text-text-muted">该日期暂无灵感推荐</p>
        </div>
      </div>

      <!-- Idea action bar -->
      <div v-if="currentIdea && !ideaLoading && isAuthenticated" class="shrink-0 px-6 py-4 safe-area-bottom">
        <div class="flex items-center justify-around">
          <!-- Undo -->
          <button
            class="w-12 h-12 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xl shadow active:bg-bg-hover transition-colors"
            :disabled="ideaHistory.length === 0"
            :class="ideaHistory.length === 0 ? 'opacity-30' : ''"
            @click="undoIdea"
          >↩️</button>

          <!-- Skip -->
          <button
            class="w-14 h-14 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-2xl shadow active:bg-bg-hover transition-colors"
            @click="skipIdea"
          >⏭️</button>

          <!-- Detail -->
          <button
            class="w-12 h-12 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xl shadow active:bg-bg-hover transition-colors"
            @click="openIdeaDetail"
          >🔍</button>

          <!-- Collect -->
          <button
            class="w-14 h-14 rounded-full bg-gradient-to-br from-[#fd267a] to-[#ff6036] flex items-center justify-center text-2xl shadow-lg active:opacity-80 transition-opacity border-none"
            @click="collectIdea"
          >⭐</button>
        </div>
      </div>
    </template>
  </div>
</template>
