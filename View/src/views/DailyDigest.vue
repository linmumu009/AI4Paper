<script setup lang="ts">
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import PaperCard from '../components/PaperCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import ComparePanel from '../components/ComparePanel.vue'
import CompareResultViewer from '../components/CompareResultViewer.vue'
import NoteEditor from './NoteEditor.vue'
import PaperDetail from './PaperDetail.vue'
import { fetchDates, fetchDigest, fetchKbTree, addKbPaper, deleteNote, fetchCompareResultsTree, dismissPaper, API_ORIGIN } from '../api'
import type { PaperSummary, KbTree, KbCompareResultsTree } from '../types/paper'
import { currentTier, ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const router = useRouter()
const route = useRoute()

// Data
const dates = ref<string[]>([])
const selectedDate = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)
const error = ref('')
const errorType = ref<'proxy' | 'server' | 'unknown'>('unknown')
const totalAvailable = ref<number>(0)
const quotaLimit = ref<number | null>(null)
const responseTier = ref<string>('anonymous')

// Card navigation
const currentIndex = ref(0)
const cardAnimClass = ref('card-enter')
const history = ref<number[]>([])

// Knowledge base
const kbTree = ref<KbTree>({ folders: [], papers: [] })
const activeFolderId = ref<number | null>(null)

// Compare results tree
const compareTree = ref<KbCompareResultsTree | null>(null)

const currentPaper = computed(() => papers.value[currentIndex.value] ?? null)
const remaining = computed(() => papers.value.length - currentIndex.value)
const allSwiped = computed(() => papers.value.length > 0 && currentIndex.value >= papers.value.length)
const isActuallyLimited = computed(() => {
  if (quotaLimit.value === null) return false
  return totalAvailable.value > papers.value.length
})

// Count total KB papers for display
const kbPaperCount = computed(() => {
  let count = kbTree.value.papers.length
  function countInFolders(folders: typeof kbTree.value.folders) {
    for (const f of folders) {
      count += f.papers?.length ?? 0
      if (f.children?.length) countInFolders(f.children)
    }
  }
  countInFolders(kbTree.value.folders)
  return count
})

// Load KB tree
async function loadKbTree() {
  if (!isAuthenticated.value) {
    kbTree.value = { folders: [], papers: [] }
    return
  }
  try {
    kbTree.value = await fetchKbTree()
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

// 加载日期列表（可被 retryLoad 复用）
async function loadDates() {
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch (e: any) {
    errorType.value = e?.errorType || 'unknown'
    error.value = e?.message || '获取日期失败'
  }
}

// Load dates
onMounted(async () => {
  await ensureAuthInitialized()
  await loadDates()

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
  }
})

async function loadDigestForDate(date: string, fallbackAuthed = isAuthenticated.value) {
  loading.value = true
  error.value = ''
  errorType.value = 'unknown'
  try {
    const res = await fetchDigest(date)
    const fetchedPapers = Array.isArray(res.papers) ? res.papers : []
    papers.value = fetchedPapers
    totalAvailable.value = res.total_available ?? fetchedPapers.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (fallbackAuthed ? currentTier.value : 'anonymous')
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
    if (import.meta.env.DEV) {
      console.debug('[DailyDigest] digest loaded', {
        date,
        papers: papers.value.length,
        totalAvailable: totalAvailable.value,
        quotaLimit: quotaLimit.value,
        tier: responseTier.value,
      })
    }
  } catch (e: any) {
    errorType.value = e?.errorType || (e?.response ? 'server' : 'unknown')
    error.value = e?.message || '加载失败'
    papers.value = []
    totalAvailable.value = 0
    quotaLimit.value = null
    responseTier.value = 'anonymous'
  } finally {
    loading.value = false
  }
}

// Load papers on date change
watch(selectedDate, async (date) => {
  if (!date) return
  await loadDigestForDate(date)
})

// 判断是否超限（用户已刷完所有允许的论文，且论文数等于配额上限）
const isQuotaExceeded = computed(() => {
  if (loading.value) return false
  const limit = quotaLimit.value
  const paperCount = papers.value.length
  if (limit === null || paperCount === 0) return false
  return currentIndex.value >= paperCount && paperCount >= limit
})

// 获取超限提示信息
const quotaExceededMessage = computed(() => {
  const tier = responseTier.value
  const limit = quotaLimit.value
  if (import.meta.env.DEV) {
    console.debug('[DailyDigest] quota message state', { tier, limit })
  }
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') {
    return `您已达到 Pro 账号上限（${limit ?? 15} 条）`
  }
  if (tier === 'anonymous') {
    return `您已达到未登录账号上限（${limit ?? 3} 条）`
  }
  return `您已达到普通账号上限（${limit ?? 3} 条）`
})

// 不再需要弹窗控制

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
    // Login/logout changes user-scoped filtering and quota.
    // Reload digest to avoid stale index/quota state from previous session.
    if (selectedDate.value) {
      const date = selectedDate.value
      await loadDigestForDate(date, authed)
    }
  },
)

function onDateChange(event: Event) {
  selectedDate.value = (event.target as HTMLSelectElement).value
}

function retryLoad() {
  errorType.value = 'unknown'
  error.value = ''
  if (dates.value.length === 0) {
    loadDates()
  } else if (selectedDate.value) {
    loadDigestForDate(selectedDate.value)
  }
}

// Actions
function next(direction: 'left' | 'right') {
  if (!currentPaper.value) return
  cardAnimClass.value = direction === 'left' ? 'card-swipe-left' : 'card-swipe-right'
  history.value.push(currentIndex.value)
  setTimeout(() => {
    currentIndex.value++
    cardAnimClass.value = 'card-enter'
  }, 300)
}

function skip() {
  const paper = currentPaper.value
  next('left')
  // 已登录用户：后台静默标记为"不感兴趣"，下次加载时不再展示
  if (paper && isAuthenticated.value) {
    dismissPaper(paper.paper_id).catch(() => {})
  }
}

function like() {
  const paper = currentPaper.value
  if (!paper) return
  if (!isAuthenticated.value) {
    router.push({ path: '/login', query: { redirect: route.fullPath } })
    return
  }
  // Animate card immediately for snappy UX
  next('right')
  // Fire API in background — don't block the animation
  addKbPaper(paper.paper_id, paper, activeFolderId.value)
    .then(() => loadKbTree())
    .catch(() => {})
}

function undo() {
  if (history.value.length === 0) return
  const prevIdx = history.value.pop()!
  currentIndex.value = prevIdx
  cardAnimClass.value = 'card-enter'
}

function openDetail() {
  if (currentPaper.value) {
    router.push(`/papers/${currentPaper.value.paper_id}`)
  }
}

function openPdf() {
  if (currentPaper.value) {
    window.open(`https://arxiv.org/pdf/${currentPaper.value.paper_id}`, '_blank')
  }
}

// Sidebar ref for refreshing notes
const sidebarRef = ref<InstanceType<typeof Sidebar> | null>(null)

// Inline note editor（携带 noteId + paperId，方便右侧显示详情）
const editingNote = ref<{ id: number; paperId: string } | null>(null)

// 从知识库点击的论文，在中间区域居中展示详情
const sidebarPaperId = ref<string | null>(null)
const viewingPdf = ref<{ paperId: string; filePath: string; title: string } | null>(null)

// 笔记编辑器组件引用，便于外部触发保存/检查是否为空
const noteEditorRef = ref<InstanceType<typeof NoteEditor> | null>(null)

// 对比分析
const comparingPaperIds = ref<string[] | null>(null)

// 查看已保存对比结果
const viewingCompareResultId = ref<number | null>(null)

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
  // 清理其他视图状态
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
  // 如果当前正在编辑笔记，优先处理笔记状态
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      // 笔记无内容：不保留这条笔记，直接删除记录
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败，继续切换
      }
      editingNote.value = null
    } else {
      // 笔记有内容：先自动保存，再关闭编辑器
      try {
        await noteEditorRef.value.flushSave()
      } catch {
        // 保存失败也不阻塞跳转
      }
      editingNote.value = null
    }
  }

  // 然后跳转到新点击论文的详情
  sidebarPaperId.value = paperId
  // 移动端：自动收起侧边栏，让用户立刻看到内容
  if (!mql.matches) showSidebar.value = false
}

async function openNoteFromSidebar(payload: { id: number; paperId: string }) {
  viewingPdf.value = null
  comparingPaperIds.value = null
  viewingCompareResultId.value = null
  // 如果当前正在编辑笔记，先判断是否为空
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      // 当前笔记为空：删除这条笔记记录，然后仅展示新点击论文的详情页
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
      editingNote.value = null
      sidebarPaperId.value = payload.paperId
      if (!mql.matches) showSidebar.value = false
      return
    } else {
      // 当前笔记有内容：自动保存后再打开新点击笔记的详情编辑页
      try {
        await noteEditorRef.value.flushSave()
      } catch {
        // 保存失败也不阻塞切换
      }
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

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  // 桌面端 pdfjs 和 kb_files 都托管在服务器上，需要加 API_ORIGIN 前缀
  const viewerPath = `${API_ORIGIN}/static/pdfjs/web/viewer.html`
  const fileUrl = `${API_ORIGIN}/static/kb_files/${viewingPdf.value.filePath}`
  return `${viewerPath}?file=${encodeURIComponent(fileUrl)}&paperId=${encodeURIComponent(viewingPdf.value.paperId)}`
})

// 全局“回到推荐”按钮事件处理：应用自动保存/删除规则，并回到推荐卡片视图
async function handleGoToDigestClick() {
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
    } else {
      try {
        await noteEditorRef.value.flushSave()
      } catch {
        // 保存失败也不阻塞
      }
    }
    editingNote.value = null
    // 保存或删除之后，确保左侧知识库立即刷新
    await loadKbTree()
    sidebarRef.value?.refreshAllExpandedNotes()
  }
  // 清理仅知识库详情状态，回到推荐刷卡视图
  sidebarPaperId.value = null
  viewingPdf.value = null
  comparingPaperIds.value = null
}

async function closeNoteEditor() {
  editingNote.value = null
  // 关闭笔记编辑时保留当前 sidebarPaperId，不打扰中间详情
  // Refresh sidebar notes to show updated titles
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

async function handleNoteSaved(payload: { id: number; title: string }) {
  // 先本地更新当前论文下笔记列表的标题，立即反馈到左侧知识库
  if (editingNote.value) {
    sidebarRef.value?.updateNoteTitle(editingNote.value.paperId, payload.id, payload.title)
  }
  // 再刷新一次知识库树和已展开论文下的笔记，确保与后端完全同步
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

function resetCards() {
  currentIndex.value = 0
  history.value = []
  cardAnimClass.value = 'card-enter'
}

// Sidebar toggle — default open on desktop, closed on mobile
const mql = window.matchMedia('(min-width: 1024px)')
const showSidebar = ref(mql.matches)

function onMqlChange(e: MediaQueryListEvent) {
  // When crossing the lg breakpoint, auto-adjust state:
  // opening on desktop resize-up, closing on mobile resize-down
  if (e.matches) {
    showSidebar.value = true
  } else {
    showSidebar.value = false
  }
}
mql.addEventListener('change', onMqlChange)

// 监听全局"回到推荐"事件
onMounted(() => {
  window.addEventListener('go-to-digest-click', handleGoToDigestClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('go-to-digest-click', handleGoToDigestClick)
  mql.removeEventListener('change', onMqlChange)
})

// 离开推荐页路由时（例如切到列表页），也应用同样的自动保存/删除规则
onBeforeRouteLeave(async (_to, _from, next) => {
  if (editingNote.value && noteEditorRef.value) {
    const isEmpty = noteEditorRef.value.isEffectivelyEmpty()
    if (isEmpty) {
      try {
        await deleteNote(editingNote.value.id)
      } catch {
        // 忽略删除失败
      }
    } else {
      try {
        await noteEditorRef.value.flushSave()
      } catch {
        // 保存失败不阻塞导航
      }
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
            scope="kb"
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
          <!-- Collapse button (universal: mobile + desktop) -->
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
            <h3 class="text-base font-semibold text-text-primary mb-2">登录后使用知识库</h3>
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
      </Transition>
    </template>

    <!-- Universal "open sidebar" button — visible whenever sidebar is collapsed -->
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

    <!-- Center content area -->
    <div class="flex-1 flex flex-col relative overflow-hidden min-w-0">
      <!-- 知识库模式：中间论文详情 + 右侧笔记编辑，等宽两栏（大屏）/ 上下两栏（小屏） -->
      <div
        v-if="editingNote !== null"
        class="flex flex-col lg:flex-row flex-1 overflow-hidden border-l border-border mt-3"
      >
        <!-- 中间：论文详情 -->
        <div class="h-1/2 lg:h-full lg:w-1/2 overflow-hidden border-b lg:border-b-0 lg:border-r border-border bg-bg">
          <PaperDetail
            :key="editingNote.paperId"
            :id="editingNote.paperId"
            :embedded="true"
          />
        </div>

        <!-- 右侧：笔记编辑 -->
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
          scope="kb"
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

      <!-- 仅从知识库点击 PDF 时：中间区域内嵌 PDF 阅读器 -->
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

      <!-- 仅从知识库点击论文时：中间区域显示论文详情（占满高度，可完整滚动） -->
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

      <!-- 默认卡片刷刷模式 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center relative">
        <!-- Loading -->
        <div v-if="loading" class="flex flex-col items-center gap-3">
          <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          <span class="text-text-muted text-sm">加载论文中...</span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex flex-col items-center gap-3 text-center px-8">
          <span class="text-tinder-pink text-lg">{{ error }}</span>
          <p v-if="errorType === 'proxy'" class="text-sm text-text-muted max-w-xs">
            检测到系统代理可能未启动，请关闭代理程序（如 Clash / V2Ray）或确保代理正常运行后重试
          </p>
          <p v-else-if="errorType === 'server'" class="text-sm text-text-muted">
            服务端出现异常，请稍后再试
          </p>
          <button
            class="px-4 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="retryLoad"
          >
            重试
          </button>
        </div>

        <!-- 超限提示（不显示卡片，显示背景文字） -->
        <div v-else-if="isQuotaExceeded && isActuallyLimited && quotaExceededMessage" class="flex flex-col items-center justify-center gap-4 text-center px-8">
          <div class="text-5xl mb-2">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">查看限制</h2>
          <p class="text-base text-text-secondary max-w-md">
            {{ quotaExceededMessage }}
          </p>
          <!-- 未登录用户：提示登录以继续 -->
          <template v-if="!isAuthenticated">
            <p class="text-sm text-text-muted">登录后即可继续浏览更多论文</p>
            <button
              class="mt-2 px-6 py-2.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold border-none cursor-pointer hover:opacity-90 transition-opacity"
              @click="router.push({ path: '/login', query: { redirect: route.fullPath } })"
            >
              立即登录
            </button>
          </template>
          <!-- 已登录用户：提示升级 -->
          <template v-else>
            <p class="text-sm text-text-muted mt-2">
              升级账号可查看更多论文
            </p>
          </template>
        </div>

        <!-- All swiped -->
        <div v-else-if="allSwiped" class="flex flex-col items-center gap-4 text-center px-8">
          <div class="text-5xl mb-2">🎉</div>
          <h2 class="text-xl font-bold text-text-primary">今日论文已全部浏览</h2>
          <p class="text-sm text-text-muted">
            共浏览 {{ papers.length }} 篇，知识库已收藏 {{ kbPaperCount }} 篇
          </p>
          <button
            class="px-6 py-2.5 rounded-full bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white text-sm font-semibold cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="resetCards"
          >
            重新浏览
          </button>
        </div>

        <!-- Card -->
        <template v-else-if="currentPaper">
          <!-- Counter -->
          <div class="absolute top-4 left-1/2 -translate-x-1/2 text-xs text-text-muted z-20">
            {{ currentIndex + 1 }} / {{ papers.length }}
          </div>

          <!-- The card — responsive width/height -->
          <div class="w-full max-w-[400px] px-3 sm:px-0 mx-auto" style="height: clamp(480px, calc(100dvh - 210px), 620px)">
            <PaperCard
              :key="currentPaper.paper_id"
              :paper="currentPaper"
              :anim-class="cardAnimClass"
            />
          </div>

          <!-- Action buttons -->
          <ActionButtons
            @undo="undo"
            @skip="skip"
            @like="like"
            @detail="openDetail"
            @superlike="openPdf"
          />
        </template>

        <!-- No data -->
        <div v-else-if="!loading && selectedDate" class="text-center text-text-muted">
          该日期暂无论文
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
