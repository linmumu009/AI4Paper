<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KbTree, KbFolder, KbPaper, KbMenuItem, KbNote, KbCompareResult, KbCompareResultsTree, KbCompareFolder } from '../types/paper'
import KbContextMenu from './KbContextMenu.vue'
import FolderPickerDialog from './FolderPickerDialog.vue'
import SidebarFolder from './SidebarFolder.vue'
import {
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
  renameCompareResult as apiRenameCompare,
  deleteCompareResult as apiDeleteCompare,
  moveCompareResult as apiMoveCompare,
} from '../api'
import type { KbScope } from '../api'

const props = withDefaults(defineProps<{
  kbTree: KbTree
  compareTree: KbCompareResultsTree | null
  activeFolderId: number | null
  selectedDate: string
  dates: string[]
  title?: string
  emptyTitle?: string
  emptyDesc?: string
  scope?: KbScope
}>(), {
  title: '知识库',
  emptyTitle: '开始浏览',
  emptyDesc: '当你对论文点赞后，它们会在这里出现。',
  scope: 'kb',
  compareTree: null,
})

// ---- Tab switching ----
type SidebarTab = 'papers' | 'compare'
const activeTab = ref<SidebarTab>('papers')

const emit = defineEmits<{
  'update:selectedDate': [value: string]
  'update:activeFolderId': [value: number | null]
  openPaper: [paperId: string]
  openNote: [payload: { id: number; paperId: string }]
  openPdf: [payload: { paperId: string; filePath: string; title: string }]
  compare: [paperIds: string[]]
  refresh: []
  openCompareResult: [resultId: number]
  refreshCompare: []
}>()

// ---- Folder expand/collapse state ----
const expandedFolders = ref<Set<number>>(new Set())

function toggleFolder(folderId: number) {
  const next = new Set(expandedFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedFolders.value = next
}

function selectFolder(folderId: number | null) {
  emit('update:activeFolderId', folderId)
  if (folderId !== null) {
    const next = new Set(expandedFolders.value)
    next.add(folderId)
    expandedFolders.value = next
  }
}

// ---- New folder ----
const showNewFolderInput = ref(false)
const newFolderName = ref('')
const newFolderParentId = ref<number | null>(null)
let _creatingFolder = false

function startNewFolder(parentId: number | null = null) {
  newFolderParentId.value = parentId
  newFolderName.value = ''
  _creatingFolder = false
  showNewFolderInput.value = true
  if (parentId !== null) {
    const next = new Set(expandedFolders.value)
    next.add(parentId)
    expandedFolders.value = next
  }
}

async function confirmNewFolder() {
  if (_creatingFolder) return
  _creatingFolder = true
  const name = newFolderName.value.trim()
  showNewFolderInput.value = false
  if (!name) return
  try {
    await createKbFolder(name, newFolderParentId.value, props.scope)
    emit('refresh')
  } catch {}
}

// ---- Rename folder ----
const renamingFolderId = ref<number | null>(null)
const renamingFolderName = ref('')
let _renamingFolder = false

function startRenameFolder(folder: KbFolder) {
  renamingFolderId.value = folder.id
  renamingFolderName.value = folder.name
  _renamingFolder = false
}

async function confirmRenameFolder() {
  if (_renamingFolder) return
  _renamingFolder = true
  const folderId = renamingFolderId.value
  if (folderId === null) return
  const name = renamingFolderName.value.trim()
  renamingFolderId.value = null
  if (!name) return
  try {
    await renameKbFolder(folderId, name, props.scope)
    emit('refresh')
  } catch {}
}

// ---- Rename paper ----
const renamingPaperId = ref<string | null>(null)
const renamingPaperTitle = ref('')
let _renamingPaper = false

function startRenamePaper(paper: KbPaper) {
  renamingPaperId.value = paper.paper_id
  renamingPaperTitle.value = paper.paper_data.short_title || paper.paper_id
  _renamingPaper = false
}

async function confirmRenamePaper() {
  if (_renamingPaper) return
  _renamingPaper = true
  const paperId = renamingPaperId.value
  if (!paperId) return
  const title = renamingPaperTitle.value.trim()
  renamingPaperId.value = null
  if (!title) return
  try {
    await renameKbPaper(paperId, title, props.scope)
    emit('refresh')
  } catch {}
}

// ---- Compare result management ----
const expandedCompareFolders = ref<Set<number>>(new Set())

function toggleCompareFolder(folderId: number) {
  const next = new Set(expandedCompareFolders.value)
  if (next.has(folderId)) next.delete(folderId)
  else next.add(folderId)
  expandedCompareFolders.value = next
}

const renamingCompareId = ref<number | null>(null)
const renamingCompareTitle = ref('')
let _renamingCompare = false

function startRenameCompare(result: KbCompareResult) {
  renamingCompareId.value = result.id
  renamingCompareTitle.value = result.title
  _renamingCompare = false
}

async function confirmRenameCompare() {
  if (_renamingCompare) return
  _renamingCompare = true
  const id = renamingCompareId.value
  if (id === null) return
  const title = renamingCompareTitle.value.trim()
  renamingCompareId.value = null
  if (!title) return
  try {
    await apiRenameCompare(id, title)
    emit('refreshCompare')
  } catch {}
}

async function deleteCompareResult(id: number) {
  try {
    await apiDeleteCompare(id)
    emit('refreshCompare')
  } catch {}
}

// ---- Context menu ----
const contextMenu = ref<{ x: number; y: number; items: KbMenuItem[]; target: any } | null>(null)

function openFolderMenu(e: MouseEvent, folder: KbFolder) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'new-subfolder', label: '新建子文件夹' },
      { key: 'rename', label: '重命名' },
      { key: 'move-folder', label: '移动到...' },
      { key: 'delete', label: '删除文件夹', danger: true },
    ],
    target: { type: 'folder' as const, folder },
  }
}

function openPaperMenu(e: MouseEvent, paper: KbPaper) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'rename-paper', label: '重命名' },
      { key: 'move', label: '移动到文件夹...' },
      { key: 'delete', label: '从知识库删除', danger: true },
    ],
    target: { type: 'paper' as const, paper },
  }
}

function openCompareResultMenu(e: MouseEvent, result: KbCompareResult) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'rename-compare', label: '重命名' },
      { key: 'delete-compare', label: '删除', danger: true },
    ],
    target: { type: 'compare-result' as const, result },
  }
}

async function handleContextMenuSelect(key: string) {
  if (!contextMenu.value) return
  const { target } = contextMenu.value

  if (target.type === 'folder') {
    const folder = target.folder as KbFolder
    if (key === 'rename') {
      startRenameFolder(folder)
    } else if (key === 'delete') {
      try {
        await deleteKbFolder(folder.id, props.scope)
        if (props.activeFolderId === folder.id) {
          emit('update:activeFolderId', null)
        }
        emit('refresh')
      } catch {}
    } else if (key === 'new-subfolder') {
      startNewFolder(folder.id)
    } else if (key === 'move-folder') {
      movingFolderId.value = folder.id
      movingPaperIds.value = []
      folderPickerTitle.value = `移动"${folder.name}"到...`
      showFolderPicker.value = true
    }
  }

  if (target.type === 'paper') {
    const paper = target.paper as KbPaper
    if (key === 'delete') {
      try {
        await removeKbPaper(paper.paper_id, props.scope)
        emit('refresh')
      } catch {}
    } else if (key === 'move') {
      movingPaperIds.value = [paper.paper_id]
      showFolderPicker.value = true
    } else if (key === 'rename-paper') {
      startRenamePaper(paper)
    }
  }

  if (target.type === 'note') {
    const note = target.note as KbNote
    if (key === 'delete') {
      await handleDeleteNote(note.id)
    }
  }

  if (target.type === 'compare-result') {
    const result = target.result as KbCompareResult
    if (key === 'rename-compare') {
      startRenameCompare(result)
    } else if (key === 'delete-compare') {
      await deleteCompareResult(result.id)
    }
  }
}

// ---- Batch mode toggle ----
const batchMode = ref(false)

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    checkedPapers.value = new Set()
  }
}

// ---- Checkbox multi-select ----
const checkedPapers = ref<Set<string>>(new Set())

function toggleCheck(paperId: string) {
  const next = new Set(checkedPapers.value)
  if (next.has(paperId)) next.delete(paperId)
  else next.add(paperId)
  checkedPapers.value = next
}

const hasChecked = computed(() => checkedPapers.value.size > 0)
const canCompare = computed(() => checkedPapers.value.size >= 2 && checkedPapers.value.size <= 5)

function startCompare() {
  if (!canCompare.value) return
  const ids = [...checkedPapers.value]
  // Exit batch mode
  batchMode.value = false
  checkedPapers.value = new Set()
  emit('compare', ids)
}

// ---- Move (folder picker dialog) ----
const showFolderPicker = ref(false)
const movingPaperIds = ref<string[]>([])
const movingFolderId = ref<number | null>(null)
const folderPickerTitle = ref('')

function startBatchMove() {
  movingPaperIds.value = [...checkedPapers.value]
  movingFolderId.value = null
  folderPickerTitle.value = '移动论文到文件夹'
  showFolderPicker.value = true
}

async function handleMoveTo(targetId: number | null) {
  showFolderPicker.value = false

  if (movingFolderId.value !== null) {
    try {
      await moveKbFolder(movingFolderId.value, targetId, props.scope)
      emit('refresh')
    } catch {}
    movingFolderId.value = null
    return
  }

  if (movingPaperIds.value.length === 0) return
  try {
    await moveKbPapers(movingPaperIds.value, targetId, props.scope)
    checkedPapers.value = new Set()
    emit('refresh')
  } catch {}
  movingPaperIds.value = []
}

// ---- Color helper ----
function avatarColor(paperId: string): string {
  let hash = 0
  for (let i = 0; i < paperId.length; i++) {
    hash = paperId.charCodeAt(i) + ((hash << 5) - hash)
  }
  return `hsl(${Math.abs(hash % 360)}, 60%, 35%)`
}

const allFolders = computed(() => props.kbTree?.folders ?? [])

// ---- Paper expand / notes ----
const expandedPapers = ref<Set<string>>(new Set())
const paperNotes = ref<Map<string, KbNote[]>>(new Map())

async function togglePaper(paperId: string) {
  const next = new Set(expandedPapers.value)
  if (next.has(paperId)) {
    next.delete(paperId)
  } else {
    next.add(paperId)
    // load notes if not cached
    if (!paperNotes.value.has(paperId)) {
      await loadPaperNotes(paperId)
    }
  }
  expandedPapers.value = next
}

async function loadPaperNotes(paperId: string) {
  try {
    const res = await fetchNotes(paperId, props.scope)
    const next = new Map(paperNotes.value)
    next.set(paperId, res.notes)
    paperNotes.value = next
  } catch {}
}

// ---- Note actions ----
async function handleCreateNote(paperId: string) {
  try {
    const note = await createNote(paperId, '未命名笔记', '', props.scope)
    // expand and refresh notes
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    emit('refresh')
    // 打开右侧笔记编辑，同时携带所属论文 ID
    emit('openNote', { id: note.id, paperId })
  } catch {}
}

// Hidden file input ref
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadTargetPaperId = ref<string>('')

function handleUploadFile(paperId: string) {
  uploadTargetPaperId.value = paperId
  fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !uploadTargetPaperId.value) return
  try {
    await uploadNoteFile(uploadTargetPaperId.value, file, props.scope)
    const next = new Set(expandedPapers.value)
    next.add(uploadTargetPaperId.value)
    expandedPapers.value = next
    await loadPaperNotes(uploadTargetPaperId.value)
    emit('refresh')
  } catch {}
  // reset input
  input.value = ''
}

async function handleAddLink(paperId: string) {
  const url = window.prompt('请输入链接 URL')
  if (!url) return
  const title = window.prompt('链接标题（可选）') || url
  try {
    await addNoteLink(paperId, title, url, props.scope)
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    emit('refresh')
  } catch {}
}

async function handleDeleteNote(noteId: number) {
  try {
    await apiDeleteNote(noteId)
    // refresh all expanded papers' notes
    for (const pid of expandedPapers.value) {
      await loadPaperNotes(pid)
    }
    emit('refresh')
  } catch {}
}

function noteIcon(type: string): string {
  if (type === 'file') return '📎'
  if (type === 'link') return '🔗'
  return '📝'
}

function openNoteMenu(e: MouseEvent, note: KbNote) {
  e.stopPropagation()
  contextMenu.value = {
    x: e.clientX,
    y: e.clientY,
    items: [
      { key: 'delete', label: '删除笔记', danger: true },
    ],
    target: { type: 'note' as const, note },
  }
}

function onNoteClick(note: KbNote) {
  if (note.type === 'link' && note.file_url) {
    window.open(note.file_url, '_blank')
  } else if (note.type === 'file' && note.file_path) {
    const isPdf =
      (note.mime_type || '').toLowerCase() === 'application/pdf' ||
      note.file_path.toLowerCase().endsWith('.pdf') ||
      (note.title || '').toLowerCase().endsWith('.pdf')
    if (isPdf) {
      emit('openPdf', {
        paperId: note.paper_id,
        filePath: note.file_path,
        title: note.title,
      })
      return
    }
    window.open(`/static/kb_files/${note.file_path}`, '_blank')
  } else {
    emit('openNote', { id: note.id, paperId: note.paper_id })
  }
}

// Root-level paper add menu
const rootAddMenuPaperId = ref<string | null>(null)
function toggleRootAddMenu(paperId: string) {
  rootAddMenuPaperId.value = rootAddMenuPaperId.value === paperId ? null : paperId
}

// Expose method for parent to refresh notes after editing
async function refreshAllExpandedNotes() {
  for (const pid of expandedPapers.value) {
    await loadPaperNotes(pid)
  }
}

// 供父组件直接更新某条笔记的标题，避免必须依赖重新拉取列表
function updateNoteTitle(paperId: string, noteId: number, title: string) {
  const current = paperNotes.value.get(paperId)
  if (!current) return
  const nextNotes = current.map((n) =>
    n.id === noteId
      ? { ...n, title }
      : n,
  )
  const nextMap = new Map(paperNotes.value)
  nextMap.set(paperId, nextNotes)
  paperNotes.value = nextMap
}

defineExpose({ refreshAllExpandedNotes, updateNoteTitle })
</script>

<template>
  <aside class="w-72 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0">
    <!-- Hidden file input for uploads -->
    <input
      ref="fileInputRef"
      type="file"
      class="hidden"
      @change="onFileSelected"
    />

    <!-- Header: date selector -->
    <div class="p-4 border-b border-border">
      <div class="bg-gradient-to-r from-[#fd267a] to-[#ff6036] rounded-xl p-3 mb-3">
        <div class="text-xs font-bold text-white/80 mb-1">论文日报</div>
        <select
          :value="selectedDate"
          @change="$emit('update:selectedDate', ($event.target as HTMLSelectElement).value)"
          class="w-full bg-white/20 border-none rounded-lg px-2 py-1.5 text-white text-sm font-medium focus:outline-none cursor-pointer appearance-none"
        >
          <option v-for="d in dates" :key="d" :value="d" class="text-black">{{ d }}</option>
        </select>
      </div>

      <!-- Tab bar: papers / compare -->
      <div class="flex items-center justify-between">
        <div class="flex gap-4 text-sm font-semibold">
          <span
            class="pb-1 cursor-pointer transition-colors"
            :class="activeTab === 'papers'
              ? 'text-tinder-pink border-b-2 border-tinder-pink'
              : 'text-text-muted hover:text-text-secondary'"
            @click="activeTab = 'papers'; selectFolder(null)"
          >{{ title }}</span>
          <span
            class="pb-1 cursor-pointer transition-colors"
            :class="activeTab === 'compare'
              ? 'text-[#8b5cf6] border-b-2 border-[#8b5cf6]'
              : 'text-text-muted hover:text-text-secondary'"
            @click="activeTab = 'compare'"
          >对比库</span>
        </div>
        <div v-if="activeTab === 'papers'" class="flex items-center gap-2">
          <button
            class="text-xs px-1.5 py-0.5 rounded bg-transparent border cursor-pointer transition-colors"
            :class="batchMode
              ? 'border-tinder-pink/60 text-tinder-pink'
              : 'border-border text-text-muted hover:text-text-secondary hover:border-border-light'"
            title="批量操作"
            @click="toggleBatchMode"
          >批量</button>
          <button
            class="text-xs text-text-muted hover:text-tinder-pink bg-transparent border-none cursor-pointer transition-colors px-1"
            title="新建文件夹"
            @click="startNewFolder(activeFolderId)"
          >+ 文件夹</button>
        </div>
      </div>
    </div>

    <!-- ============ Papers tab ============ -->
    <div v-if="activeTab === 'papers'" class="flex-1 overflow-y-auto p-2" @click="selectFolder(null)">
      <!-- New folder input (root level) -->
      <div v-if="showNewFolderInput && newFolderParentId === null" class="flex items-center gap-2 px-2 py-2 mb-1">
        <svg class="shrink-0" width="33" height="40" viewBox="0 0 24 24" fill="none" opacity="0.5">
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v15H6.5A2.5 2.5 0 0 0 4 19.5Z" fill="#3b82f6" stroke="#60a5fa" stroke-width="0.75"/>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20v5H6.5A2.5 2.5 0 0 1 4 19.5Z" fill="#2563eb" stroke="#60a5fa" stroke-width="0.75"/>
        </svg>
        <input
          v-model="newFolderName"
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-tinder-blue/50"
          placeholder="文件夹名称..."
          autofocus
          @keydown.enter="confirmNewFolder"
          @keydown.escape="showNewFolderInput = false"
          @blur="confirmNewFolder"
        />
      </div>

      <!-- Folders -->
      <SidebarFolder
        v-for="folder in kbTree.folders"
        :key="folder.id"
        :folder="folder"
        :depth="0"
        :expanded-folders="expandedFolders"
        :active-folder-id="activeFolderId"
        :renaming-folder-id="renamingFolderId"
        :renaming-folder-name="renamingFolderName"
        :show-new-folder-input="showNewFolderInput"
        :new-folder-parent-id="newFolderParentId"
        :checked-papers="checkedPapers"
        :batch-mode="batchMode"
        :expanded-papers="expandedPapers"
        :paper-notes="paperNotes"
        :renaming-paper-id="renamingPaperId"
        :renaming-paper-title="renamingPaperTitle"
        @toggle-folder="toggleFolder"
        @select-folder="selectFolder"
        @open-folder-menu="openFolderMenu"
        @open-paper-menu="openPaperMenu"
        @open-paper="(id: string) => emit('openPaper', id)"
        @toggle-check="toggleCheck"
        @update:renaming-name="renamingFolderName = $event"
        @confirm-rename="confirmRenameFolder"
        @cancel-rename="renamingFolderId = null"
        @update:new-folder-name="newFolderName = $event"
        @confirm-new-folder="confirmNewFolder"
        @cancel-new-folder="showNewFolderInput = false"
        @toggle-paper="togglePaper"
        @create-note="handleCreateNote"
        @upload-file="handleUploadFile"
        @add-link="handleAddLink"
        @open-note="(payload) => emit('openNote', payload)"
        @open-pdf="(payload) => emit('openPdf', payload)"
        @delete-note="handleDeleteNote"
        @update:renaming-paper-title="renamingPaperTitle = $event"
        @confirm-rename-paper="confirmRenamePaper"
        @cancel-rename-paper="renamingPaperId = null"
      />

      <!-- Root papers -->
      <div v-if="kbTree.papers.length > 0" class="mt-1">
        <div
          v-for="paper in kbTree.papers"
          :key="paper.paper_id"
        >
          <!-- Paper row -->
          <div class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors group">
            <!-- Checkbox (only in batch mode) -->
            <label
              v-if="batchMode"
              class="kb-checkbox shrink-0"
              @click.stop
            >
              <input
                type="checkbox"
                :checked="checkedPapers.has(paper.paper_id)"
                @change="toggleCheck(paper.paper_id)"
              />
              <span class="kb-checkbox-mark"></span>
            </label>

            <!-- Expand arrow -->
            <button
              v-if="(paper.note_count ?? 0) > 0"
              class="w-4 h-4 flex items-center justify-center text-[8px] text-text-muted bg-transparent border-none cursor-pointer shrink-0 transition-transform duration-150"
              :class="expandedPapers.has(paper.paper_id) ? 'rotate-90' : ''"
              @click.stop="togglePaper(paper.paper_id)"
            >▶</button>
            <div v-else class="w-4 shrink-0"></div>

            <!-- Paper content (inline rename or normal) -->
            <template v-if="renamingPaperId === paper.paper_id">
              <div
                class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold"
                :style="{ background: avatarColor(paper.paper_id) }"
              >
                {{ (paper.paper_data.institution || '?').slice(0, 2) }}
              </div>
              <input
                v-model="renamingPaperTitle"
                class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-tinder-pink/50 min-w-0"
                autofocus
                @keydown.enter="confirmRenamePaper"
                @keydown.escape="renamingPaperId = null"
                @blur="confirmRenamePaper"
                @click.stop
              />
            </template>
            <button
              v-else
              class="flex-1 flex items-center gap-2 min-w-0 bg-transparent border-none cursor-pointer text-left p-0"
              @click="emit('openPaper', paper.paper_id)"
            >
              <div
                class="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold"
                :style="{ background: avatarColor(paper.paper_id) }"
              >
                {{ (paper.paper_data.institution || '?').slice(0, 2) }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-xs font-medium text-text-primary truncate">
                  {{ paper.paper_data.short_title }}
                </div>
                <div class="text-[10px] text-text-muted truncate">
                  {{ paper.paper_data.institution }} · {{ paper.paper_id }}
                </div>
              </div>
            </button>

            <!-- + Add button -->
            <div class="relative shrink-0">
              <button
                class="w-6 h-6 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
                @click.stop="toggleRootAddMenu(paper.paper_id)"
                title="添加笔记/文件"
              >+</button>

              <div
                v-if="rootAddMenuPaperId === paper.paper_id"
                class="absolute right-0 top-6 z-50 w-36 bg-bg-elevated border border-border rounded-lg shadow-lg py-1 text-xs"
                @click.stop
              >
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleCreateNote(paper.paper_id)"
                >
                  <span>📝</span> 新建笔记
                </button>
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleUploadFile(paper.paper_id)"
                >
                  <span>📎</span> 上传文件
                </button>
                <button
                  class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                  @click="rootAddMenuPaperId = null; handleAddLink(paper.paper_id)"
                >
                  <span>🔗</span> 添加链接
                </button>
              </div>
            </div>

            <!-- Menu button -->
            <button
              class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity"
              @click.stop="openPaperMenu($event, paper)"
            >⋯</button>
          </div>

          <!-- Expanded notes for root paper -->
          <div v-if="expandedPapers.has(paper.paper_id) && paperNotes.has(paper.paper_id)">
            <div
              v-for="note in paperNotes.get(paper.paper_id)"
              :key="note.id"
              class="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-bg-hover transition-colors group/note cursor-pointer"
              style="padding-left: 50px;"
              @click="onNoteClick(note)"
            >
              <span class="text-xs shrink-0">{{ noteIcon(note.type) }}</span>
              <span class="text-xs text-text-secondary truncate flex-1">{{ note.title }}</span>
              <button
                class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/note:opacity-100 transition-opacity"
                @click.stop="openNoteMenu($event, note)"
              >⋯</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="kbTree.folders.length === 0 && kbTree.papers.length === 0" class="text-center py-8">
        <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-gradient-to-br from-[#fd267a] to-[#ff6036] opacity-60"></div>
        <p class="text-sm font-semibold text-text-primary mb-1">{{ emptyTitle }}</p>
        <p class="text-xs text-text-muted leading-relaxed px-4">
          {{ emptyDesc }}
        </p>
      </div>
    </div>

    <!-- ============ Compare tab ============ -->
    <div v-if="activeTab === 'compare'" class="flex-1 overflow-y-auto p-2">
      <template v-if="compareTree">
        <!-- Compare folders -->
        <div
          v-for="folder in compareTree.folders"
          :key="folder.id"
          class="mb-1"
        >
          <div
            class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
            @click="toggleCompareFolder(folder.id)"
          >
            <span class="text-[8px] text-text-muted transition-transform duration-150" :class="expandedCompareFolders.has(folder.id) ? 'rotate-90' : ''">▶</span>
            <span class="text-xs">📁</span>
            <span class="text-xs font-medium text-text-primary truncate flex-1">{{ folder.name }}</span>
          </div>
          <div v-if="expandedCompareFolders.has(folder.id)" class="pl-4">
            <div
              v-for="result in folder.results"
              :key="result.id"
              class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
              @click="emit('openCompareResult', result.id)"
            >
              <span class="text-xs">📊</span>
              <template v-if="renamingCompareId === result.id">
                <input
                  v-model="renamingCompareTitle"
                  class="flex-1 bg-bg-elevated border border-border rounded px-2 py-0.5 text-xs text-text-primary focus:outline-none focus:border-[#8b5cf6]/50 min-w-0"
                  autofocus
                  @keydown.enter="confirmRenameCompare"
                  @keydown.escape="renamingCompareId = null"
                  @blur="confirmRenameCompare"
                  @click.stop
                />
              </template>
              <template v-else>
                <span class="text-xs text-text-primary truncate flex-1">{{ result.title }}</span>
                <span class="text-[10px] text-text-muted shrink-0">{{ result.paper_ids.length }}篇</span>
                <button
                  class="shrink-0 w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-xs"
                  @click.stop="openCompareResultMenu($event, result)"
                >⋯</button>
              </template>
            </div>
          </div>
        </div>

        <!-- Root compare results -->
        <div
          v-for="result in compareTree.results"
          :key="result.id"
          class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer group"
          @click="emit('openCompareResult', result.id)"
        >
          <span class="text-xs">📊</span>
          <template v-if="renamingCompareId === result.id">
            <input
              v-model="renamingCompareTitle"
              class="flex-1 bg-bg-elevated border border-border rounded px-2 py-0.5 text-xs text-text-primary focus:outline-none focus:border-[#8b5cf6]/50 min-w-0"
              autofocus
              @keydown.enter="confirmRenameCompare"
              @keydown.escape="renamingCompareId = null"
              @blur="confirmRenameCompare"
              @click.stop
            />
          </template>
          <template v-else>
            <span class="text-xs text-text-primary truncate flex-1">{{ result.title }}</span>
            <span class="text-[10px] text-text-muted shrink-0">{{ result.paper_ids.length }}篇</span>
            <button
              class="shrink-0 w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-xs"
              @click.stop="openCompareResultMenu($event, result)"
            >⋯</button>
          </template>
        </div>

        <!-- Empty compare state -->
        <div
          v-if="compareTree.folders.length === 0 && compareTree.results.length === 0"
          class="text-center py-8"
        >
          <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-gradient-to-br from-[#6366f1] to-[#8b5cf6] opacity-60 flex items-center justify-center">
            <span class="text-2xl">📊</span>
          </div>
          <p class="text-sm font-semibold text-text-primary mb-1">暂无对比结果</p>
          <p class="text-xs text-text-muted leading-relaxed px-4">
            在批量模式中选择论文进行对比分析后，<br/>
            点击「保存」将结果存入对比库。
          </p>
        </div>
      </template>
      <div v-else class="text-center py-8">
        <p class="text-xs text-text-muted">加载中...</p>
      </div>
    </div>

    <!-- Batch action bar (only in papers tab) -->
    <div
      v-if="batchMode && activeTab === 'papers'"
      class="px-3 py-2.5 border-t border-border bg-bg-elevated flex flex-col gap-2"
    >
      <div class="flex items-center justify-between">
        <span class="text-xs text-text-muted">已选 {{ checkedPapers.size }} 篇</span>
        <button
          class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="toggleBatchMode"
        >取消</button>
      </div>
      <div class="flex items-center gap-2">
        <button
          :disabled="!hasChecked"
          class="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity"
          :class="hasChecked
            ? 'text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          @click="startBatchMove"
        >移动到...</button>
        <button
          :disabled="!canCompare"
          class="flex-1 px-3 py-1.5 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity flex items-center justify-center gap-1"
          :class="canCompare
            ? 'text-white bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          :title="checkedPapers.size < 2 ? '请至少选择 2 篇论文' : checkedPapers.size > 5 ? '最多选择 5 篇论文' : '对比分析选中论文'"
          @click="startCompare"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          对比分析
        </button>
      </div>
    </div>

    <!-- Context menu -->
    <KbContextMenu
      v-if="contextMenu"
      :items="contextMenu.items"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @select="handleContextMenuSelect"
      @close="contextMenu = null"
    />

    <!-- Folder picker dialog -->
    <FolderPickerDialog
      v-if="showFolderPicker"
      :folders="allFolders"
      :title="folderPickerTitle"
      @select="handleMoveTo"
      @cancel="showFolderPicker = false"
    />
  </aside>
</template>
