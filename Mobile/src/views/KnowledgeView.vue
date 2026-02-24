<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import FolderItem from '../components/FolderItem.vue'
import PaperMiniCard from '../components/PaperMiniCard.vue'
import ActionSheet from '../components/ActionSheet.vue'
import FolderPickerSheet from '../components/FolderPickerSheet.vue'
import {
  fetchKbTree,
  createKbFolder,
  renameKbFolder,
  deleteKbFolder,
  moveKbFolder,
  removeKbPaper,
  moveKbPapers,
  renameKbPaper,
  fetchNotes,
  createNote,
  uploadNoteFile,
  addNoteLink,
  deleteNote as apiDeleteNote,
  fetchCompareResultsTree,
  renameCompareResult as apiRenameCompare,
  deleteCompareResult as apiDeleteCompare,
} from '../api'
import type { KbScope } from '../api'
import type { KbTree, KbPaper, KbFolder, KbNote, KbMenuItem, KbCompareResultsTree, KbCompareResult } from '../types/paper'
import { isAuthenticated } from '../stores/auth'

defineOptions({ name: 'KnowledgeView' })

const router = useRouter()

// ---- Core state ----
const scope = ref<KbScope>('kb')
const tree = ref<KbTree>({ folders: [], papers: [] })
const compareTree = ref<KbCompareResultsTree | null>(null)
const loading = ref(false)

// ---- Tab ----
type ViewTab = 'papers' | 'compare'
const activeTab = ref<ViewTab>('papers')

// ---- New folder ----
const showNewFolder = ref(false)
const newFolderName = ref('')

// ---- Rename folder ----
const renamingFolder = ref<KbFolder | null>(null)
const renamingFolderName = ref('')

// ---- Rename paper ----
const renamingPaper = ref<KbPaper | null>(null)
const renamingPaperTitle = ref('')

// ---- Action sheet ----
const actionSheetItems = ref<KbMenuItem[]>([])
const actionSheetTitle = ref('')
const showActionSheet = ref(false)
const actionTarget = ref<{ type: string; data: any } | null>(null)

// ---- Folder picker ----
const showFolderPicker = ref(false)
const folderPickerTitle = ref('')
const movingPaperIds = ref<string[]>([])
const movingFolderId = ref<number | null>(null)

// ---- Batch mode ----
const batchMode = ref(false)
const checkedPapers = ref<Set<string>>(new Set())

const hasChecked = computed(() => checkedPapers.value.size > 0)
const canCompare = computed(() => checkedPapers.value.size >= 2 && checkedPapers.value.size <= 5)

// ---- Notes ----
const expandedPapers = ref<Set<string>>(new Set())
const paperNotes = ref<Map<string, KbNote[]>>(new Map())

// ---- File upload ----
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetPaperId = ref('')

// ---- Computed ----
const totalPapers = computed(() => {
  let count = tree.value.papers.length
  function countInFolders(folders: KbFolder[]) {
    for (const f of folders) {
      count += f.papers?.length ?? 0
      if (f.children?.length) countInFolders(f.children)
    }
  }
  countInFolders(tree.value.folders)
  return count
})

const allFolders = computed(() => tree.value.folders ?? [])

// ---- Load data ----
async function loadTree() {
  if (!isAuthenticated.value) return
  loading.value = true
  try {
    tree.value = await fetchKbTree(scope.value)
  } catch {
    tree.value = { folders: [], papers: [] }
  } finally {
    loading.value = false
  }
}

async function loadCompareTree() {
  try {
    compareTree.value = await fetchCompareResultsTree()
  } catch {
    compareTree.value = { folders: [], results: [] }
  }
}

onMounted(() => {
  loadTree()
  loadCompareTree()
})

watch(scope, () => {
  loadTree()
  // Reset batch mode on scope change
  batchMode.value = false
  checkedPapers.value = new Set()
})

watch(isAuthenticated, (v) => {
  if (v) {
    loadTree()
    loadCompareTree()
  }
})

// ---- Navigation ----
function openPaper(paperId: string) {
  router.push(`/paper/${paperId}`)
}

// ---- Toggle batch mode ----
function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    checkedPapers.value = new Set()
  }
}

function toggleCheck(paperId: string) {
  const next = new Set(checkedPapers.value)
  if (next.has(paperId)) next.delete(paperId)
  else next.add(paperId)
  checkedPapers.value = next
}

// ---- Paper operations via ActionSheet ----
function openPaperMenu(paper: KbPaper) {
  actionTarget.value = { type: 'paper', data: paper }
  actionSheetTitle.value = paper.paper_data.short_title
  actionSheetItems.value = [
    { key: 'rename-paper', label: '重命名' },
    { key: 'move-paper', label: '移动到文件夹...' },
    { key: 'delete-paper', label: '从知识库删除', danger: true },
  ]
  showActionSheet.value = true
}

function openFolderMenu(folder: KbFolder) {
  actionTarget.value = { type: 'folder', data: folder }
  actionSheetTitle.value = folder.name
  actionSheetItems.value = [
    { key: 'new-subfolder', label: '新建子文件夹' },
    { key: 'rename-folder', label: '重命名' },
    { key: 'move-folder', label: '移动到...' },
    { key: 'delete-folder', label: '删除文件夹', danger: true },
  ]
  showActionSheet.value = true
}

function openCompareResultMenu(result: KbCompareResult) {
  actionTarget.value = { type: 'compare-result', data: result }
  actionSheetTitle.value = result.title
  actionSheetItems.value = [
    { key: 'rename-compare', label: '重命名' },
    { key: 'delete-compare', label: '删除', danger: true },
  ]
  showActionSheet.value = true
}

async function handleActionSelect(key: string) {
  showActionSheet.value = false
  if (!actionTarget.value) return

  const { type, data } = actionTarget.value

  if (type === 'paper') {
    const paper = data as KbPaper
    if (key === 'rename-paper') {
      renamingPaper.value = paper
      renamingPaperTitle.value = paper.paper_data.short_title
    } else if (key === 'move-paper') {
      movingPaperIds.value = [paper.paper_id]
      movingFolderId.value = null
      folderPickerTitle.value = '移动论文到文件夹'
      showFolderPicker.value = true
    } else if (key === 'delete-paper') {
      try {
        await removeKbPaper(paper.paper_id, scope.value)
        await loadTree()
      } catch {}
    }
  }

  if (type === 'folder') {
    const folder = data as KbFolder
    if (key === 'rename-folder') {
      renamingFolder.value = folder
      renamingFolderName.value = folder.name
    } else if (key === 'delete-folder') {
      try {
        await deleteKbFolder(folder.id, scope.value)
        await loadTree()
      } catch {}
    } else if (key === 'new-subfolder') {
      // Prompt for name
      const name = window.prompt('子文件夹名称')
      if (name?.trim()) {
        try {
          await createKbFolder(name.trim(), folder.id, scope.value)
          await loadTree()
        } catch {}
      }
    } else if (key === 'move-folder') {
      movingFolderId.value = folder.id
      movingPaperIds.value = []
      folderPickerTitle.value = `移动"${folder.name}"到...`
      showFolderPicker.value = true
    }
  }

  if (type === 'compare-result') {
    const result = data as KbCompareResult
    if (key === 'rename-compare') {
      const newTitle = window.prompt('新标题', result.title)
      if (newTitle?.trim()) {
        try {
          await apiRenameCompare(result.id, newTitle.trim())
          await loadCompareTree()
        } catch {}
      }
    } else if (key === 'delete-compare') {
      try {
        await apiDeleteCompare(result.id)
        await loadCompareTree()
      } catch {}
    }
  }

  actionTarget.value = null
}

// ---- Rename folder confirm ----
async function confirmRenameFolder() {
  if (!renamingFolder.value) return
  const name = renamingFolderName.value.trim()
  const folderId = renamingFolder.value.id
  renamingFolder.value = null
  if (!name) return
  try {
    await renameKbFolder(folderId, name, scope.value)
    await loadTree()
  } catch {}
}

// ---- Rename paper confirm ----
async function confirmRenamePaper() {
  if (!renamingPaper.value) return
  const title = renamingPaperTitle.value.trim()
  const paperId = renamingPaper.value.paper_id
  renamingPaper.value = null
  if (!title) return
  try {
    await renameKbPaper(paperId, title, scope.value)
    await loadTree()
  } catch {}
}

// ---- New folder ----
async function handleCreateFolder() {
  if (!newFolderName.value.trim()) return
  try {
    await createKbFolder(newFolderName.value.trim(), null, scope.value)
    newFolderName.value = ''
    showNewFolder.value = false
    await loadTree()
  } catch {}
}

// ---- Folder picker confirm ----
async function handleMoveTo(targetId: number | null) {
  showFolderPicker.value = false

  if (movingFolderId.value !== null) {
    try {
      await moveKbFolder(movingFolderId.value, targetId, scope.value)
      await loadTree()
    } catch {}
    movingFolderId.value = null
    return
  }

  if (movingPaperIds.value.length === 0) return
  try {
    await moveKbPapers(movingPaperIds.value, targetId, scope.value)
    checkedPapers.value = new Set()
    await loadTree()
  } catch {}
  movingPaperIds.value = []
}

// ---- Batch operations ----
function startBatchMove() {
  movingPaperIds.value = [...checkedPapers.value]
  movingFolderId.value = null
  folderPickerTitle.value = '移动论文到文件夹'
  showFolderPicker.value = true
}

function startCompare() {
  if (!canCompare.value) return
  const ids = [...checkedPapers.value]
  batchMode.value = false
  checkedPapers.value = new Set()
  router.push({ path: '/compare', query: { ids: ids.join(',') } })
}

// ---- Notes ----
async function togglePaperExpand(paperId: string) {
  const next = new Set(expandedPapers.value)
  if (next.has(paperId)) {
    next.delete(paperId)
  } else {
    next.add(paperId)
    if (!paperNotes.value.has(paperId)) {
      await loadPaperNotes(paperId)
    }
  }
  expandedPapers.value = next
}

async function loadPaperNotes(paperId: string) {
  try {
    const res = await fetchNotes(paperId, scope.value)
    const next = new Map(paperNotes.value)
    next.set(paperId, res.notes)
    paperNotes.value = next
  } catch {}
}

async function handleCreateNote(paperId: string) {
  try {
    await createNote(paperId, '未命名笔记', '', scope.value)
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    await loadTree()
  } catch {}
}

function handleUploadFile(paperId: string) {
  uploadTargetPaperId.value = paperId
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !uploadTargetPaperId.value) return
  try {
    await uploadNoteFile(uploadTargetPaperId.value, file, scope.value)
    const next = new Set(expandedPapers.value)
    next.add(uploadTargetPaperId.value)
    expandedPapers.value = next
    await loadPaperNotes(uploadTargetPaperId.value)
    await loadTree()
  } catch {}
  input.value = ''
}

async function handleAddLink(paperId: string) {
  const url = window.prompt('请输入链接 URL')
  if (!url) return
  const title = window.prompt('链接标题（可选）') || url
  try {
    await addNoteLink(paperId, title, url, scope.value)
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    await loadTree()
  } catch {}
}

function handleOpenNote(note: KbNote) {
  if (note.type === 'link' && note.file_url) {
    window.open(note.file_url, '_blank')
  } else if (note.type === 'file' && note.file_path) {
    window.open(`/static/kb_files/${note.file_path}`, '_blank')
  } else {
    // For markdown notes, open note editor
    router.push(`/notes/${note.id}`)
  }
}

async function handleDeleteNote(noteId: number) {
  try {
    await apiDeleteNote(noteId)
    for (const pid of expandedPapers.value) {
      await loadPaperNotes(pid)
    }
    await loadTree()
  } catch {}
}

// ---- Compare result navigation ----
function openCompareResult(resultId: number) {
  router.push(`/compare-result/${resultId}`)
}

// Compare folders expand state
const expandedCompareFolders = ref<Set<number>>(new Set())
function toggleCompareFolder(folderId: number) {
  const next = new Set(expandedCompareFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedCompareFolders.value = next
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Hidden file input -->
    <input ref="fileInputRef" type="file" class="hidden" @change="onFileSelected" />

    <!-- Header -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center justify-between px-5 pt-4 pb-2">
        <h1 class="text-xl font-bold gradient-text">
          {{ scope === 'kb' ? '知识库' : '灵感库' }}
        </h1>
        <div class="flex items-center gap-2">
          <!-- Batch toggle (only in papers tab) -->
          <button
            v-if="activeTab === 'papers'"
            class="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors"
            :class="batchMode
              ? 'border-tinder-pink text-tinder-pink bg-tinder-pink/10'
              : 'border-border text-text-muted bg-transparent active:bg-bg-hover'"
            @click="toggleBatchMode"
          >
            {{ batchMode ? '取消' : '批量' }}
          </button>
          <!-- Add folder button -->
          <button
            v-if="activeTab === 'papers'"
            class="w-9 h-9 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-muted active:bg-bg-hover"
            @click="showNewFolder = !showNewFolder"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Scope toggle -->
      <div class="flex mx-4 mb-2 p-0.5 rounded-xl bg-bg-elevated">
        <button
          class="flex-1 py-2 rounded-lg text-sm font-semibold transition-all border-none"
          :class="scope === 'kb' ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white' : 'bg-transparent text-text-muted'"
          @click="scope = 'kb'"
        >
          知识库
        </button>
        <button
          class="flex-1 py-2 rounded-lg text-sm font-semibold transition-all border-none"
          :class="scope === 'inspiration' ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white' : 'bg-transparent text-text-muted'"
          @click="scope = 'inspiration'"
        >
          灵感库
        </button>
      </div>

      <!-- Papers / Compare tab bar -->
      <div class="flex items-center gap-6 px-5 border-b border-border">
        <button
          class="pb-2.5 text-sm font-semibold border-none bg-transparent transition-colors"
          :class="activeTab === 'papers'
            ? 'text-tinder-pink border-b-2 border-tinder-pink'
            : 'text-text-muted'"
          :style="activeTab === 'papers' ? 'border-bottom: 2px solid var(--color-tinder-pink)' : ''"
          @click="activeTab = 'papers'"
        >
          论文
        </button>
        <button
          class="pb-2.5 text-sm font-semibold border-none bg-transparent transition-colors"
          :class="activeTab === 'compare'
            ? 'text-[#8b5cf6] border-b-2 border-[#8b5cf6]'
            : 'text-text-muted'"
          :style="activeTab === 'compare' ? 'border-bottom: 2px solid #8b5cf6' : ''"
          @click="activeTab = 'compare'; loadCompareTree()"
        >
          对比库
        </button>
      </div>

      <!-- New folder input -->
      <div v-if="showNewFolder && activeTab === 'papers'" class="flex items-center gap-2 px-4 py-2 border-b border-border">
        <input
          v-model="newFolderName"
          placeholder="新文件夹名称"
          class="flex-1 bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink"
          @keydown.enter="handleCreateFolder"
        />
        <button
          class="px-4 py-2.5 rounded-lg bg-tinder-pink text-white text-sm font-semibold border-none"
          @click="handleCreateFolder"
        >
          创建
        </button>
      </div>
    </div>

    <!-- ========== Papers tab content ========== -->
    <div v-if="activeTab === 'papers'" class="flex-1 overflow-y-auto pb-4">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
      </div>

      <template v-else>
        <!-- Folders -->
        <FolderItem
          v-for="folder in tree.folders"
          :key="folder.id"
          :folder="folder"
          :batch-mode="batchMode"
          :checked-papers="checkedPapers"
          :expanded-papers="expandedPapers"
          :paper-notes="paperNotes"
          @tap-paper="openPaper"
          @remove-paper="(id) => removeKbPaper(id, scope).then(loadTree)"
          @paper-menu="openPaperMenu"
          @folder-menu="openFolderMenu"
          @toggle-check="toggleCheck"
          @toggle-expand="togglePaperExpand"
          @create-note="handleCreateNote"
          @upload-file="handleUploadFile"
          @add-link="handleAddLink"
          @open-note="handleOpenNote"
          @delete-note="handleDeleteNote"
        />

        <!-- Root-level papers -->
        <div v-if="tree.papers.length" class="space-y-2 px-4 mt-2">
          <PaperMiniCard
            v-for="p in tree.papers"
            :key="p.paper_id"
            :paper="p"
            :batch-mode="batchMode"
            :checked="checkedPapers.has(p.paper_id)"
            :expanded="expandedPapers.has(p.paper_id)"
            :notes="paperNotes.get(p.paper_id)"
            @tap="openPaper"
            @remove="(id) => removeKbPaper(id, scope).then(loadTree)"
            @menu="openPaperMenu"
            @toggle-check="toggleCheck"
            @toggle-expand="togglePaperExpand"
            @create-note="handleCreateNote"
            @upload-file="handleUploadFile"
            @add-link="handleAddLink"
            @open-note="handleOpenNote"
            @delete-note="handleDeleteNote"
          />
        </div>

        <!-- Empty state -->
        <div v-if="!tree.folders.length && !tree.papers.length" class="flex flex-col items-center justify-center py-16 px-8 text-center">
          <div class="text-5xl mb-4">📚</div>
          <h3 class="text-lg font-semibold text-text-primary mb-2">
            {{ scope === 'kb' ? '知识库为空' : '灵感库为空' }}
          </h3>
          <p class="text-sm text-text-muted leading-relaxed">
            在推荐页右滑论文即可收藏到{{ scope === 'kb' ? '知识库' : '灵感库' }}
          </p>
        </div>
      </template>
    </div>

    <!-- ========== Compare tab content ========== -->
    <div v-if="activeTab === 'compare'" class="flex-1 overflow-y-auto pb-4">
      <template v-if="compareTree">
        <!-- Compare folders -->
        <div
          v-for="folder in compareTree.folders"
          :key="folder.id"
          class="border-b border-border"
        >
          <div
            class="flex items-center gap-3 px-4 py-3.5 active:bg-bg-hover transition-colors"
            @click="toggleCompareFolder(folder.id)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
              class="shrink-0 text-text-muted transition-transform duration-200"
              :class="expandedCompareFolders.has(folder.id) ? 'rotate-90' : ''"
            >
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span class="text-sm">📁</span>
            <span class="text-sm font-medium text-text-primary truncate flex-1">{{ folder.name }}</span>
          </div>
          <div v-if="expandedCompareFolders.has(folder.id)" class="pl-6">
            <div
              v-for="result in folder.results"
              :key="result.id"
              class="flex items-center gap-3 px-4 py-3 active:bg-bg-hover transition-colors"
              @click="openCompareResult(result.id)"
            >
              <span class="text-sm">📊</span>
              <span class="text-sm text-text-primary truncate flex-1">{{ result.title }}</span>
              <span class="text-xs text-text-muted shrink-0">{{ result.paper_ids.length }}篇</span>
              <button
                class="shrink-0 w-7 h-7 flex items-center justify-center text-text-muted bg-transparent border-none rounded-full active:bg-bg-hover"
                @click.stop="openCompareResultMenu(result)"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Root compare results -->
        <div
          v-for="result in compareTree.results"
          :key="result.id"
          class="flex items-center gap-3 px-4 py-3.5 border-b border-border active:bg-bg-hover transition-colors"
          @click="openCompareResult(result.id)"
        >
          <span class="text-sm">📊</span>
          <span class="text-sm text-text-primary truncate flex-1">{{ result.title }}</span>
          <span class="text-xs text-text-muted shrink-0">{{ result.paper_ids.length }}篇</span>
          <button
            class="shrink-0 w-7 h-7 flex items-center justify-center text-text-muted bg-transparent border-none rounded-full active:bg-bg-hover"
            @click.stop="openCompareResultMenu(result)"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
            </svg>
          </button>
        </div>

        <!-- Empty compare state -->
        <div
          v-if="compareTree.folders.length === 0 && compareTree.results.length === 0"
          class="flex flex-col items-center justify-center py-16 px-8 text-center"
        >
          <div class="w-16 h-16 mx-auto mb-4 rounded-xl bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] opacity-60 flex items-center justify-center">
            <span class="text-2xl">📊</span>
          </div>
          <h3 class="text-lg font-semibold text-text-primary mb-2">暂无对比结果</h3>
          <p class="text-sm text-text-muted leading-relaxed">
            在论文 tab 中使用批量模式选择论文进行对比分析
          </p>
        </div>
      </template>
      <div v-else class="flex items-center justify-center py-12">
        <svg class="animate-spin h-8 w-8 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
      </div>
    </div>

    <!-- ========== Bottom bars ========== -->

    <!-- Stats bar (non-batch) -->
    <div v-if="!batchMode" class="shrink-0 px-4 py-2.5 border-t border-border bg-bg-card">
      <span class="text-xs text-text-muted">共 {{ totalPapers }} 篇论文</span>
    </div>

    <!-- Batch action bar -->
    <div
      v-if="batchMode && activeTab === 'papers'"
      class="shrink-0 px-4 py-3 border-t border-border bg-bg-card safe-area-bottom"
    >
      <div class="flex items-center justify-between mb-2.5">
        <span class="text-sm font-medium text-text-primary">已选 {{ checkedPapers.size }} 篇</span>
        <button
          class="text-sm text-text-muted bg-transparent border-none"
          @click="toggleBatchMode"
        >取消</button>
      </div>
      <div class="flex items-center gap-3">
        <button
          :disabled="!hasChecked"
          class="flex-1 py-2.5 rounded-xl text-sm font-semibold border-none transition-opacity"
          :class="hasChecked
            ? 'text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036]'
            : 'text-text-muted bg-bg-elevated'"
          @click="startBatchMove"
        >移动到...</button>
        <button
          :disabled="!canCompare"
          class="flex-1 py-2.5 rounded-xl text-sm font-semibold border-none transition-opacity flex items-center justify-center gap-1.5"
          :class="canCompare
            ? 'text-white bg-gradient-to-r from-[#6366f1] to-[#8b5cf6]'
            : 'text-text-muted bg-bg-elevated'"
          @click="startCompare"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          对比分析
        </button>
      </div>
    </div>

    <!-- ========== Overlays ========== -->

    <!-- Rename folder dialog -->
    <Teleport to="body">
      <div v-if="renamingFolder" class="fixed inset-0 z-[9998] bg-black/50 flex items-center justify-center" @click.self="renamingFolder = null">
        <div class="w-[85vw] max-w-[320px] bg-bg-card rounded-2xl overflow-hidden">
          <div class="px-5 py-4 border-b border-border">
            <h3 class="text-base font-semibold text-text-primary">重命名文件夹</h3>
          </div>
          <div class="px-5 py-4">
            <input
              v-model="renamingFolderName"
              class="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink"
              autofocus
              @keydown.enter="confirmRenameFolder"
            />
          </div>
          <div class="flex border-t border-border">
            <button
              class="flex-1 py-3.5 text-base text-text-muted bg-transparent border-none border-r border-border"
              @click="renamingFolder = null"
            >取消</button>
            <button
              class="flex-1 py-3.5 text-base font-semibold text-tinder-pink bg-transparent border-none"
              @click="confirmRenameFolder"
            >确认</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Rename paper dialog -->
    <Teleport to="body">
      <div v-if="renamingPaper" class="fixed inset-0 z-[9998] bg-black/50 flex items-center justify-center" @click.self="renamingPaper = null">
        <div class="w-[85vw] max-w-[320px] bg-bg-card rounded-2xl overflow-hidden">
          <div class="px-5 py-4 border-b border-border">
            <h3 class="text-base font-semibold text-text-primary">重命名论文</h3>
          </div>
          <div class="px-5 py-4">
            <input
              v-model="renamingPaperTitle"
              class="w-full bg-bg-elevated border border-border rounded-xl px-4 py-3 text-base text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink"
              autofocus
              @keydown.enter="confirmRenamePaper"
            />
          </div>
          <div class="flex border-t border-border">
            <button
              class="flex-1 py-3.5 text-base text-text-muted bg-transparent border-none border-r border-border"
              @click="renamingPaper = null"
            >取消</button>
            <button
              class="flex-1 py-3.5 text-base font-semibold text-tinder-pink bg-transparent border-none"
              @click="confirmRenamePaper"
            >确认</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Action Sheet -->
    <ActionSheet
      v-if="showActionSheet"
      :items="actionSheetItems"
      :title="actionSheetTitle"
      @select="handleActionSelect"
      @close="showActionSheet = false"
    />

    <!-- Folder Picker -->
    <FolderPickerSheet
      v-if="showFolderPicker"
      :folders="allFolders"
      :title="folderPickerTitle"
      @select="handleMoveTo"
      @cancel="showFolderPicker = false"
    />
  </div>
</template>
