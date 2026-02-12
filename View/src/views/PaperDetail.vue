<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SummarySection from '../components/SummarySection.vue'
import AssetsAccordion from '../components/AssetsAccordion.vue'
import { fetchPaperDetail } from '../api'
import type { PaperDetailResponse } from '../types/paper'

const props = defineProps<{
  /** 作为嵌入组件时直接传入 paperId；未传时回退到路由参数 */
  id?: string
  /** 嵌入模式下，不显示返回按钮等导航 UI */
  embedded?: boolean
}>()

const route = useRoute()
const router = useRouter()

const detail = ref<PaperDetailResponse | null>(null)
const loading = ref(true)
const error = ref('')
const activeTab = ref<'summary' | 'assets'>('summary')
const showPdfPane = ref(false)

function buildPdfViewerSrc(pdfUrl: string, paperId: string): string {
  const viewerPath = '/static/pdfjs/web/viewer.html'
  return `${viewerPath}?file=${encodeURIComponent(pdfUrl)}&paperId=${encodeURIComponent(paperId)}`
}

function openPdfPane() {
  showPdfPane.value = true
}

function closePdfPane() {
  showPdfPane.value = false
}

async function load(paperId: string) {
  loading.value = true
  error.value = ''
  try {
    detail.value = await fetchPaperDetail(paperId)
    showPdfPane.value = false
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? '论文未找到' : (e?.message || '加载失败')
    detail.value = null
    showPdfPane.value = false
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const id = (props.id as string) || (route.params.id as string)
  if (id) load(id)
})
watch(
  () => [props.id, route.params.id],
  ([pid, rid]) => {
    const id = (pid as string) || (rid as string)
    if (id) load(id)
  },
)
</script>

<template>
  <div :class="showPdfPane ? 'h-full overflow-hidden p-6' : 'h-full overflow-y-auto p-6'">
    <div :class="showPdfPane ? 'h-full max-w-none' : 'max-w-3xl mx-auto pb-24'">
      <!-- Back -->
      <button
        v-if="!props.embedded"
        class="inline-flex items-center gap-1 text-sm text-text-muted hover:text-tinder-pink mb-5 cursor-pointer bg-transparent border-none transition-colors"
        @click="router.back()"
      >
        ← 返回
      </button>

      <!-- Loading -->
      <div v-if="loading" class="flex justify-center py-20">
        <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="text-center py-20">
        <p class="text-tinder-pink text-lg mb-4">{{ error }}</p>
        <button
          class="px-5 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none"
          @click="router.push('/papers')"
        >返回列表</button>
      </div>

      <!-- Content -->
      <template v-if="detail && !loading">
        <div
          :class="showPdfPane ? 'h-full flex items-stretch' : ''"
          :style="showPdfPane ? 'padding-left:3%;padding-right:3%;gap:3%;' : ''"
        >
          <div :class="showPdfPane ? 'w-[40%] h-full min-w-0 overflow-y-auto' : ''">
            <!-- Header card -->
            <div class="bg-bg-card rounded-2xl border border-border p-6 mb-5">
              <div class="flex flex-wrap items-center gap-2 mb-3">
                <span class="px-3 py-1 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-xs font-semibold text-white">
                  {{ detail.summary.institution || '未知机构' }}
                </span>
                <span
                  v-if="detail.summary.is_large_institution"
                  class="px-2.5 py-0.5 rounded-full text-xs font-bold bg-tag-large-bg text-tag-large-text"
                >大机构</span>
                <span class="text-xs text-text-muted">{{ detail.date }}</span>
              </div>

              <h1 class="text-2xl font-bold text-text-primary leading-snug mb-2">
                {{ detail.summary.short_title }}
              </h1>
              <p class="text-sm text-text-secondary leading-relaxed mb-4">
                {{ detail.summary['📖标题'] }}
              </p>

              <div class="flex flex-wrap gap-3">
                <a
                  :href="detail.arxiv_url"
                  target="_blank"
                  rel="noopener"
                  class="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-bg-elevated border border-border text-sm font-medium text-tinder-blue no-underline hover:bg-bg-hover transition-colors"
                >
                  📄 arXiv
                </a>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-bg-elevated border border-border text-sm font-medium text-tinder-pink cursor-pointer hover:bg-bg-hover transition-colors"
                  @click="openPdfPane"
                >
                  📕 PDF
                </button>
                <span class="self-center text-xs font-mono text-text-muted">{{ detail.summary.paper_id }}</span>
              </div>
            </div>

            <!-- Tabs -->
            <div class="flex gap-1 mb-4 border-b border-border">
              <button
                class="px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
                :class="activeTab === 'summary'
                  ? 'border-tinder-pink text-tinder-pink'
                  : 'border-transparent text-text-muted hover:text-text-secondary'"
                @click="activeTab = 'summary'"
              >论文摘要</button>
              <button
                v-if="detail.paper_assets"
                class="px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors cursor-pointer bg-transparent border-l-0 border-r-0 border-t-0"
                :class="activeTab === 'assets'
                  ? 'border-tinder-pink text-tinder-pink'
                  : 'border-transparent text-text-muted hover:text-text-secondary'"
                @click="activeTab = 'assets'"
              >结构化分析</button>
            </div>

            <!-- Summary tab -->
            <div v-if="activeTab === 'summary'" class="bg-bg-card rounded-2xl border border-border p-6">
              <SummarySection :summary="detail.summary" />
            </div>

            <!-- Assets tab -->
            <div v-if="activeTab === 'assets' && detail.paper_assets" class="bg-bg-card rounded-2xl border border-border p-6">
              <AssetsAccordion :assets="detail.paper_assets" />
            </div>
          </div>

          <div
            v-if="showPdfPane"
            class="w-[51%] h-full min-w-0 bg-bg-card rounded-2xl border border-border overflow-hidden flex flex-col"
          >
            <div class="shrink-0 px-3 py-2 border-b border-border flex items-center justify-between gap-2">
              <span class="text-xs text-text-muted truncate">{{ detail.summary.paper_id }}.pdf</span>
              <div class="flex items-center gap-2">
                <a
                  :href="detail.pdf_url"
                  target="_blank"
                  rel="noopener"
                  class="px-2.5 py-1 rounded-full text-xs text-text-muted border border-border no-underline hover:bg-bg-hover transition-colors"
                >
                  新窗口打开
                </a>
                <button
                  type="button"
                  class="px-2.5 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
                  @click="closePdfPane"
                >
                  收起
                </button>
              </div>
            </div>
            <iframe
              :src="buildPdfViewerSrc(detail.pdf_url, detail.summary.paper_id)"
              class="w-full flex-1 border-none bg-black"
              title="PDF Viewer"
            />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
