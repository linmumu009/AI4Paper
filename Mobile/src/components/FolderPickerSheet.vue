<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KbFolder } from '../types/paper'

const props = defineProps<{
  folders: KbFolder[]
  title?: string
}>()

const emit = defineEmits<{
  (e: 'select', folderId: number | null): void
  (e: 'cancel'): void
}>()

const visible = ref(false)
const selectedId = ref<number | null>(null)

// Animate in
requestAnimationFrame(() => {
  visible.value = true
})

interface FlatFolder {
  id: number
  name: string
  depth: number
}

const flatFolders = computed(() => {
  const result: FlatFolder[] = []
  function walk(list: KbFolder[], depth: number) {
    for (const f of list) {
      result.push({ id: f.id, name: f.name, depth })
      if (f.children?.length) {
        walk(f.children, depth + 1)
      }
    }
  }
  walk(props.folders, 0)
  return result
})

function pick(id: number | null) {
  selectedId.value = id
}

function confirm() {
  visible.value = false
  setTimeout(() => emit('select', selectedId.value), 200)
}

function cancel() {
  visible.value = false
  setTimeout(() => emit('cancel'), 200)
}
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div
      class="fixed inset-0 z-[9998] transition-opacity duration-200"
      :class="visible ? 'bg-black/50' : 'bg-transparent'"
      @click="cancel"
    />

    <!-- Sheet -->
    <div
      class="fixed left-0 right-0 bottom-0 z-[9999] transition-transform duration-200 ease-out max-h-[70vh] flex flex-col"
      :class="visible ? 'translate-y-0' : 'translate-y-full'"
    >
      <div class="bg-bg-card rounded-t-2xl flex flex-col overflow-hidden safe-area-bottom">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3.5 border-b border-border shrink-0">
          <button
            class="text-sm text-text-muted bg-transparent border-none"
            @click="cancel"
          >取消</button>
          <h3 class="text-base font-semibold text-text-primary">{{ title || '移动到文件夹' }}</h3>
          <button
            class="text-sm font-semibold text-tinder-pink bg-transparent border-none"
            @click="confirm"
          >确认</button>
        </div>

        <!-- Folder list -->
        <div class="flex-1 overflow-y-auto p-3 space-y-1">
          <!-- Root option -->
          <button
            class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-colors border-none"
            :class="selectedId === null
              ? 'bg-gradient-to-r from-[#fd267a]/15 to-[#ff6036]/15 text-tinder-pink font-semibold'
              : 'bg-transparent text-text-secondary active:bg-bg-hover'"
            @click="pick(null)"
          >
            <span class="text-lg">📂</span>
            <span class="text-sm">根目录</span>
            <svg v-if="selectedId === null" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="ml-auto text-tinder-pink">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>

          <!-- Flattened folder list -->
          <button
            v-for="ff in flatFolders"
            :key="ff.id"
            class="w-full flex items-center gap-3 py-3 rounded-xl text-left transition-colors border-none"
            :class="selectedId === ff.id
              ? 'bg-gradient-to-r from-[#fd267a]/15 to-[#ff6036]/15 text-tinder-pink font-semibold'
              : 'bg-transparent text-text-secondary active:bg-bg-hover'"
            :style="{ paddingLeft: (16 + ff.depth * 20) + 'px', paddingRight: '16px' }"
            @click="pick(ff.id)"
          >
            <span class="text-lg">📁</span>
            <span class="text-sm flex-1">{{ ff.name }}</span>
            <svg v-if="selectedId === ff.id" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="text-tinder-pink">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>

          <!-- Empty state -->
          <div v-if="flatFolders.length === 0" class="text-center py-8 text-sm text-text-muted">
            暂无文件夹，请先创建
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
