<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import {
  fetchIdeaCandidate,
  fetchIdeaAtom,
  fetchIdeaPlan,
  reviewIdeaCandidate,
  createIdeaFeedback,
  createIdeaPlan,
  createIdeaExemplar,
  fetchGeneratePlanStream,
} from '../../api'

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
import type { IdeaCandidate, IdeaAtom, IdeaPlan } from '../../types/paper'

const props = defineProps<{
  candidateId: number
}>()

const emit = defineEmits<{
  close: []
  openPaper: [paperId: string]
}>()

const candidate = ref<IdeaCandidate | null>(null)
const atoms = ref<IdeaAtom[]>([])
const plan = ref<IdeaPlan | null>(null)
const loading = ref(true)
const error = ref('')

// 评审状态
const reviewAction = ref<'approve' | 'reject' | 'revise'>('approve')
const reviewFeedback = ref('')
const reviewScores = ref({ novelty: 7, feasibility: 7, impact: 7 })
const submittingReview = ref(false)
const reviewSuccess = ref(false)
const reviewError = ref('')

// 标签页
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

const atomTypeLabel: Record<string, string> = {
  claim: '论断', method: '方法', setup: '设置', limitation: '局限', tag: '标签',
}
const atomTypeIcon: Record<string, string> = {
  claim: '💬', method: '⚙️', setup: '📊', limitation: '⚠️', tag: '🏷️',
}

// 评审决定标签
const verdictLabel: Record<string, string> = {
  approve: '✅ 通过', approved: '✅ 通过',
  reject: '❌ 拒绝', rejected: '❌ 拒绝',
  revise: '📝 修订',
}
const verdictColor: Record<string, string> = {
  approve: 'text-green-400', approved: 'text-green-400',
  reject: 'text-red-400', rejected: 'text-red-400',
  revise: 'text-yellow-400',
}

// 最新评审意见（来自 revision_history，取最后一条有 feedback/summary 的记录）
const latestReview = computed(() => {
  if (!candidate.value?.revision_history?.length) return null
  const history = [...candidate.value.revision_history].reverse()
  return history.find((e: any) => (e.type === 'manual_review' || e.type === 'review') && (e.feedback || e.summary)) ?? null
})

// 全部评审记录（manual_review + AI review，倒序排列）
const reviewHistory = computed(() => {
  if (!candidate.value?.revision_history?.length) return []
  return [...candidate.value.revision_history]
    .filter((e: any) => e.type === 'manual_review' || e.type === 'review')
    .reverse()
})

function formatReviewTime(ts: string | undefined): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleString('zh-CN', {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return ts
  }
}

// 来源论文去重
const sourcePapers = computed(() => {
  const seen = new Set<string>()
  const result: { paper_id: string; snippet: string }[] = []
  for (const atom of atoms.value) {
    if (!seen.has(atom.paper_id)) {
      seen.add(atom.paper_id)
      result.push({ paper_id: atom.paper_id, snippet: atom.content.slice(0, 80) })
    }
  }
  return result
})

async function loadCandidate() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaCandidate(props.candidateId)
    candidate.value = res.candidate

    if (res.candidate.input_atom_ids?.length) {
      const atomPromises = res.candidate.input_atom_ids.slice(0, 20).map((aid) =>
        fetchIdeaAtom(aid).then((r) => r.atom).catch(() => null),
      )
      const loaded = await Promise.all(atomPromises)
      atoms.value = loaded.filter((a): a is IdeaAtom => a !== null)
    }

    try {
      const planRes = await fetchIdeaPlan(props.candidateId)
      plan.value = planRes.plan
    } catch {}
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadCandidate()
  createIdeaFeedback({ candidate_id: props.candidateId, action: 'view' }).catch(() => {})
})
watch(() => props.candidateId, () => {
  activeTab.value = 'overview'
  loadCandidate()
})

// 评审
async function submitReview() {
  submittingReview.value = true
  reviewSuccess.value = false
  reviewError.value = ''
  try {
    await reviewIdeaCandidate(props.candidateId, {
      action: reviewAction.value,
      feedback: reviewFeedback.value || undefined,
      scores: reviewScores.value,
    })
    await loadCandidate()
    reviewFeedback.value = ''
    reviewSuccess.value = true
    // 3 秒后自动消失
    setTimeout(() => { reviewSuccess.value = false }, 3000)
  } catch (e: any) {
    reviewError.value = e?.response?.data?.detail || '评审提交失败，请稍后重试'
  } finally {
    submittingReview.value = false
  }
}

// 生成计划（SSE 流式 + 保存）
const creatingPlan = ref(false)
const planStreamText = ref('')
let planAbortController: AbortController | null = null

async function handleCreatePlan() {
  creatingPlan.value = true
  planStreamText.value = ''
  activeTab.value = 'plan'
  planAbortController = new AbortController()
  try {
    // 第一步：通过 LLM 流式生成计划文本
    await fetchGeneratePlanStream(
      props.candidateId,
      (chunk) => { planStreamText.value += chunk },
      planAbortController.signal,
    )
    // 第二步：保存生成的计划
    const res = await createIdeaPlan(props.candidateId, {
      full_plan: planStreamText.value,
    } as any)
    plan.value = res.plan
    planStreamText.value = ''
  } catch (e: any) {
    if ((e as any).name === 'AbortError') return
    error.value = e?.message || e?.response?.data?.detail || '创建计划失败'
  } finally {
    creatingPlan.value = false
    planAbortController = null
  }
}

// 标记为范例
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
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- 顶部栏 -->
    <div class="shrink-0 flex items-center gap-3 px-4 sm:px-6 py-3 border-b border-border bg-bg">
      <button
        class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors flex items-center gap-1.5"
        @click="emit('close')"
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

    <!-- 加载中 -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">🧪</span>
        </div>
        <p class="text-sm text-text-muted">加载中...</p>
      </div>
    </div>

    <!-- 错误 -->
    <div v-else-if="error && !candidate" class="flex-1 flex items-center justify-center">
      <div class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>
    </div>

    <!-- 详情内容 -->
    <template v-else-if="candidate">
      <!-- 标签栏 -->
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

      <!-- 可滚动内容区 -->
      <div class="flex-1 overflow-y-auto p-3 sm:p-6">

        <!-- ===== 概览 ===== -->
        <div v-if="activeTab === 'overview'" class="max-w-3xl mx-auto space-y-6 pb-24">
          <!-- 评分卡 -->
          <div v-if="candidate.scores" class="grid grid-cols-3 gap-3">
            <div
              v-for="(label, key) in { novelty: '新颖度', feasibility: '可行性', impact: '影响力' }"
              :key="key"
              class="rounded-lg bg-bg-card border border-border p-3 text-center"
            >
              <div
                class="text-2xl font-bold"
                :class="(candidate.scores as any)[key] >= 7 ? 'text-green-400' : (candidate.scores as any)[key] >= 5 ? 'text-yellow-400' : 'text-red-400'"
              >
                {{ (candidate.scores as any)[key]?.toFixed(1) ?? '—' }}
              </div>
              <div class="text-[10px] text-text-muted mt-1">{{ label }}</div>
            </div>
          </div>

          <!-- 目标 -->
          <div>
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">🎯 目标与适用场景</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4">
              {{ candidate.goal }}
            </p>
          </div>

          <!-- 机制 -->
          <div v-if="candidate.mechanism">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">⚙️ 核心机制</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4 whitespace-pre-wrap">
              {{ candidate.mechanism }}
            </p>
          </div>

          <!-- 风险 -->
          <div v-if="candidate.risks">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">⚠️ 风险与假设</h3>
            <p class="text-sm text-text-secondary leading-relaxed bg-bg-card border border-border rounded-lg p-4 whitespace-pre-wrap">
              {{ candidate.risks }}
            </p>
          </div>

          <!-- 来源论文 -->
          <div v-if="sourcePapers.length > 0">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">📄 来源论文</h3>
            <div class="space-y-2">
              <button
                v-for="src in sourcePapers"
                :key="src.paper_id"
                class="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg bg-bg-card border border-border text-left cursor-pointer hover:border-border-light hover:bg-bg-hover transition-colors group"
                @click="emit('openPaper', src.paper_id)"
              >
                <span class="text-base shrink-0">📄</span>
                <div class="flex-1 min-w-0">
                  <div class="text-xs font-semibold text-text-primary truncate">{{ src.paper_id }}</div>
                  <div class="text-[11px] text-text-muted truncate mt-0.5">{{ src.snippet }}</div>
                </div>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  class="w-3.5 h-3.5 shrink-0 text-text-muted group-hover:text-text-secondary transition-colors"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"
                ><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>

          <!-- 标签 -->
          <div v-if="candidate.tags?.length">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">🏷️ 标签</h3>
            <div class="flex flex-wrap gap-2">
              <span
                v-for="t in candidate.tags"
                :key="t"
                class="text-xs px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-muted"
              >{{ t }}</span>
            </div>
          </div>

          <!-- 最新评审意见 -->
          <div v-if="latestReview">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">🔍 最新评审意见</h3>
            <div class="bg-bg-card border border-border rounded-lg p-4 space-y-2">
              <!-- 评审决定 + 分数 -->
              <div class="flex items-center justify-between flex-wrap gap-2">
                <span
                  v-if="latestReview.verdict || latestReview.action"
                  class="text-xs font-semibold"
                  :class="verdictColor[(latestReview.verdict || latestReview.action) as string] || 'text-text-muted'"
                >
                  {{ verdictLabel[(latestReview.verdict || latestReview.action) as string] || (latestReview.verdict || latestReview.action) }}
                </span>
                <!-- 评审分数（若有） -->
                <div v-if="latestReview.scores && Object.keys(latestReview.scores).length" class="flex items-center gap-3">
                  <span
                    v-for="(scoreVal, scoreKey) in { novelty: '新颖', feasibility: '可行', impact: '影响' }"
                    :key="scoreKey"
                    class="text-[10px] text-text-muted flex items-center gap-1"
                  >
                    <span class="text-text-secondary font-semibold">{{ (latestReview.scores as any)[scoreKey] ?? '—' }}</span>
                    {{ scoreVal }}
                  </span>
                </div>
                <span v-if="latestReview.timestamp" class="text-[10px] text-text-muted">
                  {{ new Date(latestReview.timestamp).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }}
                </span>
              </div>
              <!-- 反馈文本 -->
              <p v-if="latestReview.feedback" class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap border-t border-border pt-2 mt-1">
                {{ latestReview.feedback }}
              </p>
              <p v-else-if="latestReview.summary" class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap border-t border-border pt-2 mt-1">
                {{ latestReview.summary }}
              </p>
            </div>
          </div>

          <!-- 操作 -->
          <div class="flex items-center gap-2 pt-4 border-t border-border">
            <button
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-green-400 hover:border-green-500/30 hover:bg-green-500/10 transition-colors"
              @click="markAsExemplar"
            >⭐ 标记为范例</button>
            <button
              v-if="!plan && !creatingPlan"
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-blue-400 hover:border-blue-500/30 hover:bg-blue-500/10 transition-colors"
              @click="handleCreatePlan"
            >📐 生成实验计划</button>
            <button
              v-else-if="creatingPlan"
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-not-allowed opacity-60 flex items-center gap-1.5"
              disabled
            >
              <div class="w-3 h-3 rounded-full border-2 border-transparent border-t-[#fd267a] animate-spin" />
              生成中...
            </button>
            <button
              v-else
              class="text-xs px-4 py-2 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-blue-400 hover:border-blue-500/30 hover:bg-blue-500/10 transition-colors"
              @click="activeTab = 'plan'"
            >📐 查看计划</button>
          </div>
        </div>

        <!-- ===== 证据链 ===== -->
        <div v-else-if="activeTab === 'evidence'" class="max-w-3xl mx-auto space-y-4 pb-24">
          <h3 class="text-sm font-semibold text-text-primary mb-3">组合来源（{{ atoms.length }} 个原子）</h3>
          <div
            v-if="atoms.length === 0"
            class="text-sm text-text-muted bg-bg-card border border-border rounded-lg p-4"
          >暂无关联的灵感原子。</div>
          <div
            v-for="atom in atoms"
            :key="atom.id"
            class="bg-bg-card border border-border rounded-lg p-4 space-y-2"
          >
            <div class="flex items-center gap-2">
              <span class="text-sm">{{ atomTypeIcon[atom.atom_type] || '📄' }}</span>
              <span class="text-xs font-semibold text-text-primary">{{ atomTypeLabel[atom.atom_type] || atom.atom_type }}</span>
              <button
                class="text-[10px] text-text-muted hover:text-tinder-blue underline underline-offset-2 cursor-pointer bg-transparent border-none"
                @click="emit('openPaper', atom.paper_id)"
              >{{ atom.paper_id }}</button>
              <span v-if="atom.section" class="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">{{ atom.section }}</span>
            </div>
            <p class="text-sm text-text-secondary leading-relaxed">{{ atom.content }}</p>
            <div v-if="atom.evidence?.length" class="space-y-1 pl-3 border-l-2 border-border">
              <div v-for="(ev, i) in atom.evidence" :key="i" class="text-xs text-text-muted italic leading-relaxed">
                "{{ (ev as any).snippet || (ev as any).text }}"
              </div>
            </div>
            <div v-if="atom.tags?.length" class="flex flex-wrap gap-1">
              <span
                v-for="t in atom.tags"
                :key="t"
                class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted"
              >{{ t }}</span>
            </div>
          </div>

          <!-- 灵感级证据 -->
          <div v-if="candidate.evidence?.length" class="mt-6">
            <h3 class="text-sm font-semibold text-text-primary mb-3">灵感级证据</h3>
            <div
              v-for="(ev, i) in candidate.evidence"
              :key="i"
              class="bg-bg-card border border-border rounded-lg p-3 mb-2"
            >
              <p class="text-xs text-text-secondary italic leading-relaxed">"{{ (ev as any).snippet || (ev as any).text }}"</p>
            </div>
          </div>
        </div>

        <!-- ===== 评审 ===== -->
        <div v-else-if="activeTab === 'review'" class="max-w-3xl mx-auto space-y-6 pb-24">
          <h3 class="text-sm font-semibold text-text-primary">评审灵感</h3>
          <div class="grid grid-cols-3 gap-4">
            <div
              v-for="(label, key) in { novelty: '新颖度', feasibility: '可行性', impact: '影响力' }"
              :key="key"
              class="space-y-1"
            >
              <label class="text-xs text-text-muted">{{ label }}</label>
              <input
                v-model.number="(reviewScores as any)[key]"
                type="range" min="1" max="10" step="0.5"
                class="w-full accent-[#fd267a]"
              />
              <div class="text-center text-xs font-semibold text-text-secondary">{{ (reviewScores as any)[key] }}</div>
            </div>
          </div>
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
              >{{ opt.label }}</button>
            </div>
          </div>
          <div class="space-y-2">
            <label class="text-xs text-text-muted">反馈意见（可选）</label>
            <textarea
              v-model="reviewFeedback"
              rows="4"
              class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light resize-none transition-colors"
              placeholder="输入你的评审意见..."
            />
          </div>
          <div class="flex items-center gap-3 flex-wrap">
            <button
              class="px-6 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50"
              :disabled="submittingReview"
              @click="submitReview"
            >{{ submittingReview ? '提交中...' : '提交评审' }}</button>

            <!-- 成功提示 -->
            <Transition name="fade-msg">
              <span
                v-if="reviewSuccess"
                class="text-xs px-3 py-1.5 rounded-full bg-green-500/15 border border-green-500/30 text-green-400 flex items-center gap-1.5"
              >
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                评审已提交
              </span>
            </Transition>
          </div>

          <!-- 错误提示 -->
          <Transition name="fade-msg">
            <div
              v-if="reviewError"
              class="flex items-center justify-between text-xs px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400"
            >
              <span>{{ reviewError }}</span>
              <button class="ml-2 text-red-400 hover:text-red-300 bg-transparent border-none cursor-pointer" @click="reviewError = ''">✕</button>
            </div>
          </Transition>

          <!-- ===== 评审记录 ===== -->
          <div class="pt-4 border-t border-border space-y-3">
            <h3 class="text-xs font-semibold text-text-muted uppercase tracking-wider flex items-center gap-2">
              📜 评审记录
              <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-bg-elevated border border-border font-normal normal-case">
                {{ reviewHistory.length }} 条
              </span>
            </h3>

            <!-- 无记录 -->
            <div
              v-if="reviewHistory.length === 0"
              class="text-xs text-text-muted bg-bg-card border border-border rounded-lg px-4 py-3"
            >
              暂无评审记录，提交评审后将在此显示。
            </div>

            <!-- 记录列表 -->
            <div
              v-for="(entry, idx) in reviewHistory"
              :key="idx"
              class="bg-bg-card border border-border rounded-lg p-4 space-y-2"
            >
              <!-- 顶部：决定 + 类型 + 时间 -->
              <div class="flex items-center justify-between flex-wrap gap-2">
                <div class="flex items-center gap-2">
                  <span
                    class="text-xs font-semibold"
                    :class="verdictColor[(entry as any).verdict || (entry as any).action] || 'text-text-muted'"
                  >
                    {{ verdictLabel[(entry as any).verdict || (entry as any).action] || (entry as any).verdict || (entry as any).action || '—' }}
                  </span>
                  <span class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted border border-border">
                    {{ (entry as any).type === 'manual_review' ? '人工评审' : 'AI 评审' }}
                  </span>
                </div>
                <span class="text-[10px] text-text-muted">
                  {{ formatReviewTime((entry as any).timestamp || (entry as any).created_at) }}
                </span>
              </div>

              <!-- 分数行 -->
              <div
                v-if="(entry as any).scores && Object.keys((entry as any).scores).length"
                class="flex items-center gap-4"
              >
                <div
                  v-for="(scoreLabel, scoreKey) in { novelty: '新颖', feasibility: '可行', impact: '影响', overall: '综合' }"
                  :key="scoreKey"
                  class="flex items-center gap-1 text-[10px] text-text-muted"
                >
                  <span
                    class="font-semibold text-xs"
                    :class="((entry as any).scores[scoreKey] ?? 0) >= 7 ? 'text-green-400' : ((entry as any).scores[scoreKey] ?? 0) >= 5 ? 'text-yellow-400' : 'text-red-400'"
                  >
                    {{ (entry as any).scores[scoreKey] != null ? Number((entry as any).scores[scoreKey]).toFixed(1) : '—' }}
                  </span>
                  {{ scoreLabel }}
                </div>
              </div>

              <!-- 反馈/摘要文字 -->
              <p
                v-if="(entry as any).feedback || (entry as any).summary"
                class="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap border-t border-border pt-2"
              >{{ (entry as any).feedback || (entry as any).summary }}</p>
            </div>
          </div>
        </div>

        <!-- ===== 计划 ===== -->
        <div v-else-if="activeTab === 'plan'" class="max-w-3xl mx-auto space-y-4 pb-24">
          <!-- 流式生成中 -->
          <div v-if="creatingPlan" class="bg-bg-card border border-border rounded-lg p-4 space-y-3">
            <div class="flex items-center gap-2 text-xs text-text-muted">
              <div class="w-3.5 h-3.5 rounded-full border-2 border-transparent border-t-[#fd267a] animate-spin shrink-0" />
              <span>正在用 AI 生成实验计划...</span>
            </div>
            <div
              v-if="planStreamText"
              class="prose-idea text-sm leading-relaxed"
              v-html="md.render(planStreamText)"
            />
          </div>
          <div v-else-if="!plan" class="text-center py-12">
            <p class="text-sm text-text-muted mb-4">尚未生成实验计划</p>
            <button
              class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="handleCreatePlan"
            >📐 生成实验计划</button>
          </div>
          <template v-else>
            <div v-if="plan.full_plan" class="bg-bg-card border border-border rounded-lg p-4">
              <div
                class="prose-idea text-sm leading-relaxed"
                v-html="md.render(plan.full_plan)"
              />
            </div>
            <div v-if="plan.milestones?.length" class="bg-bg-card border border-border rounded-lg p-4">
              <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">里程碑</h4>
              <div v-for="(m, i) in plan.milestones" :key="i" class="flex items-center gap-2 py-1">
                <span class="text-xs">{{ (m as any).status === 'completed' ? '✅' : (m as any).status === 'in_progress' ? '🔄' : '⏳' }}</span>
                <span class="text-sm text-text-secondary">{{ (m as any).name }}</span>
              </div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div v-if="plan.datasets" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">数据集</h4>
                <div class="prose-idea text-sm" v-html="md.render(plan.datasets)" />
              </div>
              <div v-if="plan.metrics" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">指标</h4>
                <div class="prose-idea text-sm" v-html="md.render(plan.metrics)" />
              </div>
              <div v-if="plan.timeline" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">时间线</h4>
                <div class="prose-idea text-sm" v-html="md.render(plan.timeline)" />
              </div>
              <div v-if="plan.cost" class="bg-bg-card border border-border rounded-lg p-4">
                <h4 class="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">成本</h4>
                <div class="prose-idea text-sm" v-html="md.render(plan.cost)" />
              </div>
            </div>
          </template>
        </div>

        <!-- ===== 修订历史 ===== -->
        <div v-else-if="activeTab === 'history'" class="max-w-3xl mx-auto space-y-4 pb-24">
          <h3 class="text-sm font-semibold text-text-primary">修订历史</h3>
          <div
            v-if="!candidate.revision_history?.length"
            class="text-sm text-text-muted bg-bg-card border border-border rounded-lg p-4"
          >暂无修订记录。</div>
          <div
            v-for="(entry, i) in candidate.revision_history"
            :key="i"
            class="bg-bg-card border border-border rounded-lg p-4 space-y-1"
          >
            <div class="flex items-center gap-2 text-xs text-text-muted">
              <span>{{ (entry as any).timestamp }}</span>
              <span v-if="(entry as any).reviewer_role" class="px-1.5 py-0.5 rounded bg-bg-elevated">{{ (entry as any).reviewer_role }}</span>
            </div>
            <p class="text-sm text-text-secondary whitespace-pre-wrap">{{ (entry as any).content_diff }}</p>
          </div>
        </div>

      </div>
    </template>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

/* 评审反馈消息淡入淡出 */
.fade-msg-enter-active,
.fade-msg-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.fade-msg-enter-from,
.fade-msg-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Markdown 渲染样式 */
.prose-idea :deep(h1) {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--color-border);
}
.prose-idea :deep(h2) {
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-top: 1.25rem;
  margin-bottom: 0.4rem;
}
.prose-idea :deep(h3) {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 1rem;
  margin-bottom: 0.35rem;
}
.prose-idea :deep(p) {
  color: var(--color-text-secondary);
  line-height: 1.7;
  margin-bottom: 0.6rem;
}
.prose-idea :deep(ul),
.prose-idea :deep(ol) {
  color: var(--color-text-secondary);
  padding-left: 1.4rem;
  margin-bottom: 0.6rem;
}
.prose-idea :deep(li) {
  margin-bottom: 0.2rem;
  line-height: 1.65;
}
.prose-idea :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 0.75rem;
  font-size: 0.8125rem;
}
.prose-idea :deep(th) {
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: 0.4rem 0.65rem;
  text-align: left;
  font-weight: 600;
  border: 1px solid var(--color-border);
}
.prose-idea :deep(td) {
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}
.prose-idea :deep(tr:nth-child(even)) {
  background: var(--color-bg-elevated);
}
.prose-idea :deep(strong) {
  color: var(--color-text-primary);
  font-weight: 600;
}
.prose-idea :deep(em) {
  color: var(--color-text-muted);
  font-style: italic;
}
.prose-idea :deep(code) {
  background: var(--color-bg-elevated);
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-size: 0.8125rem;
  color: var(--color-tinder-purple);
}
.prose-idea :deep(blockquote) {
  border-left: 3px solid var(--color-tinder-pink);
  padding-left: 0.9rem;
  color: var(--color-text-muted);
  font-style: italic;
  margin: 0.6rem 0;
}
.prose-idea :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: 1rem 0;
}
</style>
