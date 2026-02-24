<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import IdeaLabView from './IdeaLabView.vue'
import AtomBrowserView from './AtomBrowserView.vue'
import ExemplarView from './ExemplarView.vue'

defineOptions({ name: 'WorkbenchView' })

const router = useRouter()

type Tool = 'idea' | 'atoms' | 'exemplars'

const activeTool = ref<Tool>('idea')

const tools: { key: Tool; icon: string; label: string }[] = [
  { key: 'idea', icon: '🧪', label: '灵感工作台' },
  { key: 'atoms', icon: '🔬', label: '原子库' },
  { key: 'exemplars', icon: '⭐', label: '范例库' },
]
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center gap-3 px-5 pt-4 pb-2">
        <button
          class="w-9 h-9 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-text-muted active:bg-bg-hover"
          @click="router.back()"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <h1 class="text-xl font-bold gradient-text flex-1">工作台</h1>
      </div>

      <!-- Tool tabs -->
      <div class="flex items-center gap-1 px-4 pb-2 overflow-x-auto no-scrollbar">
        <button
          v-for="tool in tools"
          :key="tool.key"
          class="shrink-0 flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all border-none"
          :class="activeTool === tool.key
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white'
            : 'bg-bg-elevated text-text-muted active:bg-bg-hover'"
          @click="activeTool = tool.key"
        >
          <span class="text-base">{{ tool.icon }}</span>
          <span>{{ tool.label }}</span>
        </button>
      </div>
    </div>

    <!-- Tool content -->
    <div class="flex-1 overflow-hidden">
      <IdeaLabView v-if="activeTool === 'idea'" />
      <AtomBrowserView v-else-if="activeTool === 'atoms'" />
      <ExemplarView v-else-if="activeTool === 'exemplars'" />
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
</style>
