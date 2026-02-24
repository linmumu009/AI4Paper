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

// Review
const reviewAction = ref<'approve' | 'reject' | 'revise'>('approve')
const reviewFeedback = ref('')
const reviewScores = ref({ novelty: 7, feasibility: 7, impact: 7 })
const submittingReview = ref(false)
const reviewSuccess = ref(false)

// Plan
const creatingPlan = ref(false)

// Exemplar
const markingExemplar = ref(false)
const exemplarSuccess = ref(false)

// Tabs
type DetailTab = 'overview' | 'evidence' | 'review' | 'plan' | 'history'
const activeTab = ref<DetailTab>('overview')

const detailTabs: { key: DetailTab; label: string }[] = [
  { key: 'overview', label: '📋 概览' },
  { key: 'evidence', label: '🔗 证据链' },
  { key: 'review', label: '🔍 评审' },
  { key: 'plan', label: '📐 计划' },
  { key: 'history', label: '📜 历史' },
]

// ─── Status / display maps ────────────────────────────────────────────────────
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

const atomTypeLabel: Record<string, string> = {
  claim: '论断', method: '方法', setup: '设置', limitation: '局限', tag: '标签',
}
const atomTypeIcon: Record<string, string> = {
  claim: '💬', method: '⚙️', setup: '📊', limitation: '⚠️', tag: '🏷️',
}

// ─── Load ─────────────────────────────────────────────────────────────────────
async function loadCandidate() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidate(candidateId.value)
    candidate.value = res.candidate

    // Load related atoms (up to 20)
    if (res.candidate.input_atom_ids?.length) {
      const atomPromises = res.candidate.input_atom_ids
        .slice(0, 20)
        .map((aid) => fetchIdeaAtom(aid).then((r) => r.atom).catch(() => null))
      const loaded = await Promise.all(atomPromises)
      atoms.value = loaded.filter((a): a is IdeaAtom => a !== null)
    }

    // Load plan
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
    createIdeaFeedback({ candidate_id: candidateId.value, action: 'view' }).catch(() => {})
  }
})

// ─── Review ───────────────────────────────────────────────────────────────────
async function submitReview() {
  submittingReview.value = true
  reviewSuccess.value = false
  try {
    await reviewIdeaCandidate(candidateId.value, {
      action: reviewAction.value,
      feedback: reviewFeedback.value || undefined,
      scores: reviewScores.value,
    })
    reviewFeedback.value = ''
    reviewSuccess.value = true
    await loadCandidate()
    setTimeout(() => { reviewSuccess.value = false }, 2000)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '评审提交失败'
  } finally {
    submittingReview.value = false
  }
}

// ─── Plan ─────────────────────────────────────────────────────────────────────
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

// ─── Exemplar ─────────────────────────────────────────────────────────────────
async function markAsExemplar() {
  if (!candidate.value) return
  markingExemplar.value = true
  exemplarSuccess.value = false
  try {
    await createIdeaExemplar({
      candidate_id: candidate.value.id,
      name: candidate.value.title,
      description: candidate.value.goal,
      tags: candidate.value.tags,
    })
    exemplarSuccess.value = true
    setTimeout(() => { exemplarSuccess.value = false }, 2000)
  } catch {} finally {
    markingExemplar.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-bg">

    <!-- ═══ Top bar ════════════════════════════════════════════════════════════ -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center gap-3 px-4 pt-4 pb-3 border-b border-border">
        <button
          class="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer active:bg-bg-elevated transition-colors"
          @click="router.push('/idea')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          返回
        </button>

        <div class="flex-1 min-w-0">
          <h2 v-if="candidate" class="text-sm font-semibold text-text-primary truncate">
            {{ candidate.title }}
          </h2>
          <div v-else-if="loading" class="h-4 w-32 bg-bg-elevated rounded animate-pulse" />
        </div>

        <span
          v-if="candidate"
          class="shrink-0 text-[10px] px-2 py-0.5 rounded-full border"
          :class="statusColor[candidate.status] || 'bg-bg-elevated text-text-muted border-border'"
        >
          {{ statusLabel[candidate.status] || candidate.status }}
        </span>
      </div>
    </div>

    <!-- ═══ Loading ═══════════════════════════════════════════════════════════ -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">🧪</span>
        </div>
        <p class="text-sm text-text-muted">加载中...</p>
      </div>
    </div>

    <!-- ═══ Error ══════════════════════════════════════════════════════════════ -->
    <div v-else-if="error && !candidate" class="flex-1 flex items-center justify-center px-8">
      <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-center">
        {{ error }}
      </div>
    </div>

    <!-- ═══ Content ════════════════════════════════════════════════════════════ -->
    <template v-else-if="candidate">
      <!-- Tab bar -->
      <div class="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-border bg-bg overflow-x-auto no-scrollbar">
        <button
          v-for="tab in detailTabs"
          :key="tab.key"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
          :class="activeTab === tab.key
            ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
            : 'bg-transparent text-text-muted border-transparent'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Scrollable content -->
      <div class="flex-1 overflow-y-auto p-4 pb-8">

        <!-- ══ Overview tab ════════════════════════════════════════════════════ -->
        <div v-if="activeTab === 'overview'" class="space-y-5">
          <!-- Score cards -->
          <div v-if="candidate.scores" class="grid grid-cols-3 gap-2">
            <div
              v-for="(label, key) in ({ novelty: '新颖度', feasibility: '可行性', impact: '影响力' } as Record<string,string>)"
              :key="key"
              class="rounded-xl bg-bg-card border border-border p-3 text-center"
            >
              <div
                class="text-2xl font-bold"
                :class="(candidate.scores as any)[key] >= 7
                  ? 'text-green-400'
                  : (candidate.scores as any)[key] >= 5
                    ? 'text-yellow-400'
                    : 'text-red-400'"
              >
                {{ (candidate.scores as any)[key]?.toFixed(1) ?? '—' }}
              </div>
              <div class="text-[10px] text-text-muted mt-1">{{ label }}</div>
            </div>
          </div>

          <!-- Goal -->
          <div>
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              🎯 目标与适用场景
            </h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-xl p-4">
              {{ candidate.goal }}
            </p>
          </div>

          <!-- Mechanism -->
          <div v-if="candidate.mechanism">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              ⚙️ 核心机制
            </h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-xl p-4 whitespace-pre-wrap">
              {{ candidate.mechanism }}
            </p>
          </div>

          <!-- Risks -->
          <div v-if="candidate.risks">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              ⚠️ 风险与假设
            </h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-xl p-4 whitespace-pre-wrap">
              {{ candidate.risks }}
            </p>
          </div>

          <!-- Tags -->
          <div v-if="candidate.tags?.length">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              🏷️ 标签
            </h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="t in candidate.tags"
                :key="t"
                class="text-xs px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-muted"
              >
                {{ t }}
              </span>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="flex flex-col gap-3 pt-2 border-t border-border">
            <!-- Exemplar -->
            <button
              class="w-full py-3 rounded-xl border transition-colors text-sm font-medium cursor-pointer"
              :class="exemplarSuccess
                ? 'bg-green-500/10 border-green-500/30 text-green-400'
                : 'border-border bg-transparent text-text-muted active:bg-bg-elevated'"
              :disabled="markingExemplar"
              @click="markAsExemplar"
            >
              {{ exemplarSuccess ? '✅ 已标记为范例' : markingExemplar ? '标记中...' : '⭐ 标记为范例' }}
            </button>
            <!-- Plan -->
            <button
              v-if="!plan"
              class="w-full py-3 rounded-xl border border-border bg-transparent text-text-muted text-sm font-medium cursor-pointer active:bg-bg-elevated transition-colors"
              :disabled="creatingPlan"
              @click="handleCreatePlan"
            >
              {{ creatingPlan ? '生成中...' : '📐 生成实验计划' }}
            </button>
            <button
              v-else
              class="w-full py-3 rounded-xl border border-blue-500/30 bg-blue-500/10 text-blue-400 text-sm font-medium cursor-pointer active:bg-blue-500/20 transition-colors"
              @click="activeTab = 'plan'"
            >
              📐 查看实验计划
            </button>
          </div>
        </div>

        <!-- ══ Evidence tab ════════════════════════════════════════════════════ -->
        <div v-else-if="activeTab === 'evidence'" class="space-y-4">
          <h3 class="text-sm font-semibold text-text-primary">
            组合来源（{{ atoms.length }} 个原子）
          </h3>

          <div
            v-if="atoms.length === 0"
            class="text-sm text-text-muted bg-bg-card border border-border rounded-xl p-4"
          >
            暂无关联的灵感原子。
          </div>

          <div
            v-for="atom in atoms"
            :key="atom.id"
            class="bg-bg-card border border-border rounded-xl p-4 space-y-2"
          >
            <div class="flex items-center gap-2 flex-wrap">
              <span class="text-base">{{ atomTypeIcon[atom.atom_type] || '📄' }}</span>
              <span class="text-xs font-semibold text-text-primary">
                {{ atomTypeLabel[atom.atom_type] || atom.atom_type }}
              </span>
              <span class="text-[10px] text-text-muted font-mono">{{ atom.paper_id }}</span>
              <span v-if="atom.section" class="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">
                {{ atom.section }}
              </span>
            </div>
            <p class="text-sm text-text-secondary leading-relaxed">{{ atom.content }}</p>
            <!-- Evidence snippets -->
            <div v-if="atom.evidence?.length" class="space-y-1 pl-3 border-l-2 border-border">
              <div v-for="(ev, i) in atom.evidence" :key="i" class="text-xs text-text-muted italic leading-relaxed">
                "{{ ev.snippet || ev.text }}"
                <span v-if="ev.page" class="text-[10px] text-text-muted ml-1 not-italic">
                  p.{{ ev.page }}{{ ev.paragraph ? `, ¶${ev.paragraph}` : '' }}
                </span>
              </div>
            </div>
            <!-- Tags -->
            <div v-if="atom.tags?.length" class="flex flex-wrap gap-1">
              <span
                v-for="t in atom.tags"
                :key="t"
                class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted"
              >
                {{ t }}
              </span>
            </div>
          </div>

          <!-- Candidate-level evidence -->
          <div v-if="candidate.evidence?.length" class="mt-4">
            <h3 class="text-sm font-semibold text-text-primary mb-3">灵感级证据</h3>
            <div
              v-for="(ev, i) in candidate.evidence"
              :key="i"
              class="bg-bg-card border border-border rounded-xl p-3 mb-2"
            >
              <p class="text-xs text-text-secondary italic leading-relaxed">
                "{{ ev.snippet || ev.text }}"
              </p>
              <span v-if="ev.page" class="text-[10px] text-text-muted">
                p.{{ ev.page }}{{ ev.paragraph ? `, ¶${ev.paragraph}` : '' }}
              </span>
            </div>
          </div>
        </div>

        <!-- ══ Review tab ══════════════════════════════════════════════════════ -->
        <div v-else-if="activeTab === 'review'" class="space-y-5">
          <h3 class="text-sm font-semibold text-text-primary">评审灵感</h3>

          <!-- Score sliders -->
          <div class="space-y-4">
            <div
              v-for="(label, key) in ({ novelty: '新颖度', feasibility: '可行性', impact: '影响力' } as Record<string,string>)"
              :key="key"
              class="space-y-1.5"
            >
              <div class="flex items-center justify-between text-xs">
                <label class="text-text-muted">{{ label }}</label>
                <span class="text-text-secondary font-semibold">{{ (reviewScores as any)[key] }}</span>
              </div>
              <input
                v-model.number="(reviewScores as any)[key]"
                type="range"
                min="1"
                max="10"
                step="0.5"
                class="w-full accent-[#fd267a]"
              />
            </div>
          </div>

          <!-- Decision buttons -->
          <div class="space-y-2">
            <label class="text-xs text-text-muted">决定</label>
            <div class="grid grid-cols-3 gap-2 mt-1">
              <button
                v-for="opt in ([
                  { key: 'approve', label: '✅ 通过', active: 'bg-green-500/15 border-green-500/40 text-green-400' },
                  { key: 'revise', label: '📝 修订', active: 'bg-yellow-500/15 border-yellow-500/40 text-yellow-400' },
                  { key: 'reject', label: '❌ 拒绝', active: 'bg-red-500/15 border-red-500/40 text-red-400' },
                ] as const)"
                :key="opt.key"
                class="py-2.5 rounded-xl border text-xs font-medium cursor-pointer transition-colors"
                :class="reviewAction === opt.key
                  ? opt.active
                  : 'bg-transparent border-border text-text-muted active:bg-bg-elevated'"
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
              class="w-full px-3 py-2.5 text-sm rounded-xl border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light resize-none"
              placeholder="输入你的评审意见..."
            />
          </div>

          <!-- Submit -->
          <button
            class="w-full py-3.5 rounded-xl text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
            :class="reviewSuccess ? 'bg-green-500' : 'bg-gradient-to-r from-[#fd267a] to-[#ff6036]'"
            :disabled="submittingReview"
            @click="submitReview"
          >
            {{ reviewSuccess ? '✅ 评审已提交' : submittingReview ? '提交中...' : '提交评审' }}
          </button>
        </div>

        <!-- ══ Plan tab ════════════════════════════════════════════════════════ -->
        <div v-else-if="activeTab === 'plan'" class="space-y-4">
          <div v-if="!plan" class="flex flex-col items-center justify-center py-12 gap-4 text-center">
            <p class="text-sm text-text-muted">尚未生成实验计划</p>
            <button
              class="px-6 py-3 rounded-xl bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="creatingPlan"
              @click="handleCreatePlan"
            >
              {{ creatingPlan ? '生成中...' : '📐 生成实验计划' }}
            </button>
          </div>

          <template v-else>
            <!-- Full plan -->
            <div v-if="plan.full_plan" class="bg-bg-card border border-border rounded-xl p-4">
              <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">完整计划</h4>
              <p class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
                {{ plan.full_plan }}
              </p>
            </div>

            <!-- Milestones -->
            <div v-if="plan.milestones?.length" class="bg-bg-card border border-border rounded-xl p-4">
              <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">里程碑</h4>
              <div
                v-for="(m, i) in plan.milestones"
                :key="i"
                class="flex items-center gap-2 py-1.5"
              >
                <span class="text-base">
                  {{ m.status === 'completed' ? '✅' : m.status === 'in_progress' ? '🔄' : '⏳' }}
                </span>
                <span class="text-sm text-text-secondary">{{ m.name }}</span>
              </div>
            </div>

            <!-- Details grid -->
            <div class="grid grid-cols-1 gap-3">
              <div v-if="plan.datasets" class="bg-bg-card border border-border rounded-xl p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">数据集</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.datasets }}</p>
              </div>
              <div v-if="plan.metrics" class="bg-bg-card border border-border rounded-xl p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">评估指标</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.metrics }}</p>
              </div>
              <div v-if="plan.timeline" class="bg-bg-card border border-border rounded-xl p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">时间线</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.timeline }}</p>
              </div>
              <div v-if="plan.cost" class="bg-bg-card border border-border rounded-xl p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">成本估算</h4>
                <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ plan.cost }}</p>
              </div>
            </div>
          </template>
        </div>

        <!-- ══ History tab ══════════════════════════════════════════════════════ -->
        <div v-else-if="activeTab === 'history'" class="space-y-4">
          <h3 class="text-sm font-semibold text-text-primary">修订历史</h3>

          <div
            v-if="!candidate.revision_history?.length"
            class="text-sm text-text-muted bg-bg-card border border-border rounded-xl p-4"
          >
            暂无修订记录。
          </div>

          <div
            v-for="(entry, i) in candidate.revision_history"
            :key="i"
            class="bg-bg-card border border-border rounded-xl p-4 space-y-2"
          >
            <div class="flex items-center gap-2 text-xs text-text-muted flex-wrap">
              <span>{{ entry.timestamp }}</span>
              <span
                v-if="entry.reviewer_role"
                class="px-1.5 py-0.5 rounded bg-bg-elevated border border-border"
              >
                {{ entry.reviewer_role }}
              </span>
              <span
                v-if="entry.verdict"
                class="px-1.5 py-0.5 rounded"
                :class="entry.verdict === 'approved' ? 'bg-green-500/15 text-green-400' : entry.verdict === 'rejected' ? 'bg-red-500/15 text-red-400' : 'bg-yellow-500/15 text-yellow-400'"
              >
                {{ entry.verdict }}
              </span>
            </div>
            <p v-if="entry.summary" class="text-sm text-text-secondary leading-relaxed">
              {{ entry.summary }}
            </p>
            <p
              v-else-if="entry.content_diff"
              class="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed"
            >
              {{ entry.content_diff }}
            </p>
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
