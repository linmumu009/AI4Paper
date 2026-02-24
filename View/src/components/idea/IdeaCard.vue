<script setup lang="ts">
import { computed } from 'vue'
import type { IdeaCandidate } from '../../types/paper'

const props = defineProps<{
  candidate: IdeaCandidate
  animClass?: string
}>()

const emit = defineEmits<{
  collect: [id: number]
  discard: [id: number]
}>()

const statusLabel: Record<string, string> = {
  draft: '草稿',
  review: '评审中',
  approved: '已通过',
  archived: '已归档',
  implemented: '已落地',
}

const statusColor: Record<string, string> = {
  draft: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  review: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  approved: 'bg-green-500/15 text-green-400 border-green-500/30',
  archived: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  implemented: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

const overallScore = computed(() => {
  const s = props.candidate.scores
  if (!s) return null
  return s.overall ?? null
})

const scoreColor = computed(() => {
  const v = overallScore.value
  if (v === null) return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
  if (v >= 8) return { border: 'border-tag-score-high', text: 'text-tag-score-high' }
  if (v >= 6) return { border: 'border-tag-score-mid', text: 'text-tag-score-mid' }
  return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
})

const atomCount = computed(() => props.candidate.input_atom_ids?.length ?? 0)

const strategyLabel: Record<string, string> = {
  transfer: '迁移',
  migration: '迁移',
  stitch: '缝合',
  stitching: '缝合',
  counterfactual: '反事实',
  patch: '修补',
  patching: '修补',
  resource_constrained: '资源约束',
  resource_constraint: '资源约束',
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
  } catch {
    return dateStr
  }
}
</script>

<template>
  <div
    class="card-bg relative w-full h-full rounded-2xl overflow-hidden select-none flex flex-col"
    :class="animClass"
  >
    <!-- Scrollable content area -->
    <div class="relative z-10 flex-1 overflow-y-auto px-5 pt-4 pb-5 space-y-4 scrollbar-thin card-body">
      <!-- === Header: strategy badge + score === -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span v-if="candidate.strategy" class="strategy-badge">
            {{ strategyLabel[candidate.strategy] || candidate.strategy }}
          </span>
          <span
            v-if="candidate.status"
            class="text-[10px] px-2 py-0.5 rounded-full border"
            :class="statusColor[candidate.status] || 'bg-bg-elevated text-text-muted border-border'"
          >
            {{ statusLabel[candidate.status] || candidate.status }}
          </span>
        </div>
        <div
          v-if="overallScore !== null"
          class="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2"
          :class="scoreColor.border + ' ' + scoreColor.text"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ overallScore.toFixed(1) }}
        </div>
      </div>

      <!-- === 标题区 === -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">
          {{ candidate.title }}
        </h2>
      </div>

      <!-- === 🎯 研究目标 === -->
      <div v-if="candidate.goal" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🎯 研究目标</h3>
        <p class="text-sm card-text">
          {{ candidate.goal }}
        </p>
      </div>

      <!-- === ⚙️ 机制方法 === -->
      <div v-if="candidate.mechanism" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">⚙️ 机制方法</h3>
        <p class="text-sm card-text">
          {{ candidate.mechanism }}
        </p>
      </div>

      <!-- === ⚠️ 风险与挑战 === -->
      <div v-if="candidate.risks" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">⚠️ 风险与挑战</h3>
        <p class="text-sm card-text">
          {{ candidate.risks }}
        </p>
      </div>

      <!-- === 📊 评分维度 === -->
      <div v-if="candidate.scores" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📊 评分维度</h3>
        <div class="grid grid-cols-2 gap-2">
          <div v-if="candidate.scores.novelty != null" class="flex items-center justify-between text-xs">
            <span class="text-text-muted">新颖性</span>
            <span class="text-text-secondary font-semibold">{{ candidate.scores.novelty.toFixed(1) }}</span>
          </div>
          <div v-if="candidate.scores.feasibility != null" class="flex items-center justify-between text-xs">
            <span class="text-text-muted">可行性</span>
            <span class="text-text-secondary font-semibold">{{ candidate.scores.feasibility.toFixed(1) }}</span>
          </div>
          <div v-if="candidate.scores.impact != null" class="flex items-center justify-between text-xs">
            <span class="text-text-muted">影响力</span>
            <span class="text-text-secondary font-semibold">{{ candidate.scores.impact.toFixed(1) }}</span>
          </div>
          <div v-if="candidate.scores.consistency != null" class="flex items-center justify-between text-xs">
            <span class="text-text-muted">一致性</span>
            <span class="text-text-secondary font-semibold">{{ candidate.scores.consistency.toFixed(1) }}</span>
          </div>
        </div>
      </div>

      <!-- === 📝 证据来源 === -->
      <div v-if="candidate.evidence?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📝 证据来源</h3>
        <div class="space-y-1.5">
          <div
            v-for="(ev, idx) in candidate.evidence.slice(0, 3)"
            :key="idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-gold mt-1.5"></span>
            <div class="flex-1 min-w-0">
              <p class="text-xs text-text-muted">{{ ev.location }}</p>
              <p class="text-sm card-text">{{ ev.text }}</p>
            </div>
          </div>
          <p v-if="candidate.evidence.length > 3" class="text-xs text-text-muted">
            +{{ candidate.evidence.length - 3 }} 条更多证据
          </p>
        </div>
      </div>

      <!-- === 🏷️ 标签 === -->
      <div v-if="candidate.tags?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🏷️ 标签</h3>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="tag in candidate.tags"
            :key="tag"
            class="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted"
          >
            {{ tag }}
          </span>
        </div>
      </div>

      <!-- === Footer: atom count + created time === -->
      <div class="flex items-center justify-between pt-2 border-t border-border">
        <span class="text-xs text-text-muted flex items-center gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>
          </svg>
          {{ atomCount }} 原子
        </span>
        <span class="text-xs text-text-muted">
          {{ formatDate(candidate.created_at) }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Card background — uses theme variable */
.card-bg {
  background: var(--color-bg-card);
}

/* Strategy badge — similar to institution badge */
.strategy-badge {
  display: inline-block;
  padding: 4px 14px;
  border-radius: 9999px;
  font-size: 18px;
  font-weight: 300;
  letter-spacing: 0.06em;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", Georgia, serif;
  font-style: italic;
  color: #fff;
  background: linear-gradient(135deg, var(--color-gradient-start) 0%, var(--color-gradient-end) 100%);
}

/* Body text: uses theme-aware secondary color */
.card-text {
  color: var(--color-text-secondary);
  line-height: 1.6;
}

/* Scrollable area inherits the same text defaults */
.card-body {
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.scrollbar-thin {
  scrollbar-width: thin;
  scrollbar-color: var(--color-border-light) transparent;
}
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: var(--color-border-light);
  border-radius: 2px;
}
</style>
