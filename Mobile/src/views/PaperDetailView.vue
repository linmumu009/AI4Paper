<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { fetchPaperDetail, addKbPaper } from '../api'
import type { PaperDetailResponse } from '../types/paper'
import { isAuthenticated } from '../stores/auth'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const route = useRoute()

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')
const saved = ref(false)

const summary = computed(() => detail.value?.summary ?? null)
const assets = computed(() => detail.value?.paper_assets ?? null)

onMounted(async () => {
  try {
    detail.value = await fetchPaperDetail(props.id)
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/recommend')
  }
}

async function savePaper() {
  if (!summary.value) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  try {
    await addKbPaper(summary.value.paper_id, summary.value)
    saved.value = true
  } catch {}
}

function openArxiv() {
  if (detail.value?.arxiv_url) {
    window.open(detail.value.arxiv_url, '_blank')
  }
}

function openPdf() {
  if (detail.value?.pdf_url) {
    window.open(detail.value.pdf_url, '_blank')
  }
}

function cleanBullet(s: string): string {
  return s.replace(/^🔸\s*/, '')
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Top bar -->
    <div class="shrink-0 flex items-center gap-3 px-4 pt-4 pb-2 safe-area-top">
      <button
        class="w-10 h-10 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-primary"
        @click="goBack"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <h2 class="flex-1 text-base font-semibold text-text-primary truncate">论文详情</h2>
      <!-- Action buttons -->
      <button
        v-if="summary"
        class="px-4 py-2 rounded-full text-sm font-semibold border-none"
        :class="saved ? 'bg-tinder-green/20 text-tinder-green' : 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'"
        @click="savePaper"
      >
        {{ saved ? '已收藏' : '收藏' }}
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-5 pb-8 space-y-5" v-if="!loading && summary">
      <!-- Institution + Score -->
      <div class="flex items-center justify-between">
        <span class="institution-badge">{{ summary.institution || '未知机构' }}</span>
        <div
          v-if="summary.relevance_score != null"
          class="w-11 h-11 rounded-full flex items-center justify-center text-xs font-bold border-2"
          :class="summary.relevance_score >= 0.7
            ? 'border-tag-score-high text-tag-score-high'
            : summary.relevance_score >= 0.4
              ? 'border-tag-score-mid text-tag-score-mid'
              : 'border-tag-score-low text-tag-score-low'"
          :style="{ background: 'var(--color-bg-elevated)' }"
        >
          {{ (summary.relevance_score * 100).toFixed(0) }}
        </div>
      </div>

      <!-- Title -->
      <div>
        <h1 class="text-xl font-bold text-text-primary leading-snug">{{ summary.short_title }}</h1>
        <p class="text-sm text-text-secondary mt-1.5">{{ summary['📖标题'] }}</p>
        <p class="text-xs text-text-muted mt-1 font-mono">{{ summary['🌐来源'] }}</p>
        <p class="text-xs text-text-muted mt-0.5 font-mono">ID: {{ summary.paper_id }}</p>
      </div>

      <!-- Quick links -->
      <div class="flex gap-3">
        <button
          class="flex-1 py-2.5 rounded-xl bg-bg-elevated border border-border text-sm font-medium text-tinder-blue active:bg-bg-hover"
          @click="openArxiv"
        >
          ArXiv 页面
        </button>
        <button
          class="flex-1 py-2.5 rounded-xl bg-bg-elevated border border-border text-sm font-medium text-tinder-pink active:bg-bg-hover"
          @click="openPdf"
        >
          打开 PDF
        </button>
      </div>

      <!-- 文章简介 -->
      <div class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-base font-semibold text-tinder-blue">文章简介</h3>
        <div class="text-sm text-text-secondary space-y-1.5 leading-relaxed">
          <p v-if="summary['🛎️文章简介']?.['🔸研究问题']">
            <span class="text-tinder-pink font-medium">研究问题：</span>{{ summary['🛎️文章简介']['🔸研究问题'] }}
          </p>
          <p v-if="summary['🛎️文章简介']?.['🔸主要贡献']">
            <span class="text-tinder-pink font-medium">主要贡献：</span>{{ summary['🛎️文章简介']['🔸主要贡献'] }}
          </p>
        </div>
      </div>

      <!-- Abstract -->
      <div v-if="summary.abstract" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-base font-semibold text-tinder-blue">摘要</h3>
        <p class="text-sm text-text-secondary leading-relaxed">{{ summary.abstract }}</p>
      </div>

      <!-- 重点思路 -->
      <div v-if="summary['📝重点思路']?.length" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-base font-semibold text-tinder-blue">重点思路</h3>
        <div class="space-y-2.5">
          <div v-for="(item, idx) in summary['📝重点思路']" :key="'m' + idx" class="flex items-start gap-2.5">
            <span class="shrink-0 w-6 h-6 rounded-full bg-tinder-blue/20 text-tinder-blue flex items-center justify-center text-xs font-bold mt-0.5">
              {{ idx + 1 }}
            </span>
            <p class="text-sm text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- 分析总结 -->
      <div v-if="summary['🔎分析总结']?.length" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-base font-semibold text-tinder-blue">分析总结</h3>
        <div class="space-y-2.5">
          <div v-for="(item, idx) in summary['🔎分析总结']" :key="'f' + idx" class="flex items-start gap-2.5">
            <span class="shrink-0 w-2 h-2 rounded-full bg-tinder-gold mt-2"></span>
            <p class="text-sm text-text-secondary leading-relaxed">{{ cleanBullet(item) }}</p>
          </div>
        </div>
      </div>

      <!-- 个人观点 -->
      <div v-if="summary['💡个人观点']" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
        <h3 class="text-base font-semibold text-tinder-blue">个人观点</h3>
        <p class="text-sm text-text-secondary italic leading-relaxed">{{ summary['💡个人观点'] }}</p>
      </div>

      <!-- Structured analysis (paper_assets) -->
      <template v-if="assets">
        <div v-for="(block, key) in assets.blocks" :key="key" class="rounded-xl bg-bg-card border border-border p-5 space-y-2">
          <h3 class="text-base font-semibold text-tinder-purple capitalize">
            {{ key === 'background' ? '背景' : key === 'objective' ? '目标' : key === 'method' ? '方法' : key === 'data' ? '数据' : key === 'experiment' ? '实验' : key === 'metrics' ? '指标' : key === 'results' ? '结果' : key === 'limitations' ? '局限性' : key }}
          </h3>
          <p class="text-sm text-text-secondary leading-relaxed">{{ block.text }}</p>
          <ul v-if="block.bullets?.length" class="space-y-1.5 mt-1">
            <li v-for="(b, i) in block.bullets" :key="i" class="flex items-start gap-2">
              <span class="shrink-0 w-1.5 h-1.5 rounded-full bg-tinder-purple mt-2"></span>
              <span class="text-sm text-text-secondary leading-relaxed">{{ b }}</span>
            </li>
          </ul>
        </div>
      </template>

      <!-- Images -->
      <div v-if="detail?.images?.length" class="space-y-3">
        <h3 class="text-base font-semibold text-tinder-blue">论文图片</h3>
        <div class="grid grid-cols-2 gap-2">
          <img
            v-for="(img, idx) in detail.images"
            :key="idx"
            :src="img"
            class="w-full rounded-lg border border-border bg-bg-elevated"
            loading="lazy"
          />
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="flex-1 flex items-center justify-center">
      <svg class="animate-spin h-10 w-10 text-tinder-pink" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex-1 flex flex-col items-center justify-center gap-4 px-8">
      <span class="text-tinder-pink text-lg">{{ error }}</span>
      <button class="px-6 py-2.5 rounded-full bg-tinder-pink text-white text-base border-none" @click="goBack">
        返回
      </button>
    </div>
  </div>
</template>
