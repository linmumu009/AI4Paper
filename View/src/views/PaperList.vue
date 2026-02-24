<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import IdeaCard from '../components/idea/IdeaCard.vue'
import IdeaDetailPanel from '../components/idea/IdeaDetailPanel.vue'
import ActionButtons from '../components/ActionButtons.vue'
import ComparePanel from '../components/ComparePanel.vue'
import CompareResultViewer from '../components/CompareResultViewer.vue'
import NoteEditor from './NoteEditor.vue'
import PaperDetail from './PaperDetail.vue'
import { fetchDates, fetchKbTree, addKbPaper, deleteNote, fetchCompareResultsTree, fetchIdeaDigest, createIdeaFeedback, addNoteLink, fetchIdeaAtom } from '../api'
import type { KbTree, KbCompareResultsTree, IdeaCandidate } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'

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
      if (selectedDate.value) {
        await loadIdeaDigest(selectedDate.value)
      }
    } else {
      kbTree.value = { folders: [], papers: [] }
      compareTree.value = null
      activeFolderId.value = null
      ideaCandidates.value = []
      ideaTotalAvailable.value = 0
      ideaQuotaLimit.value = null
      ideaResponseTier.value = 'free'
    }
  },
)

// ==================== 灵感推荐（日期驱动，类 DailyDigest）====================
const ideaCandidates = ref<IdeaCandidate[]>([])
const ideaLoading = ref(false)
const ideaError = ref('')
const ideaCurrentIndex = ref(0)
const ideaCardAnimClass = ref('card-enter')
const ideaHistory = ref<number[]>([])
const ideaTotalAvailable = ref(0)
const ideaQuotaLimit = ref<number | null>(null)
const ideaResponseTier = ref<string>('free')

const currentCandidate = computed(() => ideaCandidates.value[ideaCurrentIndex.value] ?? null)
const ideaAllSwiped = computed(
  () => ideaCandidates.value.length > 0 && ideaCurrentIndex.value >= ideaCandidates.value.length,
)
const isIdeaQuotaExceeded = computed(() => {
  if (ideaLoading.value) return false
  const limit = ideaQuotaLimit.value
  const count = ideaCandidates.value.length
  if (limit === null || count === 0) return false
  return ideaCurrentIndex.value >= count && count >= limit
})
const isIdeaActuallyLimited = computed(() => {
  if (ideaQuotaLimit.value === null) return false
  return ideaTotalAvailable.value > ideaCandidates.value.length
})
const ideaQuotaExceededMessage = computed(() => {
  const tier = ideaResponseTier.value
  const limit = ideaQuotaLimit.value
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') return `您已达到 Pro 账号上限（${limit ?? 15} 条）`
  return `您已达到普通账号上限（${limit ?? 3} 条）`
})

async function loadIdeaDigest(date: string) {
  if (!isAuthenticated.value || !date) {
    ideaCandidates.value = []
    return
  }
  ideaLoading.value = true
  ideaError.value = ''
  try {
    const res = await fetchIdeaDigest(date)
    ideaCandidates.value = res.candidates
    ideaTotalAvailable.value = res.total_available
    ideaQuotaLimit.value = res.quota_limit
    ideaResponseTier.value = res.tier ?? currentTier.value
    ideaCurrentIndex.value = 0
    ideaHistory.value = []
    ideaCardAnimClass.value = 'card-enter'
  } catch (e: any) {
    ideaError.value = e?.response?.data?.detail || '加载灵感失败'
    ideaCandidates.value = []
  } finally {
    ideaLoading.value = false
  }
}

// Reload ideas when date changes
watch(selectedDate, async (date) => {
  if (date && isAuthenticated.value) {
    await loadIdeaDigest(date)
  }
})

function ideaNext(direction: 'left' | 'right') {
  if (!currentCandidate.value) return
  ideaCardAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  ideaHistory.value.push(ideaCurrentIndex.value)
  setTimeout(() => {
    ideaCurrentIndex.value++
    ideaCardAnimClass.value = 'card-enter'
  }, 300)
}

function ideaSkip() {
  const candidate = currentCandidate.value
  ideaNext('left')
  if (candidate) {
    createIdeaFeedback({ candidate_id: candidate.id, action: 'discard' }).catch(() => {})
  }
}

function ideaLike() {
  const candidate = currentCandidate.value
  if (!candidate) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  ideaNext('right')
  // 1. 记录 collect 反馈（用于排除已看过的候选，后台静默）
  createIdeaFeedback({ candidate_id: candidate.id, action: 'collect' }).catch(() => {})
  // 2. 把灵感候选本身作为条目加入灵感知识库（与论文 like 逻辑完全一致）
  const paperData = {
    paper_id: `idea_${candidate.id}`,
    short_title: candidate.title,
    institution: candidate.strategy || '灵感',
    '📖标题': candidate.title,
    '🌐来源': '灵感推荐',
    '🛎️文章简介': {
      '🔸研究问题': candidate.goal || '',
      '🔸主要贡献': candidate.mechanism || '',
    },
    '📝重点思路': [] as string[],
    '🔎分析总结': [] as string[],
    '💡个人观点': candidate.risks || '',
  }
  addKbPaper(`idea_${candidate.id}`, paperData as any, activeFolderId.value, 'inspiration')
    .then(async () => {
      await loadKbTree()
      // 3. 将关联的来源论文作为链接子项添加到此灵感条目下（后台静默）
      if (candidate.input_atom_ids?.length) {
        try {
          const atomResults = await Promise.all(
            candidate.input_atom_ids.slice(0, 10).map((aid) =>
              fetchIdeaAtom(aid).then((r) => r.atom.paper_id).catch(() => null),
            ),
          )
          const uniquePaperIds = [...new Set(atomResults.filter(Boolean) as string[])]
          for (const pid of uniquePaperIds) {
            await addNoteLink(`idea_${candidate.id}`, pid, `/papers/${pid}`, 'inspiration').catch(() => {})
          }
          await loadKbTree()
        } catch {}
      }
    })
    .catch(() => {})
}

function ideaUndo() {
  if (ideaHistory.value.length === 0) return
  const prevIdx = ideaHistory.value.pop()!
  ideaCurrentIndex.value = prevIdx
  ideaCardAnimClass.value = 'card-enter'
}

function ideaOpenDetail() {
  if (currentCandidate.value) {
    // 与点击左侧灵感涌现库的效果一致：内嵌展示 IdeaDetailPanel
    viewingIdeaId.value = currentCandidate.value.id
    if (!mql.matches) showSidebar.value = false
  }
}

function ideaResetCards() {
  ideaCurrentIndex.value = 0
  ideaHistory.value = []
  ideaCardAnimClass.value = 'card-enter'
}

async function ideaRefresh() {
  if (selectedDate.value) {
    await loadIdeaDigest(selectedDate.value)
  }
}

// ==================== 侧边栏交互（知识库详情） ====================

// 从知识库点击论文 → 中间展示详情
const sidebarPaperId = ref<string | null>(null)

// 从知识库点击灵感条目 → 中间展示灵感详情面板
const viewingIdeaId = ref<number | null>(null)

// 笔记编辑
const editingNote = ref<{ id: number; paperId: string } | null>(null)
const noteEditorRef = ref<InstanceType<typeof NoteEditor> | null>(null)

// PDF 查看
const viewingPdf = ref<{ paperId: string; filePath: string; title: string } | null>(null)

// 对比分析
const comparingPaperIds = ref<string[] | null>(null)

// 查看已保存对比结果
const viewingCompareResultId = ref<number | null>(null)

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  const viewerPath = '/static/pdfjs/web/viewer.html'
  const fileUrl = `/static/kb_files/${viewingPdf.value.filePath}`
  return `${viewerPath}?file=${encodeURIComponent(fileUrl)}&paperId=${encodeURIComponent(viewingPdf.value.paperId)}`
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
  if (!mql.matches) showSidebar.value = false
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
  if (!mql.matches) showSidebar.value = false
}

function closeCompareResult() {
  viewingCompareResultId.value = null
}

async function openPaperFromSidebar(paperId: string) {
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
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

  // 若是灵感条目（paper_id = idea_XXX），展示灵感详情面板
  if (paperId.startsWith('idea_')) {
    const ideaId = parseInt(paperId.replace('idea_', ''), 10)
    if (!isNaN(ideaId)) {
      viewingIdeaId.value = ideaId
      sidebarPaperId.value = null
      if (!mql.matches) showSidebar.value = false
      return
    }
  }

  sidebarPaperId.value = paperId
  viewingIdeaId.value = null
  if (!mql.matches) showSidebar.value = false
}

async function openNoteFromSidebar(payload: { id: number; paperId: string }) {
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try { await deleteNote(editingNote.value.id) } catch {}
      editingNote.value = null
      sidebarPaperId.value = payload.paperId
      if (!mql.matches) showSidebar.value = false
      return
    } else {
      try { await noteEditorRef.value.flushSave() } catch {}
    }
  }
  editingNote.value = payload
  if (!mql.matches) showSidebar.value = false
}

function openPdfFromSidebar(payload: { paperId: string; filePath: string; title: string }) {
  editingNote.value = null
  sidebarPaperId.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  viewingPdf.value = payload
  if (!mql.matches) showSidebar.value = false
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
  viewingIdeaId.value = null
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

// Sidebar toggle — default open on desktop, closed on mobile
const mql = window.matchMedia('(min-width: 1024px)')
const showSidebar = ref(mql.matches)

function onMqlChange(e: MediaQueryListEvent) {
  if (e.matches) {
    showSidebar.value = true
  } else {
    showSidebar.value = false
  }
}
mql.addEventListener('change', onMqlChange)

onBeforeUnmount(() => {
  mql.removeEventListener('change', onMqlChange)
})

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
  <div class="h-full flex relative">

    <!-- Sidebar overlay backdrop (mobile only, when sidebar is open) -->
    <Transition name="fade">
      <div
        v-if="showSidebar"
        class="fixed inset-0 z-20 bg-black/60 lg:hidden"
        @click="showSidebar = false"
      />
    </Transition>

    <!-- ===== Authenticated sidebar ===== -->
    <template v-if="isAuthenticated">
      <Transition name="sidebar-slide">
        <div
          v-show="showSidebar"
          :class="[
            'shrink-0 z-30 h-full transition-transform duration-300 ease-in-out',
            'fixed lg:relative inset-y-0 left-0',
            showSidebar ? 'translate-x-0' : '-translate-x-full lg:-translate-x-full'
          ]"
        >
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
            @toggle-sidebar="showSidebar = false"
          />
        </div>
      </Transition>
    </template>

    <!-- ===== Unauthenticated sidebar ===== -->
    <template v-else>
      <Transition name="sidebar-slide">
        <aside
          v-show="showSidebar"
          :class="[
            'z-30 w-[80vw] max-w-[320px] lg:w-72 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300 ease-in-out relative',
            'fixed lg:relative inset-y-0 left-0',
            showSidebar ? 'translate-x-0' : '-translate-x-full lg:-translate-x-full'
          ]"
        >
          <!-- Collapse button -->
          <button
            class="absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary hover:bg-bg-elevated border-none cursor-pointer transition-colors z-10"
            title="收起侧边栏"
            @click="showSidebar = false"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>

          <div class="p-4 border-b border-border">
            <div class="bg-gradient-to-r from-[#fd267a] to-[#ff6036] rounded-xl p-3 mb-3">
              <div class="text-xs font-bold text-white/80 mb-1">灵感日报</div>
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
            <h3 class="text-base font-semibold text-text-primary mb-2">登录后浏览灵感推荐</h3>
            <p class="text-xs text-text-muted mb-4 leading-relaxed">
              灵感推荐、收藏和管理功能需要先登录
            </p>
            <button
              class="px-4 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
            >
              去登录
            </button>
          </div>
        </aside>
      </Transition>
    </template>

    <!-- Universal "open sidebar" button -->
    <Transition name="fade">
      <button
        v-if="!showSidebar"
        class="fixed top-1/2 -translate-y-1/2 left-0 z-10 flex items-center justify-center bg-bg-card border border-border border-l-0 rounded-r-xl w-6 h-14 text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors cursor-pointer"
        title="展开知识库"
        @click="showSidebar = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
    </Transition>

    <!-- ==================== 主内容区 ==================== -->
    <div class="flex-1 flex flex-col relative overflow-hidden min-w-0">

      <!-- 知识库：笔记编辑模式 -->
      <div
        v-if="editingNote !== null"
        class="flex flex-col lg:flex-row flex-1 overflow-hidden border-l border-border mt-3"
      >
        <div class="h-1/2 lg:h-full lg:w-1/2 overflow-hidden border-b lg:border-b-0 lg:border-r border-border bg-bg">
          <PaperDetail
            :key="editingNote.paperId"
            :id="editingNote.paperId"
            :embedded="true"
          />
        </div>
        <div class="h-1/2 lg:h-full lg:w-1/2 overflow-hidden bg-bg">
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
        class="flex-1 flex flex-col overflow-hidden mt-3 px-2 sm:px-4 pb-4"
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

      <!-- 灵感详情面板（点击灵感涌现库条目时显示，布局与论文知识库详情页一致） -->
      <div
        v-else-if="viewingIdeaId !== null"
        class="flex-1 flex justify-center relative overflow-hidden mt-3"
      >
        <div class="w-full h-full">
          <IdeaDetailPanel
            :key="viewingIdeaId"
            :candidate-id="viewingIdeaId"
            @close="viewingIdeaId = null"
            @open-paper="(pid) => { sidebarPaperId = pid; viewingIdeaId = null }"
          />
        </div>
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

      <!-- ==================== 灵感推荐主界面（刷卡模式）==================== -->
      <div v-else class="flex-1 flex flex-col items-center justify-center relative">

        <!-- 未登录 -->
        <div v-if="!isAuthenticated" class="flex flex-col items-center gap-4 text-center px-8">
          <div class="w-16 h-16 rounded-xl bg-bg-elevated border border-border flex items-center justify-center text-3xl">🔒</div>
          <h3 class="text-base font-semibold text-text-primary">登录后浏览灵感推荐</h3>
          <p class="text-xs text-text-muted">灵感推荐、收藏等功能需要登录</p>
          <button
            class="px-5 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-sm font-semibold text-white border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
          >
            去登录
          </button>
        </div>

        <!-- 加载中 -->
        <div v-else-if="ideaLoading" class="flex flex-col items-center gap-3">
          <svg class="animate-spin h-8 w-8 text-[#fd267a]" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-text-muted text-sm">加载灵感中...</span>
        </div>

        <!-- 加载出错 -->
        <div v-else-if="ideaError" class="flex flex-col items-center gap-3 text-center px-8">
          <span class="text-[#fd267a] text-base">{{ ideaError }}</span>
          <button
            class="px-4 py-2 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-medium cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="ideaRefresh"
          >
            重试
          </button>
        </div>

        <!-- 配额超限 -->
        <div
          v-else-if="isIdeaQuotaExceeded && isIdeaActuallyLimited && ideaQuotaExceededMessage"
          class="flex flex-col items-center justify-center gap-4 text-center px-8"
        >
          <div class="text-5xl mb-2">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">查看限制</h2>
          <p class="text-base text-text-secondary max-w-md">{{ ideaQuotaExceededMessage }}</p>
          <p class="text-sm text-text-muted mt-2">升级账号可查看更多灵感推荐</p>
        </div>

        <!-- 全部浏览完 -->
        <div v-else-if="ideaAllSwiped" class="flex flex-col items-center gap-4 text-center px-8">
          <div class="text-5xl mb-2">🎉</div>
          <h2 class="text-xl font-bold text-text-primary">今日灵感已全部浏览</h2>
          <p class="text-sm text-text-muted">共浏览 {{ ideaCandidates.length }} 条灵感</p>
          <div class="flex items-center gap-3 mt-2">
            <button
              class="px-6 py-2.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
              @click="ideaResetCards"
            >
              重新浏览
            </button>
            <button
              class="px-4 py-2.5 rounded-full border border-border bg-transparent text-sm text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors"
              @click="router.push('/idea')"
            >
              🧪 前往工作台
            </button>
          </div>
        </div>

        <!-- 灵感卡片 -->
        <template v-else-if="currentCandidate">
          <!-- 计数 -->
          <div class="absolute top-4 left-1/2 -translate-x-1/2 text-xs text-text-muted z-20">
            {{ ideaCurrentIndex + 1 }} / {{ ideaCandidates.length }}
          </div>

          <!-- 卡片 -->
          <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(480px, calc(100dvh - 210px), 620px)">
            <IdeaCard
              :key="currentCandidate.id"
              :candidate="currentCandidate"
              :anim-class="ideaCardAnimClass"
            />
          </div>

          <!-- 操作按钮 -->
          <ActionButtons
            @undo="ideaUndo"
            @skip="ideaSkip"
            @like="ideaLike"
            @detail="ideaOpenDetail"
            @superlike="ideaOpenDetail"
          />
        </template>

        <!-- 暂无灵感 -->
        <div v-else-if="!ideaLoading" class="flex flex-col items-center gap-5 text-center px-8 max-w-lg">
          <div class="relative w-28 h-28 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full bg-gradient-to-br from-[#fd267a]/20 to-[#ff6036]/20 animate-pulse" />
            <span class="text-6xl relative z-10">💡</span>
          </div>
          <h2 class="text-lg font-bold text-text-primary">
            {{ selectedDate ? `${selectedDate} 暂无灵感` : '还没有灵感' }}
          </h2>
          <p class="text-sm text-text-secondary leading-relaxed">
            灵感由管理员从当日论文中生成。请先确认已选择正确的日期，或等待管理员运行流水线。
          </p>
          <button
            class="mt-2 px-6 py-2.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity flex items-center gap-2 shadow-lg shadow-[#fd267a]/20"
            @click="ideaRefresh"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>
            </svg>
            刷新
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Sidebar slide transition */
.sidebar-slide-enter-active,
.sidebar-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.sidebar-slide-enter-from,
.sidebar-slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

/* Fade transition for backdrop and open button */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
