<script setup lang="ts">
import { ref } from 'vue'
import type { KbFolder, KbPaper, KbNote } from '../types/paper'

defineProps<{
  folder: KbFolder
  depth: number
  expandedFolders: Set<number>
  activeFolderId: number | null
  renamingFolderId: number | null
  renamingFolderName: string
  showNewFolderInput: boolean
  newFolderParentId: number | null
  checkedPapers: Set<string>
  batchMode: boolean
  expandedPapers: Set<string>
  paperNotes: Map<string, KbNote[]>
  renamingPaperId?: string | null
  renamingPaperTitle?: string
}>()

const emit = defineEmits<{
  'toggle-folder': [id: number]
  'select-folder': [id: number]
  'open-folder-menu': [e: MouseEvent, folder: KbFolder]
  'open-paper-menu': [e: MouseEvent, paper: KbPaper]
  'open-paper': [paperId: string]
  'toggle-check': [paperId: string]
  'update:renaming-name': [name: string]
  'confirm-rename': []
  'cancel-rename': []
  'update:new-folder-name': [name: string]
  'confirm-new-folder': []
  'cancel-new-folder': []
  'toggle-paper': [paperId: string]
  'create-note': [paperId: string]
  'upload-file': [paperId: string]
  'add-link': [paperId: string]
  'open-note': [payload: { id: number; paperId: string }]
  'open-pdf': [payload: { paperId: string; filePath: string; title: string }]
  'delete-note': [noteId: number]
  'update:renaming-paper-title': [title: string]
  'confirm-rename-paper': []
  'cancel-rename-paper': []
}>()

// Per-paper add dropdown
const addMenuPaperId = ref<string | null>(null)

function toggleAddMenu(paperId: string) {
  addMenuPaperId.value = addMenuPaperId.value === paperId ? null : paperId
}

function closeAddMenu() {
  addMenuPaperId.value = null
}

function handleCreateNote(paperId: string) {
  closeAddMenu()
  emit('create-note', paperId)
}

function handleUploadFile(paperId: string) {
  closeAddMenu()
  emit('upload-file', paperId)
}

function handleAddLink(paperId: string) {
  closeAddMenu()
  emit('add-link', paperId)
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
    const isPdf =
      (note.mime_type || '').toLowerCase() === 'application/pdf' ||
      note.file_path.toLowerCase().endsWith('.pdf') ||
      (note.title || '').toLowerCase().endsWith('.pdf')
    if (isPdf) {
      emit('open-pdf', {
        paperId: note.paper_id,
        filePath: note.file_path,
        title: note.title,
      })
      return
    }
    window.open(`/static/kb_files/${note.file_path}`, '_blank')
  } else {
    emit('open-note', { id: note.id, paperId: note.paper_id })
  }
}

function avatarColor(paperId: string): string {
  let hash = 0
  for (let i = 0; i < paperId.length; i++) {
    hash = paperId.charCodeAt(i) + ((hash << 5) - hash)
  }
  return `hsl(${Math.abs(hash % 360)}, 60%, 35%)`
}
</script>

<template>
  <div @click.stop>
    <!-- Folder row -->
    <div
      class="flex items-center gap-2 px-2 py-3 rounded-xl cursor-pointer transition-colors group"
      :class="activeFolderId === folder.id ? 'bg-tinder-blue/8' : 'hover:bg-bg-hover'"
      :style="{ paddingLeft: (8 + depth * 14) + 'px' }"
      @click="emit('select-folder', folder.id)"
    >
      <!-- Expand toggle -->
      <button
        class="w-5 h-5 flex items-center justify-center text-[10px] text-text-muted bg-transparent border-none cursor-pointer shrink-0 transition-transform duration-150"
        :class="expandedFolders.has(folder.id) ? 'rotate-90' : ''"
        @click.stop="emit('toggle-folder', folder.id)"
      >▶</button>

      <!-- Book icon -->
      <svg class="shrink-0" width="33" height="40" viewBox="0 0 24 24" fill="none">
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v15H6.5A2.5 2.5 0 0 0 4 19.5Z" fill="#3b82f6" stroke="#60a5fa" stroke-width="0.75"/>
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20v5H6.5A2.5 2.5 0 0 1 4 19.5Z" fill="#2563eb" stroke="#60a5fa" stroke-width="0.75"/>
        <path d="M9 7h6" stroke="#dbeafe" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M9 10.5h4" stroke="#dbeafe" stroke-width="1.5" stroke-linecap="round"/>
      </svg>

      <!-- Folder name (or rename input) -->
      <template v-if="renamingFolderId === folder.id">
        <input
          :value="renamingFolderName"
          @input="emit('update:renaming-name', ($event.target as HTMLInputElement).value)"
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-tinder-blue/50"
          autofocus
          @keydown.enter="emit('confirm-rename')"
          @keydown.escape="emit('cancel-rename')"
          @blur="emit('confirm-rename')"
          @click.stop
        />
      </template>
      <template v-else>
        <div class="flex-1 min-w-0">
          <span
            class="text-sm font-medium truncate block"
            :class="activeFolderId === folder.id ? 'text-tinder-blue' : 'text-text-primary'"
          >{{ folder.name }}</span>
          <span v-if="folder.papers?.length" class="text-[10px] text-text-muted">{{ folder.papers.length }} 篇论文</span>
        </div>
        <!-- Menu -->
        <button
          class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-xs"
          @click.stop="emit('open-folder-menu', $event, folder)"
        >⋯</button>
      </template>
    </div>

    <!-- Expanded content -->
    <div v-if="expandedFolders.has(folder.id)">
      <!-- New subfolder input -->
      <div
        v-if="showNewFolderInput && newFolderParentId === folder.id"
        class="flex items-center gap-2 py-2"
        :style="{ paddingLeft: (22 + (depth + 1) * 14) + 'px' }"
      >
        <svg class="shrink-0" width="33" height="40" viewBox="0 0 24 24" fill="none" opacity="0.5">
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v15H6.5A2.5 2.5 0 0 0 4 19.5Z" fill="#3b82f6" stroke="#60a5fa" stroke-width="0.75"/>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20v5H6.5A2.5 2.5 0 0 1 4 19.5Z" fill="#2563eb" stroke="#60a5fa" stroke-width="0.75"/>
        </svg>
        <input
          class="flex-1 bg-bg-elevated border border-border rounded px-2 py-1 text-sm text-text-primary focus:outline-none focus:border-tinder-blue/50"
          placeholder="文件夹名称..."
          autofocus
          @input="emit('update:new-folder-name', ($event.target as HTMLInputElement).value)"
          @keydown.enter="emit('confirm-new-folder')"
          @keydown.escape="emit('cancel-new-folder')"
          @blur="emit('confirm-new-folder')"
        />
      </div>

      <!-- Child folders (recursive) -->
      <SidebarFolder
        v-for="child in folder.children"
        :key="child.id"
        :folder="child"
        :depth="depth + 1"
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
        @toggle-folder="(id: number) => emit('toggle-folder', id)"
        @select-folder="(id: number) => emit('select-folder', id)"
        @open-folder-menu="(ev: MouseEvent, f: KbFolder) => emit('open-folder-menu', ev, f)"
        @open-paper-menu="(ev: MouseEvent, p: KbPaper) => emit('open-paper-menu', ev, p)"
        @open-paper="(id: string) => emit('open-paper', id)"
        @toggle-check="(id: string) => emit('toggle-check', id)"
        @update:renaming-name="(n: string) => emit('update:renaming-name', n)"
        @confirm-rename="emit('confirm-rename')"
        @cancel-rename="emit('cancel-rename')"
        @update:new-folder-name="(n: string) => emit('update:new-folder-name', n)"
        @confirm-new-folder="emit('confirm-new-folder')"
        @cancel-new-folder="emit('cancel-new-folder')"
        @toggle-paper="(id: string) => emit('toggle-paper', id)"
        @create-note="(id: string) => emit('create-note', id)"
        @upload-file="(id: string) => emit('upload-file', id)"
        @add-link="(id: string) => emit('add-link', id)"
        @open-note="(payload) => emit('open-note', payload)"
        @open-pdf="(payload) => emit('open-pdf', payload)"
        @delete-note="(id: number) => emit('delete-note', id)"
        @update:renaming-paper-title="(t: string) => emit('update:renaming-paper-title', t)"
        @confirm-rename-paper="emit('confirm-rename-paper')"
        @cancel-rename-paper="emit('cancel-rename-paper')"
      />

      <!-- Papers inside folder -->
      <div
        v-for="paper in folder.papers"
        :key="paper.paper_id"
      >
        <!-- Paper row -->
        <div
          class="flex items-center gap-2 py-1.5 rounded-lg hover:bg-bg-hover transition-colors group"
          :style="{ paddingLeft: (22 + (depth + 1) * 14) + 'px', paddingRight: '8px' }"
        >
          <!-- Batch checkbox -->
          <label
            v-if="batchMode"
            class="kb-checkbox shrink-0"
            @click.stop
          >
            <input
              type="checkbox"
              :checked="checkedPapers.has(paper.paper_id)"
              @change="emit('toggle-check', paper.paper_id)"
            />
            <span class="kb-checkbox-mark"></span>
          </label>

          <!-- Expand arrow (when paper has notes) -->
          <button
            v-if="(paper.note_count ?? 0) > 0"
            class="w-4 h-4 flex items-center justify-center text-[8px] text-text-muted bg-transparent border-none cursor-pointer shrink-0 transition-transform duration-150"
            :class="expandedPapers.has(paper.paper_id) ? 'rotate-90' : ''"
            @click.stop="emit('toggle-paper', paper.paper_id)"
          >▶</button>
          <div v-else class="w-4 shrink-0"></div>

          <!-- Inline rename for paper -->
          <template v-if="renamingPaperId === paper.paper_id">
            <div
              class="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-white text-[9px] font-bold"
              :style="{ background: avatarColor(paper.paper_id) }"
            >{{ (paper.paper_data?.institution || '?').slice(0, 2) }}</div>
            <input
              :value="renamingPaperTitle"
              @input="emit('update:renaming-paper-title', ($event.target as HTMLInputElement).value)"
              class="flex-1 bg-bg-elevated border border-border rounded px-2 py-0.5 text-[11px] text-text-primary focus:outline-none focus:border-tinder-pink/50 min-w-0"
              autofocus
              @keydown.enter="emit('confirm-rename-paper')"
              @keydown.escape="emit('cancel-rename-paper')"
              @blur="emit('confirm-rename-paper')"
              @click.stop
            />
          </template>
          <button
            v-else
            class="flex-1 flex items-center gap-2 min-w-0 bg-transparent border-none cursor-pointer text-left p-0"
            @click="emit('open-paper', paper.paper_id)"
          >
            <div
              class="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-white text-[9px] font-bold"
              :style="{ background: avatarColor(paper.paper_id) }"
            >{{ (paper.paper_data?.institution || '?').slice(0, 2) }}</div>
            <div class="min-w-0 flex-1">
              <div class="text-[11px] font-medium text-text-primary truncate">{{ paper.paper_data?.short_title }}</div>
              <div class="text-[10px] text-text-muted truncate">{{ paper.paper_data?.institution }} · {{ paper.paper_id }}</div>
            </div>
          </button>

          <!-- + Add button -->
          <div class="relative shrink-0">
            <button
              class="w-5 h-5 flex items-center justify-center text-text-muted hover:text-tinder-green bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-xs"
              @click.stop="toggleAddMenu(paper.paper_id)"
              title="添加笔记/文件"
            >+</button>

            <!-- Add dropdown -->
            <div
              v-if="addMenuPaperId === paper.paper_id"
              class="absolute right-0 top-6 z-50 w-36 bg-bg-elevated border border-border rounded-lg shadow-lg py-1 text-xs"
              @click.stop
            >
              <button
                class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                @click="handleCreateNote(paper.paper_id)"
              >
                <span>📝</span> 新建笔记
              </button>
              <button
                class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                @click="handleUploadFile(paper.paper_id)"
              >
                <span>📎</span> 上传文件
              </button>
              <button
                class="w-full text-left px-3 py-2 hover:bg-bg-hover text-text-primary border-none bg-transparent cursor-pointer flex items-center gap-2 transition-colors"
                @click="handleAddLink(paper.paper_id)"
              >
                <span>🔗</span> 添加链接
              </button>
            </div>
          </div>

          <!-- ⋯ Menu button -->
          <button
            class="shrink-0 w-5 h-5 flex items-center justify-center text-text-muted hover:text-text-primary bg-transparent border-none cursor-pointer rounded opacity-0 group-hover:opacity-100 transition-opacity text-xs"
            @click.stop="emit('open-paper-menu', $event, paper)"
          >⋯</button>
        </div>

        <!-- Expanded notes/files under paper -->
        <div v-if="expandedPapers.has(paper.paper_id) && paperNotes.has(paper.paper_id)">
          <div
            v-for="note in paperNotes.get(paper.paper_id)"
            :key="note.id"
            class="flex items-center gap-2 py-1.5 rounded hover:bg-bg-hover transition-colors group/note cursor-pointer"
            :style="{ paddingLeft: (36 + (depth + 2) * 14) + 'px', paddingRight: '8px' }"
            @click="onNoteClick(note)"
          >
            <span class="text-xs shrink-0">{{ noteIcon(note.type) }}</span>
            <span class="text-xs text-text-secondary truncate flex-1">{{ note.title }}</span>
            <button
              class="shrink-0 w-4 h-4 flex items-center justify-center text-text-muted hover:text-tinder-pink bg-transparent border-none cursor-pointer rounded opacity-0 group-hover/note:opacity-100 transition-opacity text-[10px]"
              @click.stop="emit('delete-note', note.id)"
              title="删除"
            >✕</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
