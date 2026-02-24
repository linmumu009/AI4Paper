<script setup lang="ts">
import { ref, computed } from 'vue'
import type { IdeaCandidate } from '../types/paper'

const props = defineProps<{
  candidate: IdeaCandidate
}>()

const emit = defineEmits<{
  (e: 'swipe-left'): void
  (e: 'swipe-right'): void
  (e: 'swipe-up'): void
}>()

// Touch state
const startX = ref(0)
const startY = ref(0)
const deltaX = ref(0)
const deltaY = ref(0)
const isDragging = ref(false)
const flyAway = ref<'' | 'left' | 'right' | 'up'>('')

const SWIPE_THRESHOLD = 80
const SWIPE_UP_THRESHOLD = 100

const cardStyle = computed(() => {
  if (flyAway.value) return {}
  if (!isDragging.value) return { transform: 'translateX(0) rotate(0deg)', transition: 'transform 0.3s ease' }
  const rotate = deltaX.value * 0.08
  return {
    transform: `translateX(${deltaX.value}px) translateY(${Math.min(deltaY.value, 0)}px) rotate(${rotate}deg)`,
    transition: 'none',
  }
})

const likeOpacity = computed(() => {
  if (!isDragging.value || deltaX.value <= 0) return 0
  return Math.min(deltaX.value / SWIPE_THRESHOLD, 1)
})

const nopeOpacity = computed(() => {
  if (!isDragging.value || deltaX.value >= 0) return 0
  return Math.min(Math.abs(deltaX.value) / SWIPE_THRESHOLD, 1)
})

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  startX.value = touch.clientX
  startY.value = touch.clientY
  deltaX.value = 0
  deltaY.value = 0
  isDragging.value = true
}

function onTouchMove(e: TouchEvent) {
  if (!isDragging.value) return
  const touch = e.touches[0]
  deltaX.value = touch.clientX - startX.value
  deltaY.value = touch.clientY - startY.value
  if (Math.abs(deltaX.value) > 10 || deltaY.value < -10) {
    e.preventDefault()
  }
}

function onTouchEnd() {
  if (!isDragging.value) return
  isDragging.value = false
  if (deltaX.value > SWIPE_THRESHOLD) {
    flyAway.value = 'right'
    setTimeout(() => emit('swipe-right'), 350)
  } else if (deltaX.value < -SWIPE_THRESHOLD) {
    flyAway.value = 'left'
    setTimeout(() => emit('swipe-left'), 350)
  } else if (deltaY.value < -SWIPE_UP_THRESHOLD) {
    flyAway.value = 'up'
    setTimeout(() => emit('swipe-up'), 350)
  } else {
    deltaX.value = 0
    deltaY.value = 0
  }
}

// Display helpers
const overallScore = computed(() => props.candidate.scores?.overall ?? null)

const scoreClass = computed(() => {
  const v = overallScore.value
  if (v === null) return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
  if (v >= 8) return { border: 'border-tag-score-high', text: 'text-tag-score-high' }
  if (v >= 6) return { border: 'border-tag-score-mid', text: 'text-tag-score-mid' }
  return { border: 'border-tag-score-low', text: 'text-tag-score-low' }
})

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
</script>

<template>
  <div
    class="absolute inset-0 rounded-2xl overflow-hidden bg-bg-card shadow-xl select-none flex flex-col"
    :class="flyAway === 'left' ? 'card-swipe-left' : flyAway === 'right' ? 'card-swipe-right' : flyAway === 'up' ? 'card-swipe-up' : (isDragging ? '' : 'card-enter')"
    :style="cardStyle"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend.passive="onTouchEnd"
  >
    <!-- 感兴趣 overlay (right swipe) -->
    <div
      class="absolute top-8 left-5 z-30 px-4 py-1.5 rounded-lg border-[3px] border-tinder-green text-tinder-green text-2xl font-extrabold rotate-[-15deg] pointer-events-none"
      :style="{ opacity: likeOpacity }"
    >
      感兴趣
    </div>

    <!-- 跳过 overlay (left swipe) -->
    <div
      class="absolute top-8 right-5 z-30 px-4 py-1.5 rounded-lg border-[3px] border-tinder-pink text-tinder-pink text-2xl font-extrabold rotate-[15deg] pointer-events-none"
      :style="{ opacity: nopeOpacity }"
    >
      跳过
    </div>

    <!-- Scrollable content -->
    <div class="flex-1 overflow-y-auto px-5 pt-5 pb-4 space-y-4 z-10" style="scrollbar-width: thin;">

      <!-- Header: strategy badge + status + score -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 flex-wrap">
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
          class="shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-xs font-bold border-2"
          :class="scoreClass.border + ' ' + scoreClass.text"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ overallScore.toFixed(1) }}
        </div>
      </div>

      <!-- Title -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">{{ candidate.title }}</h2>
      </div>

      <!-- 研究目标 -->
      <div v-if="candidate.goal" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🎯 研究目标</h3>
        <p class="text-sm text-text-secondary leading-relaxed">{{ candidate.goal }}</p>
      </div>

      <!-- 机制方法 -->
      <div v-if="candidate.mechanism" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">⚙️ 机制方法</h3>
        <p class="text-sm text-text-secondary leading-relaxed">{{ candidate.mechanism }}</p>
      </div>

      <!-- 风险与挑战 -->
      <div v-if="candidate.risks" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">⚠️ 风险与挑战</h3>
        <p class="text-sm text-text-secondary leading-relaxed">{{ candidate.risks }}</p>
      </div>

      <!-- 评分维度 -->
      <div v-if="candidate.scores" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📊 评分维度</h3>
        <div class="grid grid-cols-2 gap-x-4 gap-y-1">
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

      <!-- 标签 -->
      <div v-if="candidate.tags?.length" class="flex flex-wrap gap-1.5">
        <span
          v-for="tag in candidate.tags"
          :key="tag"
          class="text-[10px] px-2 py-0.5 rounded-full bg-bg-elevated border border-border text-text-muted"
        >
          {{ tag }}
        </span>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-between pt-2 border-t border-border">
        <span class="text-xs text-text-muted flex items-center gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
          {{ candidate.input_atom_ids?.length ?? 0 }} 原子
        </span>
        <span class="text-xs text-text-muted">上滑查看详情</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.strategy-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 9999px;
  font-size: 14px;
  font-weight: 300;
  letter-spacing: 0.06em;
  font-family: "Noto Serif SC", "Source Han Serif SC", "STSong", "SimSun", Georgia, serif;
  font-style: italic;
  color: #fff;
  background: linear-gradient(135deg, var(--color-gradient-start) 0%, var(--color-gradient-end) 100%);
}
</style>
