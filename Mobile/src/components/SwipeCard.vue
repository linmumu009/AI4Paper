<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PaperSummary } from '../types/paper'

const props = defineProps<{
  paper: PaperSummary
}>()

const emit = defineEmits<{
  (e: 'swipe-left'): void
  (e: 'swipe-right'): void
  (e: 'swipe-up'): void
}>()

const cardEl = ref<HTMLElement | null>(null)

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

// Overlay opacity for like/nope indicators
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
  // Prevent page scroll while dragging card
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
    // Snap back
    deltaX.value = 0
    deltaY.value = 0
  }
}

function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}
</script>

<template>
  <div
    ref="cardEl"
    class="absolute inset-0 rounded-2xl overflow-hidden bg-bg-card shadow-xl select-none flex flex-col"
    :class="flyAway === 'left' ? 'card-swipe-left' : flyAway === 'right' ? 'card-swipe-right' : flyAway === 'up' ? 'card-swipe-up' : (isDragging ? '' : 'card-enter')"
    :style="cardStyle"
    @touchstart.passive="onTouchStart"
    @touchmove="onTouchMove"
    @touchend.passive="onTouchEnd"
  >
    <!-- LIKE overlay -->
    <div
      class="absolute top-8 left-5 z-30 px-4 py-1.5 rounded-lg border-[3px] border-tinder-green text-tinder-green text-2xl font-extrabold rotate-[-15deg] pointer-events-none"
      :style="{ opacity: likeOpacity }"
    >
      LIKE
    </div>

    <!-- NOPE overlay -->
    <div
      class="absolute top-8 right-5 z-30 px-4 py-1.5 rounded-lg border-[3px] border-tinder-pink text-tinder-pink text-2xl font-extrabold rotate-[15deg] pointer-events-none"
      :style="{ opacity: nopeOpacity }"
    >
      NOPE
    </div>

    <!-- Scrollable card content -->
    <div class="flex-1 overflow-y-auto px-5 pt-5 pb-5 space-y-4 z-10" style="scrollbar-width: thin;">

      <!-- Header: institution + score -->
      <div class="flex items-center justify-between">
        <span class="institution-badge">{{ paper.institution || '未知机构' }}</span>
        <div
          v-if="paper.relevance_score != null"
          class="w-11 h-11 rounded-full flex items-center justify-center text-xs font-bold border-2"
          :class="paper.relevance_score >= 0.7
            ? 'border-tag-score-high text-tag-score-high'
            : paper.relevance_score >= 0.4
              ? 'border-tag-score-mid text-tag-score-mid'
              : 'border-tag-score-low text-tag-score-low'"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ (paper.relevance_score * 100).toFixed(0) }}
        </div>
      </div>

      <!-- Title -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">{{ paper.short_title }}</h2>
        <p class="text-sm text-text-secondary mt-1.5">{{ paper['📖标题'] }}</p>
        <p class="text-xs text-text-muted mt-1 font-mono">{{ paper['🌐来源'] }}</p>
      </div>

      <!-- 文章简介 -->
      <div class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">文章简介</h3>
        <div class="text-sm text-text-secondary space-y-1 leading-relaxed">
          <p v-if="paper['🛎️文章简介']?.['🔸研究问题']">
            <span class="text-tinder-pink font-medium">研究问题：</span>{{ paper['🛎️文章简介']['🔸研究问题'] }}
          </p>
          <p v-if="paper['🛎️文章简介']?.['🔸主要贡献']">
            <span class="text-tinder-pink font-medium">主要贡献：</span>{{ paper['🛎️文章简介']['🔸主要贡献'] }}
          </p>
        </div>
      </div>

      <!-- 重点思路 -->
      <div v-if="paper['📝重点思路']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">重点思路</h3>
        <div class="space-y-1.5">
          <div v-for="(item, idx) in paper['📝重点思路']" :key="'m' + idx" class="flex items-start gap-2">
            <span class="shrink-0 w-5 h-5 rounded-full bg-tinder-blue/20 text-tinder-blue flex items-center justify-center text-[11px] font-bold mt-0.5">
              {{ idx + 1 }}
            </span>
            <p class="text-sm text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- 分析总结 -->
      <div v-if="paper['🔎分析总结']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">分析总结</h3>
        <div class="space-y-1.5">
          <div v-for="(item, idx) in paper['🔎分析总结']" :key="'f' + idx" class="flex items-start gap-2">
            <span class="shrink-0 w-2 h-2 rounded-full bg-tinder-gold mt-2"></span>
            <p class="text-sm text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- 个人观点 -->
      <div v-if="paper['💡个人观点']" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">个人观点</h3>
        <p class="text-sm text-text-secondary italic leading-relaxed">{{ paper['💡个人观点'] }}</p>
      </div>

      <!-- Footer: paper ID -->
      <div class="flex items-center justify-between pt-3 border-t border-border">
        <span class="text-xs text-text-muted font-mono">{{ paper.paper_id }}</span>
        <span class="text-xs text-text-muted">{{ paper.image_count || 0 }} 张图</span>
      </div>
    </div>
  </div>
</template>
