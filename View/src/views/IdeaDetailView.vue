<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  fetchIdeaCandidate,
  fetchIdeaAtom,
  fetchIdeaPlan,
  reviewIdeaCandidate,
  createIdeaFeedback,
  createIdeaPlan,
  createIdeaExemplar,
} from '../api'
import type { IdeaCandidate, IdeaAtom, IdeaPlan } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const route = useRoute()
const router = useRouter()

const candidateId = computed(() => Number(route.params.id))

const candidate = ref<IdeaCandidate | null>(null)
const atoms = ref<IdeaAtom[]>([])
const plan = ref<IdeaPlan | null>(null)
const loading = ref(true)
const error = ref('')

// Review state
const reviewAction = ref<'approve' | 'reject' | 'revise'>('approve')
const reviewFeedback = ref('')
const reviewScores = ref({ novelty: 7, feasibility: 7, impact: 7 })
const submittingReview = ref(false)

// Active tab
type DetailTab = 'overview' | 'evidence' | 'review' | 'plan' | 'history'
const activeTab = ref<DetailTab>('overview')

const detailTabs: { key: DetailTab; label: string; icon: string }[] = [
  { key: 'overview', label: '概览', icon: '📋' },
  { key: 'evidence', label: '证据链', icon: '🔗' },
  { key: 'review', label: '评审', icon: '🔍' },
  { key: 'plan', label: '计划', icon: '📐' },
  { key: 'history', label: '修订历史', icon: '📜' },
]

const statusLabel: Record<string, string> = {
  draft: '草稿', review: '评审中', approved: '已通过', archived: '已归档', implemented: '已落地',
}
const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  review: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  approved: 'bg-green-500/15 text-green-400 border-green-500/30',
  archived: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  implemented: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

async function loadCandidate() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidate(candidateId.value)
    candidate.value = res.candidate

    // Load referenced atoms
    if (res.candidate.input_atom_ids?.length) {
      const atomPromises = res.candidate.input_atom_ids.slice(0, 20).map((aid) =>
        fetchIdeaAtom(aid).then((r) => r.atom).catch(() => null),
      )
      const loaded = await Promise.all(atomPromises)
      atoms.value = loaded.filter((a): a is IdeaAtom => a !== null)
    }

    // Load plan if exists
    try {
      const planRes = await fetchIdeaPlan(candidateId.value)
      plan.value = planRes.plan
    } catch {}
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) {
    await loadCandidate()
    // Record view event
    createIdeaFeedback({ candidate_id: candidateId.value, action: 'view' }).catch(() => {})
  }
})

// Review submission
async function submitReview() {
  submittingReview.value = true
  try {
    await reviewIdeaCandidate(candidateId.value, {
      action: reviewAction.value,
      feedback: reviewFeedback.value || undefined,
      scores: reviewScores.value,
    })
    await loadCandidate()
    reviewFeedback.value = ''
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '评审提交失败'
  } finally {
    submittingReview.value = false
  }
}

// Create plan
const creatingPlan = ref(false)
async function handleCreatePlan() {
  creatingPlan.value = true
  try {
    const res = await createIdeaPlan(candidateId.value, {
      milestones: [],
      metrics: '',
      datasets: '',
      ablation: '',
      cost: '',
      timeline: '',
      full_plan: '',
    } as any)
    plan.value = res.plan
    activeTab.value = 'plan'
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建计划失败'
  } finally {
    creatingPlan.value = false
  }
}

// Mark as exemplar
async function markAsExemplar() {
  if (!candidate.value) return
  try {
    await createIdeaExemplar({
      candidate_id: candidate.value.id,
      name: candidate.value.title,
      description: candidate.value.goal,
      tags: candidate.value.tags,
    })
  } catch {}
}

const atomTypeLabel: Record<string, string> = {
  claim: '论断', method: '方法', setup: '设置', limitation: '局限', tag: '标签',
}
const atomTypeIcon: Record<string, string> = {
  claim: '💬', method: '⚙️', setup: '📊', limitation: '⚠️', tag: '🏷️',
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Top bar -->
    <div class="shrink-0 flex items-center gap-3 px-4 sm:px-6 py-3 border-b border-border bg-bg">
      <button
        class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors flex items-center gap-1.5"
        @click="router.push('/workbench')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        返回
      </button>
      <div class="flex-1 min-w-0">
        <h2 v-if="candidate" class="text-sm font-semibold text-text-primary truncate">
          {{ candidate.title }}
        </h2>
      </div>
      <span
        v-if="candidate"
        class="shrink-0 text-[10px] px-2 py-0.5 rounded-full border"
        :class="statusColor[candidate.status] || 'bg-bg-elevated text-text-muted border-border'"
      >
        {{ statusLabel[candidate.status] || candidate.status }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">🧪</span>
        </div>
        <p class="text-sm text-text-muted">加载中...</p>
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="error && !candidate" class="flex-1 flex items-center justify-center">
      <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>
    </div>

    <!-- Detail content -->
    <template v-else-if="candidate">
      <!-- Tab bar -->
      <div class="shrink-0 flex items-center gap-1 px-4 sm:px-6 py-2 border-b border-border bg-bg overflow-x-auto no-scrollbar">
        <button
          v-for="tab in detailTabs"
          :key="tab.key"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
          :class="activeTab === tab.key
            ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
            : 'bg-transparent text-text-muted border-transparent hover:text-text-secondary hover:bg-bg-hover'"
          @click="activeTab = tab.key"
        >
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="flex-1 overflow-y-auto p-4 sm:p-6">
        <!-- ===== Overview tab ===== -->
        <div v-if="activeTab === 'overview'" class="max-w-3xl space-y-6">
          <!-- Score radar -->
          <div v-if="candidate.scores" class="grid grid-cols-3 gap-3">
            <div v-for="(label, key) in { novelty: '新颖度', feasibility: '可行性', impact: '影响力' }" :key="key"
              class="rounded-lg bg-bg-card border border-border p-3 text-center"
            >
              <div class="text-2xl font-bold"
                :class="(candidate.scores as any)[key] >= 7 ? 'text-green-400' : (candidate.scores as any)[key] >= 5 ? 'text-yellow-400' : 'text-red-400'"
              >
                {{ (candidate.scores as any)[key]?.toFixed(1) ?? '—' }}
              </div>
              <div class="text-[10px] text-text-muted mt-1">{{ label }}</div>
            </div>
          </div>

          <!-- Goal -->
          <div>
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">🎯 目标与适用场景</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4">
              {{ candidate.goal }}
            </p>
          </div>

          <!-- Mechanism -->
          <div v-if="candidate.mechanism">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">⚙️ 核心机制</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4 whitespace-pre-wrap">
              {{ candidate.mechanism }}
            </p>
          </div>

          <!-- Risks -->
          <div v-if="candidate.risks">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">⚠️ 风险与假设</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4 whitespace-pre-wrap">
              {{ candidate.risks }}
            </p>
          </div>

          <!-- Tags -->
          <div v-if="candidate.tags?.length">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">🏷️ 标签</h3>
            <div class="flex flex-wrap gap-2">
              <span v-for="t in candidate.tags" :key="t" class="text-xs px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-muted">
                {{ t }}
              </span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 pt-4 border-t border-border">
            <button
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-green-400 hover:border-green-500/30 hover:bg-green-500/10 transition-colors"
              @click="markAsExemplar"
            >
              ⭐ 标记为范例
            </button>
            <button
              v-if="!plan"
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-blue-400 hover:border-blue-500/30 hover:bg-blue-500/10 transition-colors"
              :disabled="creatingPlan"
              @click="handleCreatePlan"
            >
              📐 生成实验计划
            </button>
            <button
              v-else
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-blue-400 hover:border-blue-500/30 hover:bg-blue-500/10 transition-colors"
              @click="activeTab = 'plan'"
            >
              📐 查看计划
            </button>
          </div>
        </div>

        <!-- ===== Evidence tab ===== -->
        <div v-else-if="activeTab === 'evidence'" class="max-w-3xl space-y-4">
          <h3 class="text-sm font-semibold text-text-primary mb-3">组合来源（{{ atoms.length }} 个原子）</h3>
          <div v-if="atoms.length === 0" class="text-sm text-text-muted bg-bg-card border border-border rounded-lg p-4">
            暂无关联的灵感原子。
          </div>
          <div v-for="atom in atoms" :key="atom.id" class="bg-bg-card border border-border rounded-lg p-4 space-y-2">
            <div class="flex items-center gap-2">
              <span class="text-sm">{{ atomTypeIcon[atom.atom_type] || '📄' }}</span>
              <span class="text-xs font-semibold text-text-primary">{{ atomTypeLabel[atom.atom_type] || atom.atom_type }}</span>
              <span class="text-[10px] text-text-muted">{{ atom.paper_id }}</span>
              <span v-if="atom.section" class="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">{{ atom.section }}</span>
            </div>
            <p class="text-sm text-text-secondary leading-relaxed">{{ atom.content }}</p>
            <!-- Evidence snippets -->
            <div v-if="atom.evidence?.length" class="space-y-1 pl-3 border-l-2 border-border">
              <div v-for="(ev, i) in atom.evidence" :key="i" class="text-xs text-text-muted italic leading-relaxed">
                "{{ ev.snippet }}"
                <span class="text-[10px] text-text-muted ml-1">p.{{ ev.page }}, ¶{{ ev.paragraph }}</span>
              </div>
            </div>
            <!-- Tags -->
            <div v-if="atom.tags?.length" class="flex flex-wrap gap-1">
              <span v-for="t in atom.tags" :key="t" class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">{{ t }}</span>
            </div>
          </div>

          <!-- Candidate-level evidence -->
          <div v-if="candidate.evidence?.length" class="mt-6">
            <h3 class="text-sm font-semibold text-text-primary mb-3">灵感级证据</h3>
            <div v-for="(ev, i) in candidate.evidence" :key="i" class="bg-bg-card border border-border rounded-lg p-3 mb-2">
              <p class="text-xs text-text-secondary italic leading-relaxed">"{{ ev.snippet }}"</p>
              <span class="text-[10px] text-text-muted">p.{{ ev.page }}, ¶{{ ev.paragraph }}</span>
            </div>
          </div>
        </div>

        <!-- ===== Review tab ===== -->
        <div v-else-if="activeTab === 'review'" class="max-w-3xl space-y-6">
          <h3 class="text-sm font-semibold text-text-primary">评审灵感</h3>

          <!-- Score inputs -->
          <div class="grid grid-cols-3 gap-4">
            <div v-for="(label, key) in { novelty: '新颖度', feasibility: '可行性', impact: '影响力' }" :key="key" class="space-y-1">
              <label class="text-xs text-text-muted">{{ label }}</label>
              <input
                v-model.number="(reviewScores as any)[key]"
                type="range" min="1" max="10" step="0.5"
                class="w-full accent-[#fd267a]"
              />
              <div class="text-center text-xs font-semibold text-text-secondary">{{ (reviewScores as any)[key] }}</div>
            </div>
          </div>

          <!-- Action select -->
          <div class="space-y-2">
            <label class="text-xs text-text-muted">决定</label>
            <div class="flex items-center gap-2">
              <button
                v-for="opt in [
                  { key: 'approve', label: '✅ 通过', cls: 'hover:border-green-500/40 hover:bg-green-500/10' },
                  { key: 'revise', label: '📝 修订', cls: 'hover:border-yellow-500/40 hover:bg-yellow-500/10' },
                  { key: 'reject', label: '❌ 拒绝', cls: 'hover:border-red-500/40 hover:bg-red-500/10' },
                ] as const"
                :key="opt.key"
                class="text-xs px-4 py-2 rounded-full border transition-colors cursor-pointer"
                :class="reviewAction === opt.key
                  ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
                  : `bg-transparent text-text-muted border-border ${opt.cls}`"
                @click="reviewAction = opt.key"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>

          <!-- Feedback textarea -->
          <div class="space-y-2">
            <label class="text-xs text-text-muted">反馈意见（可选）</label>
            <textarea
              v-model="reviewFeedback"
              rows="4"
              class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light resize-none transition-colors"
              placeholder="输入你的评审意见..."
            />
          </div>

          <!-- Submit -->
          <button
            class="px-6 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
            :disabled="submittingReview"
            @click="submitReview"
          >
            {{ submittingReview ? '提交中...' : '提交评审' }}
          </button>
        </div>

        <!-- ===== Plan tab ===== -->
        <div v-else-if="activeTab === 'plan'" class="max-w-3xl space-y-4">
          <div v-if="!plan" class="text-center py-12">
            <p class="text-sm text-text-muted mb-4">尚未生成实验计划</p>
            <button
              class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
              :disabled="creatingPlan"
              @click="handleCreatePlan"
            >
              📐 生成实验计划
            </button>
          </div>
          <template v-else>
            <div v-if="plan.full_plan" class="bg-bg-card border border-border rounded-lg p-4">
              <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">完整计划</h4>
              <p class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">{{ plan.full_plan }}</p>
            </div>
            <div v-if="plan.milestones?.length" class="bg-bg-card border border-border rounded-lg p-4">
              <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">里程碑</h4>
              <div v-for="(m, i) in plan.milestones" :key="i" class="flex items-center gap-2 py-1">
                <span class="text-xs">{{ m.status === 'completed' ? '✅' : m.status === 'in_progress' ? '🔄' : '⏳' }}</span>
                <span class="text-sm text-text-secondary">{{ m.name }}</span>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div v-if="plan.datasets" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">数据集</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.datasets }}</p>
              </div>
              <div v-if="plan.metrics" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">指标</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.metrics }}</p>
              </div>
              <div v-if="plan.timeline" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">时间线</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.timeline }}</p>
              </div>
              <div v-if="plan.cost" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">成本</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.cost }}</p>
              </div>
            </div>
          </template>
        </div>

        <!-- ===== History tab ===== -->
        <div v-else-if="activeTab === 'history'" class="max-w-3xl space-y-4">
          <h3 class="text-sm font-semibold text-text-primary">修订历史</h3>
          <div v-if="!candidate.revision_history?.length" class="text-sm text-text-muted bg-bg-card border border-border rounded-lg p-4">
            暂无修订记录。
          </div>
          <div v-for="(entry, i) in candidate.revision_history" :key="i" class="bg-bg-card border border-border rounded-lg p-4 space-y-1">
            <div class="flex items-center gap-2 text-xs text-text-muted">
              <span>{{ entry.timestamp }}</span>
              <span v-if="entry.reviewer_role" class="px-1.5 py-0.5 rounded bg-bg-elevated">{{ entry.reviewer_role }}</span>
            </div>
            <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ entry.content_diff }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
