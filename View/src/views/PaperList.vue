<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import ComparePanel from '../components/ComparePanel.vue'
import CompareResultViewer from '../components/CompareResultViewer.vue'
import NoteEditor from './NoteEditor.vue'
import PaperDetail from './PaperDetail.vue'
import { fetchDates, fetchKbTree, addKbPaper, deleteNote, fetchCompareResultsTree } from '../api'
import type { KbTree, KbCompareResultsTree } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const router = useRouter()
const route = useRoute()

// Dates
const dates = ref<string[]>([])
const selectedDate = ref('')

// Knowledge base
const kbTree = ref<KbTree>({ folders: [], papers: [] })
const activeFolderId = ref<number | null>(null)

// Compare results tree
const compareTree = ref<KbCompareResultsTree | null>(null)

// Sidebar ref
const sidebarRef = ref<InstanceType<typeof Sidebar> | null>(null)

// Load KB tree
async function loadKbTree() {
  if (!isAuthenticated.value) {
    kbTree.value = { folders: [], papers: [] }
    return
  }
  try {
    kbTree.value = await fetchKbTree('inspiration')
  } catch {}
}

// Load compare results tree
async function loadCompareTree() {
  if (!isAuthenticated.value) {
    compareTree.value = null
    return
  }
  try {
    compareTree.value = await fetchCompareResultsTree()
  } catch {}
}

// Load dates
onMounted(async () => {
  await ensureAuthInitialized()
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch {}

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
  }
})

watch(
  () => isAuthenticated.value,
  async (authed) => {
    if (authed) {
      await loadKbTree()
      await loadCompareTree()
    } else {
      kbTree.value = { folders: [], papers: [] }
      compareTree.value = null
      activeFolderId.value = null
    }
  },
)

// ==================== 灵感生成 ====================
type Phase = 'idle' | 'loading' | 'done'
const phase = ref<Phase>('idle')

interface Inspiration {
  id: number
  title: string
  summary: string
  relatedPapers: { paperId: string; shortTitle: string }[]
  saved: boolean
}

const inspirations = ref<Inspiration[]>([])

const mockInspirations: Inspiration[] = [
  {
    id: 1,
    title: '跨模态对比学习用于零样本 3D 场景理解',
    summary:
      '结合视觉-语言预训练与点云编码器，设计一种无需 3D 标注数据即可进行开放词汇场景分类的框架。可利用今天出现的两篇多模态对齐论文中的对比损失策略，与 3D 稀疏卷积网络结合。',
    relatedPapers: [
      { paperId: '2501.00001', shortTitle: 'CLIP-Fields' },
      { paperId: '2501.00002', shortTitle: 'Point-BERT' },
    ],
    saved: false,
  },
  {
    id: 2,
    title: '基于扩散模型的科学文献图表自动生成',
    summary:
      '提出将科学论文中的实验数据直接转化为高质量图表的生成流水线。借鉴今日扩散模型可控生成的思路，以表格/JSON 数据为条件输入，生成 publication-ready 的矢量图。',
    relatedPapers: [
      { paperId: '2501.00003', shortTitle: 'ControlNet' },
      { paperId: '2501.00004', shortTitle: 'DiT-Adaptive' },
    ],
    saved: false,
  },
  {
    id: 3,
    title: '大语言模型引导的文献综述自动构建',
    summary:
      '设计一个 Agent 流水线：检索 → 聚类 → 大纲生成 → 段落撰写 → 引用校验，自动产出结构化综述草稿。结合今日 RAG 增强论文的检索改进方案提升引用准确率。',
    relatedPapers: [
      { paperId: '2501.00005', shortTitle: 'AutoSurvey' },
      { paperId: '2501.00006', shortTitle: 'RAG-Fusion' },
    ],
    saved: false,
  },
  {
    id: 4,
    title: '时序感知的论文推荐与研究趋势预测',
    summary:
      '构建以时间为轴的论文引用图，训练图神经网络预测未来 6 个月内哪些研究方向将成为热点。可以将今日图学习论文中提出的时序图 Transformer 直接应用于 Arxiv 引用网络。',
    relatedPapers: [
      { paperId: '2501.00007', shortTitle: 'TGN-Temporal' },
      { paperId: '2501.00008', shortTitle: 'GraphFormer' },
    ],
    saved: false,
  },
]

function generateInspirations() {
  phase.value = 'loading'
  setTimeout(() => {
    inspirations.value = mockInspirations.map((m) => ({ ...m, saved: false }))
    phase.value = 'done'
  }, 2200)
}

async function toggleSave(id: number) {
  const item = inspirations.value.find((i) => i.id === id)
  if (!item) return

  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }

  if (item.saved) {
    // 已加入则不做操作（后续可扩展为取消）
    return
  }

  item.saved = true

  // 将关联论文逐一加入灵感涌现库
  for (const paper of item.relatedPapers) {
    const paperData = {
      paper_id: paper.paperId,
      short_title: paper.shortTitle,
      institution: '',
      '📖标题': paper.shortTitle,
      '🌐来源': '',
      '🛎️文章简介': { '🔸研究问题': '', '🔸主要贡献': '' },
      '📝重点思路': [],
      '🔎分析总结': [],
      '💡个人观点': '',
    }
    addKbPaper(paper.paperId, paperData as any, activeFolderId.value, 'inspiration')
      .then(() => loadKbTree())
      .catch(() => {})
  }
}

function regenerate() {
  inspirations.value = []
  phase.value = 'idle'
}

// ==================== 侧边栏交互（知识库详情） ====================

// 从知识库点击论文 → 中间展示详情
const sidebarPaperId = ref<string | null>(null)

// 笔记编辑
const editingNote = ref<{ id: number; paperId: string } | null>(null)
const noteEditorRef = ref<InstanceType<typeof NoteEditor> | null>(null)

// PDF 查看
const viewingPdf = ref<{ paperId: string; filePath: string; title: string } | null>(null)

// 对比分析
const comparingPaperIds = ref<string[] | null>(null)

// 查看已保存对比结果
const viewingCompareResultId = ref<number | null>(null)

import { computed } from 'vue'

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  const viewerPath = '/static/pdfjs/web/viewer.html'
  const fileUrl = `/static/kb_files/${viewingPdf.value.filePath}`
  return `${viewerPath}?file=${encodeURIComponent(fileUrl)}&paperId=${encodeURIComponent(viewingPdf.value.paperId)}`
})

// 是否处于侧边栏详情模式（论文详情/笔记编辑/PDF查看/对比分析/对比结果查看）
const isSidebarDetailMode = computed(() => {
  return editingNote.value !== null || sidebarPaperId.value !== null || viewingPdf.value !== null || comparingPaperIds.value !== null || viewingCompareResultId.value !== null
})

// 构建 paper_id → short_title 映射，供 ComparePanel 显示标签
const comparePaperTitles = computed(() => {
  if (!comparingPaperIds.value) return {}
  const map: Record<string, string> = {}
  const allPapers = [
    ...kbTree.value.papers,
    ...kbTree.value.folders.flatMap(function collectPapers(f: any): any[] {
      return [...(f.papers || []), ...(f.children || []).flatMap(collectPapers)]
    }),
  ]
  for (const p of allPapers) {
    map[p.paper_id] = p.paper_data?.short_title || p.paper_id
  }
  return map
})

function handleCompare(paperIds: string[]) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  viewingCompareResultId.value = null
  comparingPaperIds.value = paperIds
}

function closeCompare() {
  comparingPaperIds.value = null
}

function handleCompareSaved(_resultId: number) {
  loadCompareTree()
}

function openCompareResult(resultId: number) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = resultId
}

function closeCompareResult() {
  viewingCompareResultId.value = null
}

async function openPaperFromSidebar(paperId: string) {
  viewingPdf.value = null
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
      editingNote.value = null
    } else {
      try { await noteEditorRef.value.flushSave() } catch {}
      editingNote.value = null
    }
  }
  sidebarPaperId.value = paperId
}

async function openNoteFromSidebar(payload: { id: number; paperId: string }) {
  viewingPdf.value = null
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
      editingNote.value = null
      sidebarPaperId.value = payload.paperId
      return
    } else {
      try { await noteEditorRef.value.flushSave() } catch {}
    }
  }
  editingNote.value = payload
}

function openPdfFromSidebar(payload: { paperId: string; filePath: string; title: string }) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = payload
}

async function handleBackToInspiration() {
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
    } else {
      try { await noteEditorRef.value.flushSave() } catch {}
    }
    editingNote.value = null
    await loadKbTree()
    sidebarRef.value?.refreshAllExpandedNotes()
  }
  sidebarPaperId.value = null
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
}

async function closeNoteEditor() {
  editingNote.value = null
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

async function handleNoteSaved(payload: { id: number; title: string }) {
  if (editingNote.value) {
    sidebarRef.value?.updateNoteTitle(editingNote.value.paperId, payload.id, payload.title)
  }
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

function onDateChange(event: Event) {
  selectedDate.value = (event.target as HTMLSelectElement).value
}

// 路由离开时自动保存笔记
onBeforeRouteLeave(async (_to, _from, next) => {
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
    } else {
      try { await noteEditorRef.value.flushSave() } catch {}
    }
    editingNote.value = null
  }
  next()
})
</script>

<template>
  <div class="h-full flex">
    <!-- ==================== 左侧侧边栏 ==================== -->
    <template v-if="isAuthenticated">
      <Sidebar
        ref="sidebarRef"
        :kb-tree="kbTree"
        :compare-tree="compareTree"
        v-model:active-folder-id="activeFolderId"
        v-model:selected-date="selectedDate"
        :dates="dates"
        scope="inspiration"
        title="灵感涌现"
        empty-title="收藏灵感"
        empty-desc="当你收藏灵感中关联的论文后，它们会在这里出现。"
        @open-paper="openPaperFromSidebar"
        @open-note="openNoteFromSidebar"
        @open-pdf="openPdfFromSidebar"
        @compare="handleCompare"
        @refresh="loadKbTree"
        @open-compare-result="openCompareResult"
        @refresh-compare="loadCompareTree"
      />
    </template>
    <template v-else>
      <aside class="w-72 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0">
        <div class="p-4 border-b border-border">
          <div class="bg-gradient-to-r from-[#fd267a] to-[#ff6036] rounded-xl p-3 mb-3">
            <div class="text-xs font-bold text-white/80 mb-1">论文日报</div>
            <select
              :value="selectedDate"
              @change="onDateChange"
              class="w-full bg-white/20 border-none rounded-lg px-2 py-1.5 text-white text-sm font-medium focus:outline-none cursor-pointer appearance-none"
            >
              <option v-for="d in dates" :key="d" :value="d" class="text-black">{{ d }}</option>
            </select>
          </div>
        </div>
        <div class="flex-1 p-4 flex flex-col items-center justify-center text-center">
          <div class="w-14 h-14 rounded-xl bg-bg-elevated border border-border mb-3 flex items-center justify-center text-2xl">
            🔒
          </div>
          <h3 class="text-base font-semibold text-text-primary mb-2">登录后使用灵感涌现</h3>
          <p class="text-xs text-text-muted mb-4 leading-relaxed">
            收藏论文、文件夹管理、笔记与附件上传需要先登录
          </p>
          <button
            class="px-4 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
          >
            去登录
          </button>
        </div>
      </aside>
    </template>

    <!-- ==================== 主内容区 ==================== -->
    <div class="flex-1 flex flex-col relative overflow-hidden">

      <!-- 知识库：笔记编辑模式（左论文详情 + 右笔记） -->
      <div
        v-if="editingNote !== null"
        class="flex flex-1 overflow-hidden border-l border-border mt-3"
      >
        <div class="w-1/2 h-full overflow-hidden border-r border-border bg-bg">
          <PaperDetail
            :key="editingNote.paperId"
            :id="editingNote.paperId"
            :embedded="true"
          />
        </div>
        <div class="w-1/2 h-full overflow-hidden bg-bg">
          <NoteEditor
            ref="noteEditorRef"
            :key="editingNote.id"
            :id="String(editingNote.id)"
            :embedded="true"
            @close="closeNoteEditor"
            @saved="handleNoteSaved"
          />
        </div>
      </div>

      <!-- 对比分析面板 -->
      <div
        v-else-if="comparingPaperIds"
        class="flex-1 overflow-hidden border-l border-border mt-3"
      >
        <ComparePanel
          :paper-ids="comparingPaperIds"
          :paper-titles="comparePaperTitles"
          scope="inspiration"
          @close="closeCompare"
          @saved="handleCompareSaved"
        />
      </div>

      <!-- 查看已保存的对比结果 -->
      <div
        v-else-if="viewingCompareResultId !== null"
        class="flex-1 overflow-hidden border-l border-border mt-3"
      >
        <CompareResultViewer
          :result-id="viewingCompareResultId"
          :paper-titles="comparePaperTitles"
          @close="closeCompareResult"
        />
      </div>

      <!-- 知识库：PDF 查看 -->
      <div
        v-else-if="viewingPdf"
        class="flex-1 flex flex-col overflow-hidden mt-3 px-4 pb-4"
      >
        <div class="shrink-0 flex items-center justify-between rounded-t-xl border border-border border-b-0 bg-bg-card px-4 py-2">
          <div class="text-sm text-text-secondary truncate pr-4">
            {{ viewingPdf.title || `${viewingPdf.paperId}.pdf` }}
          </div>
          <button
            class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="viewingPdf = null"
          >
            关闭 PDF
          </button>
        </div>
        <iframe
          :src="pdfViewerSrc"
          class="w-full flex-1 rounded-b-xl border border-border bg-black"
          title="PDF Viewer"
        />
      </div>

      <!-- 知识库：论文详情 -->
      <div
        v-else-if="sidebarPaperId"
        class="flex-1 flex justify-center relative overflow-hidden mt-3"
      >
        <div class="w-full h-full">
          <PaperDetail
            :key="sidebarPaperId"
            :id="sidebarPaperId"
            :embedded="true"
          />
        </div>
      </div>

      <!-- ==================== 灵感涌现主界面 ==================== -->
      <div v-else class="h-full flex flex-col p-6 overflow-hidden">
        <!-- Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 shrink-0">
          <div class="flex items-center gap-3">
            <h1 class="text-xl font-bold text-text-primary flex items-center gap-2">
              <span class="text-2xl">💡</span> 灵感涌现
            </h1>
            <span class="text-xs text-text-muted bg-bg-elevated px-2.5 py-1 rounded-full border border-border">
              Beta
            </span>
          </div>
          <div class="flex items-center gap-3">
            <!-- 生成按钮 -->
            <button
              v-if="phase !== 'loading'"
              class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2"
              @click="phase === 'done' ? regenerate() : generateInspirations()"
            >
              <svg v-if="phase === 'idle'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <span v-if="phase === 'idle'">生成灵感</span>
              <span v-else>重新生成</span>
            </button>
          </div>
        </div>

        <!-- ========== 空状态 ========== -->
        <div v-if="phase === 'idle'" class="flex-1 flex items-center justify-center">
          <div class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
            <div class="relative w-28 h-28 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse"></div>
              <span class="text-6xl relative z-10">💡</span>
            </div>
            <h2 class="text-lg font-bold text-text-primary">让 AI 为你发现研究灵感</h2>
            <p class="text-sm text-text-secondary leading-relaxed">
              选择一个日期，点击「生成灵感」，AI 将综合分析当日推荐论文，<br />
              从跨领域关联、方法迁移、潜在改进等角度为你提出研究想法。
            </p>
            <button
              class="mt-2 px-8 py-3 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-base font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2 shadow-lg shadow-[#fd267a]/20"
              @click="generateInspirations"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              生成灵感
            </button>
          </div>
        </div>

        <!-- ========== 加载中 ========== -->
        <div v-else-if="phase === 'loading'" class="flex-1 flex items-center justify-center">
          <div class="flex flex-col items-center gap-5 text-center">
            <div class="relative w-20 h-20 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin"></div>
              <div class="absolute inset-2 rounded-full border-2 border-transparent border-b-[#fd267a] border-l-[#ff6036] animate-spin" style="animation-direction: reverse; animation-duration: 1.5s;"></div>
              <span class="text-3xl relative z-10">🧠</span>
            </div>
            <h2 class="text-lg font-bold text-text-primary">AI 正在阅读论文...</h2>
            <p class="text-sm text-text-muted">综合分析当日论文，寻找跨领域灵感</p>
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-[#fd267a] animate-pulse"></div>
              <div class="w-2 h-2 rounded-full bg-[#ff6036] animate-pulse" style="animation-delay: 0.3s;"></div>
              <div class="w-2 h-2 rounded-full bg-[#f5b731] animate-pulse" style="animation-delay: 0.6s;"></div>
            </div>
          </div>
        </div>

        <!-- ========== 灵感卡片 ========== -->
        <div v-else class="flex-1 overflow-y-auto pr-1">
          <div class="text-xs text-text-muted mb-4">
            基于 {{ selectedDate }} 的论文生成了 {{ inspirations.length }} 条灵感
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div
              v-for="idea in inspirations"
              :key="idea.id"
              class="group relative rounded-xl bg-bg-card border border-border p-5 transition-all duration-200 hover:border-border-light hover:shadow-lg hover:shadow-black/20"
            >
              <!-- 渐变顶部装饰线 -->
              <div class="absolute top-0 left-4 right-4 h-[2px] rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] opacity-0 group-hover:opacity-100 transition-opacity"></div>

              <!-- 标题 -->
              <h3 class="text-base font-bold text-text-primary mb-2 leading-snug">
                {{ idea.title }}
              </h3>

              <!-- 摘要 -->
              <p class="text-sm text-text-secondary leading-relaxed mb-4">
                {{ idea.summary }}
              </p>

              <!-- 关联论文标签 -->
              <div class="flex flex-wrap gap-2 mb-4">
                <span
                  v-for="paper in idea.relatedPapers"
                  :key="paper.paperId"
                  class="text-xs px-2.5 py-1 rounded-full bg-bg-elevated border border-border text-text-muted cursor-pointer hover:text-text-secondary hover:border-border-light transition-colors"
                  @click="openPaperFromSidebar(paper.paperId)"
                >
                  📄 {{ paper.shortTitle }}
                </span>
              </div>

              <!-- 操作区 -->
              <div class="flex items-center justify-between pt-3 border-t border-border/50">
                <button
                  class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent cursor-pointer transition-colors flex items-center gap-1.5"
                  :class="idea.saved
                    ? 'text-tinder-pink border-tinder-pink/30 bg-tinder-pink/10'
                    : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
                  @click="toggleSave(idea.id)"
                >
                  <span>{{ idea.saved ? '💡' : '✦' }}</span>
                  {{ idea.saved ? '已加入灵感' : '加入灵感' }}
                </button>
                <button
                  class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors flex items-center gap-1.5"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                  展开详情
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
