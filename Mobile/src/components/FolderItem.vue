<script setup lang="ts">
import { ref } from 'vue'
import type { KbFolder, KbPaper, KbNote } from '../types/paper'
import PaperMiniCard from './PaperMiniCard.vue'

const props = defineProps<{
  folder: KbFolder
  batchMode?: boolean
  checkedPapers?: Set<string>
  expandedPapers?: Set<string>
  paperNotes?: Map<string, KbNote[]>
}>()

const emit = defineEmits<{
  (e: 'tap-paper', paperId: string): void
  (e: 'remove-paper', paperId: string): void
  (e: 'paper-menu', paper: KbPaper): void
  (e: 'folder-menu', folder: KbFolder): void
  (e: 'toggle-check', paperId: string): void
  (e: 'toggle-expand', paperId: string): void
  (e: 'create-note', paperId: string): void
  (e: 'upload-file', paperId: string): void
  (e: 'add-link', paperId: string): void
  (e: 'open-note', note: KbNote): void
  (e: 'delete-note', noteId: number): void
}>()

const expanded = ref(false)

function toggle() {
  expanded.value = !expanded.value
}

const paperCount = (() => {
  let count = props.folder.papers?.length ?? 0
  function countChildren(folders: KbFolder[]) {
    for (const f of folders) {
      count += f.papers?.length ?? 0
      if (f.children?.length) countChildren(f.children)
    }
  }
  if (props.folder.children?.length) countChildren(props.folder.children)
  return count
})()
</script>

<template>
  <div>
    <!-- Folder header -->
    <div
      class="flex items-center gap-3 px-4 py-3.5 bg-transparent active:bg-bg-hover transition-colors"
      @click="toggle"
    >
      <!-- Expand icon -->
      <svg
        xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        class="shrink-0 text-text-muted transition-transform duration-200"
        :class="expanded ? 'rotate-90' : ''"
      >
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <!-- Folder icon -->
      <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="shrink-0 text-tinder-gold">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
      </svg>
      <span class="flex-1 text-base font-medium text-text-primary truncate">{{ folder.name }}</span>
      <span class="text-xs text-text-muted mr-1">{{ paperCount }}</span>
      <!-- Folder menu button -->
      <button
        class="shrink-0 w-7 h-7 flex items-center justify-center text-text-muted bg-transparent border-none rounded-full active:bg-bg-hover"
        @click.stop="$emit('folder-menu', folder)"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <circle cx="12" cy="5" r="2"/>
          <circle cx="12" cy="12" r="2"/>
          <circle cx="12" cy="19" r="2"/>
        </svg>
      </button>
    </div>

    <!-- Expanded content -->
    <div v-if="expanded" class="pl-7 pb-2 space-y-2">
      <!-- Sub-folders -->
      <FolderItem
        v-for="child in folder.children"
        :key="child.id"
        :folder="child"
        :batch-mode="batchMode"
        :checked-papers="checkedPapers"
        :expanded-papers="expandedPapers"
        :paper-notes="paperNotes"
        @tap-paper="$emit('tap-paper', $event)"
        @remove-paper="$emit('remove-paper', $event)"
        @paper-menu="$emit('paper-menu', $event)"
        @folder-menu="$emit('folder-menu', $event)"
        @toggle-check="$emit('toggle-check', $event)"
        @toggle-expand="$emit('toggle-expand', $event)"
        @create-note="$emit('create-note', $event)"
        @upload-file="$emit('upload-file', $event)"
        @add-link="$emit('add-link', $event)"
        @open-note="$emit('open-note', $event)"
        @delete-note="$emit('delete-note', $event)"
      />
      <!-- Papers -->
      <div class="space-y-2 px-2">
        <PaperMiniCard
          v-for="p in folder.papers"
          :key="p.paper_id"
          :paper="p"
          :batch-mode="batchMode"
          :checked="checkedPapers?.has(p.paper_id)"
          :expanded="expandedPapers?.has(p.paper_id)"
          :notes="paperNotes?.get(p.paper_id)"
          @tap="$emit('tap-paper', $event)"
          @remove="$emit('remove-paper', $event)"
          @menu="$emit('paper-menu', $event)"
          @toggle-check="$emit('toggle-check', $event)"
          @toggle-expand="$emit('toggle-expand', $event)"
          @create-note="$emit('create-note', $event)"
          @upload-file="$emit('upload-file', $event)"
          @add-link="$emit('add-link', $event)"
          @open-note="$emit('open-note', $event)"
          @delete-note="$emit('delete-note', $event)"
        />
      </div>
      <!-- Empty -->
      <div v-if="!folder.children?.length && !folder.papers?.length" class="text-sm text-text-muted py-2 px-4">
        空文件夹
      </div>
    </div>
  </div>
</template>
