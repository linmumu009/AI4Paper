<script setup lang="ts">
import type { PaperSummary } from '../types/paper'

defineProps<{
  paper: PaperSummary
  animClass?: string
}>()

/* card background is set via CSS class, no dynamic gradient needed */

/** Remove leading emoji bullet (🔸) */
function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}
</script>

<template>
  <div
    class="card-bg relative w-full h-full rounded-2xl overflow-hidden select-none flex flex-col"
    :class="animClass"
  >
    <!-- Scrollable content area -->
    <div class="relative z-10 flex-1 overflow-y-auto px-5 pt-4 pb-5 space-y-4 scrollbar-thin card-body">

      <!-- === Header: institution + score === -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="institution-badge">
            {{ paper.institution || '未知机构' }}
          </span>
        </div>
        <div v-if="paper.relevance_score != null"
          class="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold border-2"
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

      <!-- === 标题区 === -->
      <div>
        <h2 class="text-xl font-bold text-text-primary leading-snug">
          {{ paper.short_title }}
        </h2>
        <p class="text-sm card-text mt-1">
          📖 {{ paper['📖标题'] }}
        </p>
        <p class="text-xs text-text-muted mt-1 font-mono">
          🌐 {{ paper['🌐来源'] }}
        </p>
      </div>

      <!-- === 🛎️文章简介 === -->
      <div class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🛎️ 文章简介</h3>
        <div class="text-sm card-text space-y-1">
          <p v-if="paper['🛎️文章简介']?.['🔸研究问题']">
            <span class="text-tinder-pink font-medium">研究问题：</span>{{ paper['🛎️文章简介']['🔸研究问题'] }}
          </p>
          <p v-if="paper['🛎️文章简介']?.['🔸主要贡献']">
            <span class="text-tinder-pink font-medium">主要贡献：</span>{{ paper['🛎️文章简介']['🔸主要贡献'] }}
          </p>
        </div>
      </div>

      <!-- === 📝重点思路 === -->
      <div v-if="paper['📝重点思路']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">📝 重点思路</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in paper['📝重点思路']"
            :key="'m' + idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-5 h-5 rounded-full bg-tinder-blue/20 text-tinder-blue flex items-center justify-center text-[10px] font-bold mt-0.5">
              {{ idx + 1 }}
            </span>
            <p class="text-sm card-text">
              {{ cleanBullet(item) }}
            </p>
          </div>
        </div>
      </div>

      <!-- === 🔎分析总结 === -->
      <div v-if="paper['🔎分析总结']?.length" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">🔎 分析总结</h3>
        <div class="space-y-1.5">
          <div
            v-for="(item, idx) in paper['🔎分析总结']"
            :key="'f' + idx"
            class="flex items-start gap-2"
          >
            <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-gold mt-1.5"></span>
            <p class="text-sm card-text">
              {{ cleanBullet(item) }}
            </p>
          </div>
        </div>
      </div>

      <!-- === 💡个人观点 === -->
      <div v-if="paper['💡个人观点']" class="space-y-1.5">
        <h3 class="text-sm font-semibold text-tinder-blue">💡 个人观点</h3>
        <p class="text-sm card-text italic">
          {{ paper['💡个人观点'] }}
        </p>
      </div>

      <!-- === Footer: paper ID === -->
      <div class="flex items-center justify-between pt-2 border-t border-border">
        <span class="text-xs text-text-muted font-mono">
          {{ paper.paper_id }}
        </span>
        <span class="text-xs text-text-muted">
          arXiv · {{ paper.image_count || 0 }} 张图
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

/* Prominent institution badge */
.institution-badge {
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
