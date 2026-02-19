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
import { fetchDates, fetchDigest, fetchKbTree, addKbPaper, deleteNote, fetchCompareResultsTree } from '../api'
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

// Load dates
onMounted(async () => {
  await ensureAuthInitialized()
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch (e: any) {
    error.value = '获取日期失败'
  }

  if (isAuthenticated.value) {
    await loadKbTree()
    await loadCompareTree()
  }
})

// Load papers on date change
watch(selectedDate, async (date) => {
  if (!date) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchDigest(date)
    papers.value = res.papers
    totalAvailable.value = res.total_available ?? res.papers.length
    quotaLimit.value = res.quota_limit ?? null
    responseTier.value = res.tier ?? (isAuthenticated.value ? currentTier.value : 'anonymous')
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    papers.value = []
    totalAvailable.value = 0
    quotaLimit.value = null
    responseTier.value = 'anonymous'
  } finally {
    loading.value = false
  }
})

// 判断是否超限（用户已刷完所有允许的论文，且论文数等于配额上限）
const isQuotaExceeded = computed(() => {
  if (quotaLimit.value === null) return false
  return currentIndex.value >= papers.value.length && papers.value.length >= quotaLimit.value
})

// 获取超限提示信息
const quotaExceededMessage = computed(() => {
  const tier = responseTier.value
  if (tier === 'pro_plus') return ''
  if (tier === 'pro') {
    return `您已达到 Pro 账号上限（15 条）`
  }
  if (!isAuthenticated.value || tier === 'anonymous') {
    return `您已达到未登录账号上限（3 条）`
  }
  return `您已达到普通账号上限（3 条）`
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
  },
)

function onDateChange(event: Event) {
  selectedDate.value = (event.target as HTMLSelectElement).value
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
  next('left')
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
}

async function openNoteFromSidebar(payload: { id: number; paperId: string }) {
  viewingPdf.value = null
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
}

function openPdfFromSidebar(payload: { paperId: string; filePath: string; title: string }) {
  editingNote.value = null
  sidebarPaperId.value = null
  viewingPdf.value = payload
}

const pdfViewerSrc = computed(() => {
  if (!viewingPdf.value) return ''
  const viewerPath = '/static/pdfjs/web/viewer.html'
  const fileUrl = `/static/kb_files/${viewingPdf.value.filePath}`
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

// 监听全局“回到推荐”事件
onMounted(() => {
  window.addEventListener('go-to-digest-click', handleGoToDigestClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('go-to-digest-click', handleGoToDigestClick)
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
  <div class="h-full flex">
    <template v-if="isAuthenticated">
      <!-- Left sidebar (knowledge base) -->
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
    </template>

    <!-- Center content area -->
    <div class="flex-1 flex flex-col relative overflow-hidden">
      <!-- 知识库模式：中间论文详情 + 右侧笔记编辑，等宽两栏 -->
      <div
        v-if="editingNote !== null"
        class="flex flex-1 overflow-hidden border-l border-border mt-3"
      >
        <!-- 中间：论文详情 -->
        <div class="w-1/2 h-full overflow-hidden border-r border-border bg-bg">
          <PaperDetail
            :key="editingNote.paperId"
            :id="editingNote.paperId"
            :embedded="true"
          />
        </div>

        <!-- 右侧：笔记编辑 -->
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
        <div v-else-if="error" class="flex flex-col items-center gap-3 text-center">
          <span class="text-tinder-pink text-lg">{{ error }}</span>
          <button
            class="px-4 py-2 rounded-full bg-tinder-pink text-white text-sm font-medium cursor-pointer border-none hover:opacity-90 transition-opacity"
            @click="selectedDate && (loading = true)"
          >
            重试
          </button>
        </div>

        <!-- 超限提示（不显示卡片，显示背景文字） -->
        <div v-else-if="isQuotaExceeded && quotaExceededMessage" class="flex flex-col items-center justify-center gap-4 text-center px-8">
          <div class="text-5xl mb-2">🔒</div>
          <h2 class="text-xl font-bold text-text-primary">查看限制</h2>
          <p class="text-base text-text-secondary max-w-md">
            {{ quotaExceededMessage }}
          </p>
          <p class="text-sm text-text-muted mt-2">
            升级账号可查看更多论文
          </p>
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

          <!-- The card -->
          <div class="w-[400px] h-[620px] mx-auto">
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
