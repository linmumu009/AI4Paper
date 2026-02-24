<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KbPaper, KbNote } from '../types/paper'

const props = defineProps<{
  paper: KbPaper
  batchMode?: boolean
  checked?: boolean
  expanded?: boolean
  notes?: KbNote[]
}>()

const emit = defineEmits<{
  (e: 'tap', paperId: string): void
  (e: 'remove', paperId: string): void
  (e: 'menu', paper: KbPaper): void
  (e: 'toggle-check', paperId: string): void
  (e: 'toggle-expand', paperId: string): void
  (e: 'create-note', paperId: string): void
  (e: 'upload-file', paperId: string): void
  (e: 'add-link', paperId: string): void
  (e: 'open-note', note: KbNote): void
  (e: 'delete-note', noteId: number): void
}>()

const showAddMenu = ref(false)

/** 显示的标题：使用推荐卡片正标题（short_title） */
const displayTitle = computed(() => {
  return props.paper.paper_data.short_title || '未命名论文'
})

const scoreClass = computed(() => {
  const s = props.paper.paper_data.relevance_score
  if (s == null) return ''
  if (s >= 0.7) return 'bg-tag-score-high/15 text-tag-score-high'
  if (s >= 0.4) return 'bg-tag-score-mid/15 text-tag-score-mid'
  return 'bg-tag-score-low/15 text-tag-score-low'
})

function noteIcon(type: string): string {
  if (type === 'file') return '📎'
  if (type === 'link') return '🔗'
  return '📝'
}

function toggleAddMenu() {
  showAddMenu.value = !showAddMenu.value
}
</script>

<template>
  <div>
    <!-- ====== Card body ====== -->
    <div
      class="bg-bg-card rounded-xl border border-border px-3.5 py-3 active:bg-bg-hover transition-colors"
      @click="batchMode ? $emit('toggle-check', paper.paper_id) : $emit('tap', paper.paper_id)"
    >
      <!-- Top row: [checkbox?] [expand?] title ......... [+] [⋮] -->
      <div class="flex items-start gap-2">
        <!-- Batch checkbox -->
        <div v-if="batchMode" class="shrink-0 mt-0.5" @click.stop="$emit('toggle-check', paper.paper_id)">
          <div
            class="w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors"
            :class="checked
              ? 'bg-tinder-pink border-tinder-pink'
              : 'border-border bg-transparent'"
          >
            <svg v-if="checked" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
        </div>

        <!-- Expand arrow (only when has notes, not in batch) -->
        <button
          v-if="!batchMode && (paper.note_count ?? 0) > 0"
          class="shrink-0 w-4 h-4 mt-1 flex items-center justify-center text-[9px] text-text-muted bg-transparent border-none transition-transform duration-150"
          :class="expanded ? 'rotate-90' : ''"
          @click.stop="$emit('toggle-expand', paper.paper_id)"
        >▶</button>

        <!-- 标题区域（占满剩余宽度） -->
        <div class="flex-1 min-w-0">
          <h4 class="text-[13px] font-semibold text-text-primary leading-snug line-clamp-2">
            {{ displayTitle }}
          </h4>
        </div>

        <!-- + Add button -->
        <button
          v-if="!batchMode"
          class="shrink-0 w-7 h-7 flex items-center justify-center text-text-muted bg-transparent border-none rounded-full active:bg-bg-hover"
          @click.stop="toggleAddMenu"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        </button>

        <!-- ⋮ Menu button -->
        <button
          v-if="!batchMode"
          class="shrink-0 w-7 h-7 flex items-center justify-center text-text-muted bg-transparent border-none rounded-full active:bg-bg-hover"
          @click.stop="$emit('menu', paper)"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="12" cy="19" r="2"/>
          </svg>
        </button>
      </div>

      <!-- Bottom row: [机构pill⭐] · 笔记数           [分数] -->
      <div class="mt-2 flex items-center gap-1.5">
        <span class="institution-badge-mini">
          {{ paper.paper_data.institution || '未知机构' }}
        </span>
        <span
          v-if="paper.paper_data.is_large_institution"
          class="text-[9px] leading-none shrink-0"
        >⭐</span>
        <span v-if="paper.note_count" class="text-[10px] text-text-muted shrink-0">
          · {{ paper.note_count }} 笔记
        </span>
        <!-- Score -->
        <span
          v-if="paper.paper_data.relevance_score != null"
          class="ml-auto shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold leading-none"
          :class="scoreClass"
        >
          {{ (paper.paper_data.relevance_score * 100).toFixed(0) }}
        </span>
      </div>
    </div>

    <!-- ====== Add menu dropdown ====== -->
    <div v-if="showAddMenu && !batchMode" class="mx-3 mt-1 mb-1 bg-bg-elevated rounded-xl border border-border overflow-hidden">
      <button
        class="w-full flex items-center gap-3 px-4 py-3 text-left text-sm text-text-primary bg-transparent border-none active:bg-bg-hover transition-colors border-b border-border"
        @click="showAddMenu = false; $emit('create-note', paper.paper_id)"
      >
        <span>📝</span> 新建笔记
      </button>
      <button
        class="w-full flex items-center gap-3 px-4 py-3 text-left text-sm text-text-primary bg-transparent border-none active:bg-bg-hover transition-colors border-b border-border"
        @click="showAddMenu = false; $emit('upload-file', paper.paper_id)"
      >
        <span>📎</span> 上传文件
      </button>
      <button
        class="w-full flex items-center gap-3 px-4 py-3 text-left text-sm text-text-primary bg-transparent border-none active:bg-bg-hover transition-colors"
        @click="showAddMenu = false; $emit('add-link', paper.paper_id)"
      >
        <span>🔗</span> 添加链接
      </button>
    </div>

    <!-- ====== Expanded notes ====== -->
    <div v-if="expanded && notes" class="mx-3 mt-1 space-y-1">
      <div
        v-for="note in notes"
        :key="note.id"
        class="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-bg-elevated active:bg-bg-hover transition-colors"
        @click="$emit('open-note', note)"
      >
        <span class="text-sm shrink-0">{{ noteIcon(note.type) }}</span>
        <span class="text-sm text-text-secondary truncate flex-1">{{ note.title }}</span>
        <button
          class="shrink-0 w-6 h-6 flex items-center justify-center text-text-muted active:text-tinder-pink bg-transparent border-none rounded text-xs"
          @click.stop="$emit('delete-note', note.id)"
        >✕</button>
      </div>
      <div v-if="notes.length === 0" class="text-xs text-text-muted py-2 px-3">
        暂无笔记
      </div>
    </div>
  </div>
</template>
