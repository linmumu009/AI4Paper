<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchIdeaAtoms, deleteIdeaAtom } from '../api'
import type { IdeaAtom } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

const router = useRouter()

const props = defineProps<{ embedded?: boolean }>()

const atoms = ref<IdeaAtom[]>([])
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const typeFilter = ref<string>('')

const atomTypes = [
  { key: '', label: '全部', icon: '📋' },
  { key: 'claim', label: '论断', icon: '💬' },
  { key: 'method', label: '方法', icon: '⚙️' },
  { key: 'setup', label: '设置', icon: '📊' },
  { key: 'limitation', label: '局限', icon: '⚠️' },
  { key: 'tag', label: '标签', icon: '🏷️' },
]

const filteredAtoms = computed(() => {
  let list = atoms.value
  if (typeFilter.value) {
    list = list.filter((a) => a.atom_type === typeFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(
      (a) =>
        a.content.toLowerCase().includes(q) ||
        a.tags?.some((t) => t.toLowerCase().includes(q)) ||
        a.paper_id.toLowerCase().includes(q),
    )
  }
  return list
})

const typeCounts = computed(() => {
  const counts: Record<string, number> = { '': atoms.value.length }
  for (const a of atoms.value) {
    counts[a.atom_type] = (counts[a.atom_type] || 0) + 1
  }
  return counts
})

async function loadAtoms() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaAtoms({ limit: 1000 })
    atoms.value = res.atoms
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) {
    await loadAtoms()
  }
})

watch(() => isAuthenticated.value, (authed) => {
  if (authed) loadAtoms()
  else atoms.value = []
})

async function handleDelete(id: number) {
  try {
    await deleteIdeaAtom(id)
    atoms.value = atoms.value.filter((a) => a.id !== id)
  } catch {}
}

// Expanded atom detail
const expandedId = ref<number | null>(null)
function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
}

const atomTypeColor: Record<string, string> = {
  claim: 'border-l-blue-400',
  method: 'border-l-green-400',
  setup: 'border-l-yellow-400',
  limitation: 'border-l-red-400',
  tag: 'border-l-purple-400',
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <div class="shrink-0 px-4 sm:px-6 pt-4 sm:pt-6 pb-4 border-b border-border bg-bg">
      <div class="flex items-center gap-3 mb-4">
        <button
          v-if="!props.embedded"
          class="text-xs px-3 py-1.5 rounded-full border border-border bg-transparent text-text-muted cursor-pointer hover:text-text-secondary hover:bg-bg-hover transition-colors flex items-center gap-1.5"
          @click="router.push('/workbench')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回
        </button>
        <h1 class="text-xl font-bold text-text-primary flex items-center gap-2">
          <span class="text-2xl">🔬</span> 灵感原子库
        </h1>
      </div>

      <!-- Type filter tabs + search -->
      <div class="flex flex-col sm:flex-row sm:items-center gap-3">
        <div class="flex items-center gap-1 overflow-x-auto no-scrollbar">
          <button
            v-for="at in atomTypes"
            :key="at.key"
            class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors cursor-pointer"
            :class="typeFilter === at.key
              ? 'bg-bg-elevated text-text-primary border-border-light font-semibold'
              : 'bg-transparent text-text-muted border-transparent hover:text-text-secondary hover:bg-bg-hover'"
            @click="typeFilter = at.key"
          >
            {{ at.icon }} {{ at.label }}
            <span v-if="typeCounts[at.key]" class="ml-1 text-[10px] opacity-60">{{ typeCounts[at.key] }}</span>
          </button>
        </div>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索原子..."
          class="w-full sm:w-64 px-3 py-1.5 text-xs rounded-lg border border-border bg-bg-elevated text-text-primary placeholder-text-muted focus:outline-none focus:border-border-light transition-colors"
        />
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4 sm:p-6">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center min-h-[200px]">
        <div class="flex flex-col items-center gap-3">
          <div class="relative w-12 h-12 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
            <span class="text-xl">🔬</span>
          </div>
          <p class="text-sm text-text-muted">加载中...</p>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>

      <!-- Empty -->
      <div v-else-if="filteredAtoms.length === 0" class="flex items-center justify-center min-h-[200px]">
        <div class="text-center">
          <p class="text-3xl mb-3">🔬</p>
          <p class="text-sm text-text-muted">
            {{ atoms.length === 0 ? '还没有灵感原子。运行灵感流水线后，原子会在此出现。' : '没有匹配的原子。' }}
          </p>
        </div>
      </div>

      <!-- Atom list -->
      <div v-else class="space-y-2">
        <p class="text-xs text-text-muted mb-3">共 {{ filteredAtoms.length }} 个原子</p>
        <div
          v-for="atom in filteredAtoms"
          :key="atom.id"
          class="bg-bg-card border border-border rounded-lg overflow-hidden transition-colors hover:border-border-light border-l-4"
          :class="atomTypeColor[atom.atom_type] || 'border-l-border'"
        >
          <!-- Summary row -->
          <div class="flex items-start gap-3 p-3 cursor-pointer" @click="toggleExpand(atom.id)">
            <span class="text-sm shrink-0 mt-0.5">
              {{ atomTypes.find(t => t.key === atom.atom_type)?.icon || '📄' }}
            </span>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-text-primary leading-snug line-clamp-2">{{ atom.content }}</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-[10px] text-text-muted">{{ atom.paper_id }}</span>
                <span v-if="atom.section" class="text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">{{ atom.section }}</span>
              </div>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              <div v-if="atom.tags?.length" class="hidden sm:flex items-center gap-1">
                <span v-for="t in atom.tags.slice(0, 3)" :key="t" class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">{{ t }}</span>
              </div>
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5 text-text-muted transition-transform" :class="expandedId === atom.id ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
          </div>

          <!-- Expanded detail -->
          <Transition name="expand">
            <div v-if="expandedId === atom.id" class="px-3 pb-3 border-t border-border/50 pt-3 space-y-2">
              <!-- Evidence -->
              <div v-if="atom.evidence?.length">
                <p class="text-[10px] text-text-muted uppercase tracking-wider mb-1">证据</p>
                <div v-for="(ev, i) in atom.evidence" :key="i" class="text-xs text-text-secondary italic leading-relaxed pl-3 border-l-2 border-border mb-1">
                  "{{ ev.snippet }}"
                  <span class="text-[10px] text-text-muted ml-1">p.{{ ev.page }}, ¶{{ ev.paragraph }}</span>
                </div>
              </div>
              <!-- Tags -->
              <div v-if="atom.tags?.length" class="flex flex-wrap gap-1">
                <span v-for="t in atom.tags" :key="t" class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">{{ t }}</span>
              </div>
              <!-- Meta -->
              <div class="flex items-center gap-3 text-[10px] text-text-muted">
                <span>ID: {{ atom.id }}</span>
                <span>来源: {{ atom.source_file || '—' }}</span>
                <span>{{ atom.created_at }}</span>
              </div>
              <!-- Delete -->
              <div class="flex justify-end">
                <button
                  class="text-[10px] px-2 py-1 rounded border border-border bg-transparent text-text-muted cursor-pointer hover:text-red-400 hover:border-red-500/30 transition-colors"
                  @click.stop="handleDelete(atom.id)"
                >
                  删除
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

.expand-enter-active, .expand-leave-active { transition: all 0.2s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; padding-top: 0; padding-bottom: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 500px; }
</style>
