<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KbTree, KbFolder, KbPaper, KbMenuItem, KbNote } from '../types/paper'
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
  fetchNotes,
  createNote,
  uploadNoteFile,
  addNoteLink,
  deleteNote as apiDeleteNote,
} from '../api'

const props = defineProps<{
  kbTree: KbTree
  activeFolderId: number | null
  selectedDate: string
  dates: string[]
}>()

const emit = defineEmits<{
  'update:selectedDate': [value: string]
  'update:activeFolderId': [value: number | null]
  openPaper: [paperId: string]
  openNote: [noteId: number]
  refresh: []
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
    await createKbFolder(name, newFolderParentId.value)
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
    await renameKbFolder(folderId, name)
    emit('refresh')
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
      { key: 'move', label: '移动到文件夹...' },
      { key: 'delete', label: '从知识库删除', danger: true },
    ],
    target: { type: 'paper' as const, paper },
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
        await deleteKbFolder(folder.id)
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
        await removeKbPaper(paper.paper_id)
        emit('refresh')
      } catch {}
    } else if (key === 'move') {
      movingPaperIds.value = [paper.paper_id]
      showFolderPicker.value = true
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
      await moveKbFolder(movingFolderId.value, targetId)
      emit('refresh')
    } catch {}
    movingFolderId.value = null
    return
  }

  if (movingPaperIds.value.length === 0) return
  try {
    await moveKbPapers(movingPaperIds.value, targetId)
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
    const res = await fetchNotes(paperId)
    const next = new Map(paperNotes.value)
    next.set(paperId, res.notes)
    paperNotes.value = next
  } catch {}
}

// ---- Note actions ----
async function handleCreateNote(paperId: string) {
  try {
    const note = await createNote(paperId)
    // expand and refresh notes
    const next = new Set(expandedPapers.value)
    next.add(paperId)
    expandedPapers.value = next
    await loadPaperNotes(paperId)
    emit('refresh')
    // navigate to the note editor
    emit('openNote', note.id)
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
    await uploadNoteFile(uploadTargetPaperId.value, file)
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
    await addNoteLink(paperId, title, url)
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

function onNoteClick(note: KbNote) {
  if (note.type === 'link' && note.file_url) {
    window.open(note.file_url, '_blank')
  } else if (note.type === 'file' && note.file_path) {
    window.open(`/static/kb_files/${note.file_path}`, '_blank')
  } else {
    emit('openNote', note.id)
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

defineExpose({ refreshAllExpandedNotes })
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

      <!-- Knowledge base header + buttons -->
      <div class="flex items-center justify-between">
        <div class="flex gap-4 text-sm font-semibold">
          <span
            class="pb-1 cursor-pointer transition-colors"
            :class="activeFolderId === null
              ? 'text-tinder-pink border-b-2 border-tinder-pink'
              : 'text-text-muted hover:text-text-secondary'"
            @click="selectFolder(null)"
          >知识库</span>
        </div>
        <div class="flex items-center gap-2">
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

    <!-- Tree content -->
    <div class="flex-1 overflow-y-auto p-2" @click="selectFolder(null)">
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
        @open-note="(id: number) => emit('openNote', id)"
        @delete-note="handleDeleteNote"
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

            <!-- Paper content -->
            <button
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
                class="shrink-0 w-4 h-4 flex items-center justify-center text-text-muted hover:text-tinder-pink bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/note:opacity-100 transition-opacity text-[10px]"
                @click.stop="handleDeleteNote(note.id)"
                title="删除"
              >✕</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="kbTree.folders.length === 0 && kbTree.papers.length === 0" class="text-center py-8">
        <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-gradient-to-br from-[#fd267a] to-[#ff6036] opacity-60"></div>
        <p class="text-sm font-semibold text-text-primary mb-1">开始浏览</p>
        <p class="text-xs text-text-muted leading-relaxed px-4">
          当你对论文点赞后，它们会在这里出现。
        </p>
      </div>
    </div>

    <!-- Batch action bar -->
    <div
      v-if="batchMode"
      class="px-3 py-2.5 border-t border-border bg-bg-elevated flex items-center justify-between"
    >
      <span class="text-xs text-text-muted">已选 {{ checkedPapers.size }} 篇</span>
      <div class="flex items-center gap-2">
        <button
          :disabled="!hasChecked"
          class="px-3 py-1 rounded-full text-xs font-medium border-none cursor-pointer transition-opacity"
          :class="hasChecked
            ? 'text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] hover:opacity-90'
            : 'text-text-muted bg-bg-hover cursor-not-allowed'"
          @click="startBatchMove"
        >移动到...</button>
        <button
          class="px-3 py-1 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
          @click="toggleBatchMode"
        >取消</button>
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
