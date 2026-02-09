<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KbFolder } from '../types/paper'

const props = defineProps<{
  folders: KbFolder[]
  title?: string
}>()

const emit = defineEmits<{
  select: [folderId: number | null]
  cancel: []
}>()

const selectedId = ref<number | null>(null)

/** Flatten nested folders into a list with depth info for indentation */
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
  emit('select', selectedId.value)
}
</script>

<template>
  <Teleport to="body">
    <!-- Overlay -->
    <div
      class="fixed inset-0 z-[9998] bg-black/60 flex items-center justify-center"
      @click.self="emit('cancel')"
    >
      <!-- Dialog -->
      <div class="w-[320px] max-h-[70vh] bg-bg-card border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-border">
          <h3 class="text-sm font-bold text-text-primary">{{ title || '移动到文件夹' }}</h3>
        </div>

        <!-- Folder list -->
        <div class="flex-1 overflow-y-auto p-2">
          <!-- Root option -->
          <button
            class="w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors cursor-pointer border-none"
            :class="selectedId === null
              ? 'bg-tinder-pink/15 text-tinder-pink font-semibold'
              : 'bg-transparent text-text-secondary hover:bg-bg-hover'"
            @click="pick(null)"
          >
            <span class="text-sm">📂</span>
            根目录
          </button>

          <!-- Flattened folder list with indent -->
          <button
            v-for="ff in flatFolders"
            :key="ff.id"
            class="w-full text-left flex items-center gap-2 py-2 rounded-lg text-xs transition-colors cursor-pointer border-none"
            :class="selectedId === ff.id
              ? 'bg-tinder-pink/15 text-tinder-pink font-semibold'
              : 'bg-transparent text-text-secondary hover:bg-bg-hover'"
            :style="{ paddingLeft: (12 + ff.depth * 16) + 'px', paddingRight: '12px' }"
            @click="pick(ff.id)"
          >
            <span class="text-sm">📁</span>
            {{ ff.name }}
          </button>

          <!-- Empty state -->
          <div v-if="flatFolders.length === 0" class="text-center py-6 text-xs text-text-muted">
            暂无文件夹，请先创建
          </div>
        </div>

        <!-- Footer buttons -->
        <div class="flex items-center justify-end gap-2 px-4 py-3 border-t border-border">
          <button
            class="px-4 py-1.5 rounded-full text-xs text-text-muted border border-border bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="emit('cancel')"
          >
            取消
          </button>
          <button
            class="px-4 py-1.5 rounded-full text-xs text-white font-semibold bg-gradient-to-r from-[#fd267a] to-[#ff6036] border-none cursor-pointer hover:opacity-90 transition-opacity"
            @click="confirm"
          >
            确认移动
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
