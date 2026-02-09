<script setup lang="ts">
import type { PaperSummary } from '../types/paper'

defineProps<{
  summary: PaperSummary
}>()
</script>

<template>
  <div class="space-y-6">
    <!-- 文章简介 -->
    <section>
      <h2 class="flex items-center gap-2 text-base font-semibold text-text-primary mb-3">
        <span>🛎️</span> 文章简介
      </h2>
      <div class="space-y-3 pl-4 border-l-2 border-tinder-pink/30">
        <div>
          <span class="text-xs font-medium text-tinder-pink">研究问题</span>
          <p class="text-sm text-text-secondary mt-0.5 leading-relaxed">
            {{ summary['🛎️文章简介']?.['🔸研究问题'] || '—' }}
          </p>
        </div>
        <div>
          <span class="text-xs font-medium text-tinder-pink">主要贡献</span>
          <p class="text-sm text-text-secondary mt-0.5 leading-relaxed">
            {{ summary['🛎️文章简介']?.['🔸主要贡献'] || '—' }}
          </p>
        </div>
      </div>
    </section>

    <!-- 重点思路 -->
    <section v-if="summary['📝重点思路']?.length">
      <h2 class="flex items-center gap-2 text-base font-semibold text-text-primary mb-3">
        <span>📝</span> 重点思路
      </h2>
      <ul class="space-y-2 pl-4">
        <li
          v-for="(item, idx) in summary['📝重点思路']"
          :key="idx"
          class="text-sm text-text-secondary leading-relaxed"
        >{{ item }}</li>
      </ul>
    </section>

    <!-- 分析总结 -->
    <section v-if="summary['🔎分析总结']?.length">
      <h2 class="flex items-center gap-2 text-base font-semibold text-text-primary mb-3">
        <span>🔎</span> 分析总结
      </h2>
      <ul class="space-y-2 pl-4">
        <li
          v-for="(item, idx) in summary['🔎分析总结']"
          :key="idx"
          class="text-sm text-text-secondary leading-relaxed"
        >{{ item }}</li>
      </ul>
    </section>

    <!-- 个人观点 -->
    <section v-if="summary['💡个人观点']">
      <h2 class="flex items-center gap-2 text-base font-semibold text-text-primary mb-3">
        <span>💡</span> 个人观点
      </h2>
      <p class="text-sm text-text-secondary leading-relaxed pl-4 border-l-2 border-tinder-gold/30">
        {{ summary['💡个人观点'] }}
      </p>
    </section>
  </div>
</template>
