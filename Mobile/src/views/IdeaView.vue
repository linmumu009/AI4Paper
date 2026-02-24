<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import IdeaSwipeCard from '../components/IdeaSwipeCard.vue'
import ActionBar from '../components/ActionBar.vue'
import DateSelector from '../components/DateSelector.vue'
import {
  fetchDates,
  fetchIdeaDigest,
  fetchIdeaCandidates,
  fetchIdeaStats,
  createIdeaFeedback,
} from '../api'
import type { IdeaCandidate } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

defineOptions({ name: 'IdeaView' })

const router = useRouter()
const route = useRoute()

// ─── Mode toggle ─────────────────────────────────────────────────────────────
type Mode = 'digest' | 'lab'
const activeMode = ref<Mode>('digest')

// ─── Digest mode state ────────────────────────────────────────────────────────
const dates = ref<string[]>([])
const selectedDate = ref('')
const digestCandidates = ref<IdeaCandidate[]>([])
const digestLoading = ref(false)
const digestError = ref('')
const digestIndex = ref(0)
const digestHistory = ref<number[]>([])
const digestTotalAvailable = ref(0)
const digestQuotaLimit = ref<number | null>(null)

const currentCandidate = computed(() => digestCandidates.value[digestIndex.value] ?? null)
const allSwiped = computed(
  () => digestCandidates.value.length > 0 && digestIndex.value >= digestCandidates.value.length,
)
const isQuotaExceeded = computed(() => {
  if (digestLoading.value || digestQuotaLimit.value === null) return false
  return digestCandidates.value.length < digestTotalAvailable.value && allSwiped.value
})

// ─── Lab mode state ───────────────────────────────────────────────────────────
const labCandidates = ref<IdeaCandidate[]>([])
const labLoading = ref(false)
const labError = ref('')
const labSearch = ref('')
const labTab = ref('all')
const statsData = ref<Record<string, any> | null>(null)
const labLoaded = ref(false)

const labTabItems = [
  { key: 'all', label: '全部' },
  { key: 'draft', label: '草稿' },
  { key: 'review', label: '评审' },
  { key: 'approved', label: '已通过' },
  { key: 'archived', label: '归档' },
  { key: 'implemented', label: '已落地' },
]

const labFiltered = computed(() => {
  let list = labCandidates.value
  if (labTab.value !== 'all') list = list.filter((c) => c.status === labTab.value)
  if (labSearch.value.trim()) {
    const q = labSearch.value.trim().toLowerCase()
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

const labTabCounts = computed(() => {
  const counts: Record<string, number> = { all: labCandidates.value.length }
  for (const c of labCandidates.value) {
    counts[c.status] = (counts[c.status] || 0) + 1
  }
  return counts
})

// ─── Label / color maps ───────────────────────────────────────────────────────
const strategyLabel: Record<string, string> = {
  transfer: '迁移', migration: '迁移', stitch: '缝合', stitching: '缝合',
  counterfactual: '反事实', patch: '修补', patching: '修补',
  resource_constrained: '资源约束', resource_constraint: '资源约束',
}

const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  review: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  approved: 'bg-green-500/15 text-green-400 border-green-500/30',
  archived: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  implemented: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

const statusLabel: Record<string, string> = {
  draft: '草稿', review: '评审中', approved: '已通过', archived: '已归档', implemented: '已落地',
}

// ─── Load functions ───────────────────────────────────────────────────────────
async function loadDates() {
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0 && !selectedDate.value) {
      selectedDate.value = dates.value[0]
    }
  } catch {}
}

async function loadDigest(date: string) {
  if (!date) return
  digestLoading.value = true
  digestError.value = ''
  try {
    const res = await fetchIdeaDigest(date)
    digestCandidates.value = res.candidates ?? []
    digestTotalAvailable.value = res.total_available ?? digestCandidates.value.length
    digestQuotaLimit.value = res.quota_limit ?? null
    digestIndex.value = 0
    digestHistory.value = []
  } catch (e: any) {
    digestError.value = e?.response?.data?.detail || '加载失败'
    digestCandidates.value = []
  } finally {
    digestLoading.value = false
  }
}

async function loadLab() {
  labLoading.value = true
  labError.value = ''
  try {
    const [candidatesRes] = await Promise.all([
      fetchIdeaCandidates({ limit: 500 }),
      fetchIdeaStats().then((r) => { statsData.value = r.stats }).catch(() => {}),
    ])
    labCandidates.value = candidatesRes.candidates
    labLoaded.value = true
  } catch (e: any) {
    labError.value = e?.response?.data?.detail || '加载失败'
  } finally {
    labLoading.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) {
    await loadDates()
  }
})

watch(isAuthenticated, async (authed) => {
  if (authed) {
    await loadDates()
    if (activeMode.value === 'lab' && !labLoaded.value) {
      loadLab()
    }
  } else {
    dates.value = []
    digestCandidates.value = []
    labCandidates.value = []
    labLoaded.value = false
    statsData.value = null
  }
})

watch(selectedDate, (date) => {
  if (date && isAuthenticated.value) loadDigest(date)
})

watch(activeMode, (mode) => {
  if (mode === 'lab' && !labLoaded.value && isAuthenticated.value) {
    loadLab()
  }
})

// ─── Digest actions ───────────────────────────────────────────────────────────
function digestSkip() {
  const c = currentCandidate.value
  if (!c) return
  digestHistory.value.push(digestIndex.value)
  digestIndex.value++
  createIdeaFeedback({ candidate_id: c.id, action: 'discard' }).catch(() => {})
}

function digestLike() {
  const c = currentCandidate.value
  if (!c) return
  digestHistory.value.push(digestIndex.value)
  digestIndex.value++
  createIdeaFeedback({ candidate_id: c.id, action: 'collect' }).catch(() => {})
}

function digestUndo() {
  if (digestHistory.value.length === 0) return
  digestIndex.value = digestHistory.value.pop()!
}

function digestDetail() {
  if (currentCandidate.value) {
    router.push(`/idea/candidates/${currentCandidate.value.id}`)
  }
}

function digestReset() {
  digestIndex.value = 0
  digestHistory.value = []
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- ═══ Header ════════════════════════════════════════════════════════════ -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center gap-3 px-5 pt-4 pb-2">
        <h1 class="text-xl font-bold gradient-text shrink-0">灵感</h1>

        <!-- Mode toggle -->
        <div class="flex items-center gap-0.5 bg-bg-elevated rounded-full p-0.5 border border-border">
          <button
            class="px-3 py-1 text-xs rounded-full transition-colors"
            :class="activeMode === 'digest'
              ? 'bg-bg-card text-text-primary font-semibold shadow-sm'
              : 'text-text-muted'"
            @click="activeMode = 'digest'"
          >
            📅 日报
          </button>
          <button
            class="px-3 py-1 text-xs rounded-full transition-colors"
            :class="activeMode === 'lab'
              ? 'bg-bg-card text-text-primary font-semibold shadow-sm'
              : 'text-text-muted'"
            @click="activeMode = 'lab'"
          >
            🧪 工作台
          </button>
        </div>

        <!-- Date selector (digest only) -->
        <div v-if="activeMode === 'digest'" class="ml-auto">
          <DateSelector
            v-if="dates.length > 0"
            :dates="dates"
            v-model="selectedDate"
          />
        </div>

        <!-- Counter (digest only, when showing cards) -->
        <div
          v-if="activeMode === 'digest' && digestCandidates.length > 0 && currentCandidate"
          class="ml-auto text-sm text-text-muted shrink-0 tabular-nums"
        >
          {{ digestIndex + 1 }}/{{ digestCandidates.length }}
        </div>
      </div>
    </div>

    <!-- ═══ DIGEST MODE ══════════════════════════════════════════════════════ -->
    <template v-if="activeMode === 'digest'">
      <!-- Not authenticated -->
      <div
        v-if="!isAuthenticated"
        class="flex-1 flex flex-col items-center justify-center gap-4 px-8 text-center"
      >
        <div class="text-6xl">💡</div>
        <h2 class="text-xl font-bold text-text-primary">登录后使用灵感日报</h2>
        <p class="text-sm text-text-muted">灵感推荐需要登录账号</p>
        <button
          class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
          @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
        >
          立即登录
        </button>
      </div>

      <!-- Card area -->
      <div v-else class="flex-1 relative overflow-hidden">
        <!-- Loading -->
        <div v-if="digestLoading" class="absolute inset-0 flex flex-col items-center justify-center gap-4">
          <svg class="animate-spin h-10 w-10 text-tinder-pink" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span class="text-text-muted text-base">加载灵感中...</span>
        </div>

        <!-- Error -->
        <div v-else-if="digestError" class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8">
          <span class="text-tinder-pink text-lg">{{ digestError }}</span>
          <button
            class="px-6 py-2.5 rounded-full bg-tinder-pink text-white text-base font-medium border-none"
            @click="loadDigest(selectedDate)"
          >
            重试
          </button>
        </div>

        <!-- Quota exceeded -->
        <div
          v-else-if="isQuotaExceeded"
          class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center"
        >
          <div class="text-6xl">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">灵感日报已达上限</h2>
          <p class="text-sm text-text-muted">升级账号可查看更多灵感</p>
        </div>

        <!-- All swiped -->
        <div
          v-else-if="allSwiped"
          class="absolute inset-0 flex flex-col items-center justify-center gap-4 px-8 text-center"
        >
          <div class="text-6xl">🎉</div>
          <h2 class="text-xl font-bold text-text-primary">今日灵感已全部浏览</h2>
          <p class="text-sm text-text-muted">共浏览 {{ digestCandidates.length }} 条灵感</p>
          <button
            class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
            @click="digestReset"
          >
            重新浏览
          </button>
        </div>

        <!-- Swipe card -->
        <div v-else-if="currentCandidate" class="absolute inset-0 mx-4 my-3">
          <IdeaSwipeCard
            :key="currentCandidate.id"
            :candidate="currentCandidate"
            @swipe-left="digestSkip"
            @swipe-right="digestLike"
            @swipe-up="digestDetail"
          />
        </div>

        <!-- No data -->
        <div
          v-else-if="!digestLoading && selectedDate"
          class="absolute inset-0 flex items-center justify-center text-text-muted text-base"
        >
          该日期暂无灵感
        </div>
      </div>

      <!-- Action bar (digest) -->
      <div v-if="isAuthenticated && currentCandidate && !digestLoading" class="shrink-0">
        <ActionBar
          @undo="digestUndo"
          @skip="digestSkip"
          @like="digestLike"
          @detail="digestDetail"
        />
      </div>
    </template>

    <!-- ═══ LAB MODE ══════════════════════════════════════════════════════════ -->
    <template v-else-if="activeMode === 'lab'">
      <!-- Not authenticated -->
      <div
        v-if="!isAuthenticated"
        class="flex-1 flex flex-col items-center justify-center gap-4 px-8 text-center"
      >
        <div class="text-6xl">🧪</div>
        <h2 class="text-xl font-bold text-text-primary">登录后使用灵感工作台</h2>
        <p class="text-sm text-text-muted">灵感管理需要登录账号</p>
        <button
          class="px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none"
          @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
        >
          立即登录
        </button>
      </div>

      <template v-else>
        <!-- Stats bar -->
        <div
          v-if="statsData"
          class="shrink-0 flex items-center gap-4 px-5 py-2 border-b border-border text-xs text-text-muted overflow-x-auto no-scrollbar"
        >
          <span>
            <span class="text-text-secondary font-semibold">{{ statsData.total_atoms || 0 }}</span> 原子
          </span>
          <span class="w-px h-3 bg-border shrink-0" />
          <span>
            <span class="text-text-secondary font-semibold">{{ statsData.total_candidates || 0 }}</span> 灵感
          </span>
          <span class="w-px h-3 bg-border shrink-0" />
          <span>
            <span class="text-green-400 font-semibold">{{ statsData.total_approved || 0 }}</span> 已通过
          </span>
          <span class="w-px h-3 bg-border shrink-0" />
          <span>
            <span class="text-purple-400 font-semibold">{{ statsData.total_exemplars || 0 }}</span> 范例
          </span>
        </div>

        <!-- Status filter tabs -->
        <div
          class="shrink-0 flex items-center gap-1 px-4 py-2 overflow-x-auto no-scrollbar border-b border-border"
        >
          <button
            v-for="t in labTabItems"
            :key="t.key"
            class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
            :class="labTab === t.key
              ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
              : 'bg-transparent text-text-muted border-transparent'"
            @click="labTab = t.key"
          >
            {{ t.label }}
            <span v-if="labTabCounts[t.key]" class="ml-1 text-[10px] opacity-60">
              {{ labTabCounts[t.key] }}
            </span>
          </button>
        </div>

        <!-- Search bar -->
        <div class="shrink-0 px-4 py-2">
          <input
            v-model="labSearch"
            type="text"
            placeholder="搜索灵感..."
            class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light transition-colors"
          />
        </div>

        <!-- Candidate list -->
        <div class="flex-1 overflow-y-auto">
          <!-- Loading -->
          <div v-if="labLoading" class="flex flex-col items-center justify-center py-16 gap-4">
            <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span class="text-text-muted text-sm">加载中...</span>
          </div>

          <!-- Error -->
          <div v-else-if="labError" class="flex items-center justify-center py-16 px-8">
            <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-center">
              {{ labError }}
            </div>
          </div>

          <!-- Empty -->
          <div v-else-if="labFiltered.length === 0" class="flex flex-col items-center justify-center py-16 gap-4 text-center px-8">
            <div class="text-5xl">💡</div>
            <p class="text-sm text-text-muted">
              {{ labCandidates.length === 0 ? '暂无灵感，等待系统生成' : '没有匹配的灵感' }}
            </p>
            <button
              class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none"
              @click="loadLab"
            >
              刷新
            </button>
          </div>

          <!-- Cards -->
          <div v-else class="px-4 py-3 space-y-3 pb-6">
            <div
              v-for="c in labFiltered"
              :key="c.id"
              class="bg-bg-card border border-border rounded-xl p-4 active:bg-bg-elevated transition-colors cursor-pointer"
              @click="router.push(`/idea/candidates/${c.id}`)"
            >
              <!-- Header row -->
              <div class="flex items-start justify-between gap-2 mb-2">
                <div class="flex items-center gap-2 flex-wrap">
                  <span
                    v-if="c.strategy"
                    class="text-[10px] px-2 py-0.5 rounded-full bg-gradient-to-r from-[#fd267a]/20 to-[#ff6036]/20 text-[#fd267a] border border-[#fd267a]/20"
                  >
                    {{ strategyLabel[c.strategy] || c.strategy }}
                  </span>
                  <span
                    class="text-[10px] px-2 py-0.5 rounded-full border"
                    :class="statusColor[c.status] || 'bg-bg-elevated text-text-muted border-border'"
                  >
                    {{ statusLabel[c.status] || c.status }}
                  </span>
                </div>
                <div
                  v-if="c.scores?.overall != null"
                  class="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold border"
                  :class="c.scores.overall >= 8
                    ? 'border-tag-score-high text-tag-score-high'
                    : c.scores.overall >= 6
                      ? 'border-tag-score-mid text-tag-score-mid'
                      : 'border-tag-score-low text-tag-score-low'"
                  :style="{ background: 'var(--color-bg-elevated)' }"
                >
                  {{ c.scores.overall.toFixed(1) }}
                </div>
              </div>

              <!-- Title -->
              <h3 class="text-sm font-semibold text-text-primary leading-snug mb-1.5">
                {{ c.title }}
              </h3>

              <!-- Goal preview -->
              <p class="text-xs text-text-muted leading-relaxed line-clamp-2">{{ c.goal }}</p>

              <!-- Tags -->
              <div v-if="c.tags?.length" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="tag in c.tags.slice(0, 4)"
                  :key="tag"
                  class="text-[9px] px-1.5 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
