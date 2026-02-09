<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'
import PaperCard from '../components/PaperCard.vue'
import ActionButtons from '../components/ActionButtons.vue'
import NoteEditor from './NoteEditor.vue'
import { fetchDates, fetchDigest, fetchKbTree, addKbPaper } from '../api'
import type { PaperSummary, KbTree } from '../types/paper'

const router = useRouter()

// Data
const dates = ref<string[]>([])
const selectedDate = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)
const error = ref('')

// Card navigation
const currentIndex = ref(0)
const cardAnimClass = ref('card-enter')
const history = ref<number[]>([])

// Knowledge base
const kbTree = ref<KbTree>({ folders: [], papers: [] })
const activeFolderId = ref<number | null>(null)

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
  try {
    kbTree.value = await fetchKbTree()
  } catch {}
}

// Load dates
onMounted(async () => {
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch (e: any) {
    error.value = '获取日期失败'
  }

  await loadKbTree()
})

// Load papers on date change
watch(selectedDate, async (date) => {
  if (!date) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchDigest(date)
    papers.value = res.papers
    currentIndex.value = 0
    history.value = []
    cardAnimClass.value = 'card-enter'
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    papers.value = []
  } finally {
    loading.value = false
  }
})

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

// Inline note editor
const editingNoteId = ref<number | null>(null)

function openPaperFromSidebar(paperId: string) {
  router.push(`/papers/${paperId}`)
}

function openNoteFromSidebar(noteId: number) {
  editingNoteId.value = noteId
}

async function closeNoteEditor() {
  editingNoteId.value = null
  // Refresh sidebar notes to show updated titles
  await loadKbTree()
  sidebarRef.value?.refreshAllExpandedNotes()
}

function resetCards() {
  currentIndex.value = 0
  history.value = []
  cardAnimClass.value = 'card-enter'
}
</script>

<template>
  <div class="h-full flex">
    <!-- Left sidebar (knowledge base) -->
    <Sidebar
      ref="sidebarRef"
      :kb-tree="kbTree"
      v-model:active-folder-id="activeFolderId"
      v-model:selected-date="selectedDate"
      :dates="dates"
      @open-paper="openPaperFromSidebar"
      @open-note="openNoteFromSidebar"
      @refresh="loadKbTree"
    />

    <!-- Center content area -->
    <div class="flex-1 flex flex-col relative overflow-hidden">
      <!-- Inline note editor -->
      <NoteEditor
        v-if="editingNoteId !== null"
        :key="editingNoteId"
        :id="String(editingNoteId)"
        :embedded="true"
        @close="closeNoteEditor"
      />

      <!-- Card swipe area -->
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
