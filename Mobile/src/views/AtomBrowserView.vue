<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { fetchIdeaAtoms, deleteIdeaAtom } from '../api'
import type { IdeaAtom } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

defineOptions({ name: 'AtomBrowserView' })

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
  if (!confirm('确定要删除这个原子吗？')) return
  try {
    await deleteIdeaAtom(id)
    atoms.value = atoms.value.filter((a) => a.id !== id)
  } catch {}
}

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

const atomTypeLabel: Record<string, string> = {
  claim: '论断',
  method: '方法',
  setup: '设置',
  limitation: '局限',
  tag: '标签',
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Type filter + search -->
    <div class="shrink-0 px-4 py-2 border-b border-border bg-bg">
      <div class="flex items-center gap-1 overflow-x-auto no-scrollbar mb-2">
        <button
          v-for="at in atomTypes"
          :key="at.key"
          class="shrink-0 text-xs px-3 py-1.5 rounded-full border transition-colors border-none"
          :class="typeFilter === at.key
            ? 'bg-gradient-to-r from-[#fd267a] to-[#ff6036] text-white font-semibold'
            : 'bg-bg-elevated text-text-muted active:bg-bg-hover'"
          @click="typeFilter = at.key"
        >
          {{ at.icon }} {{ at.label }}
          <span v-if="typeCounts[at.key]" class="ml-1 text-[10px] opacity-80">{{ typeCounts[at.key] }}</span>
        </button>
      </div>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索原子..."
        class="w-full px-3 py-2 text-sm rounded-lg border border-border bg-bg-elevated text-text-primary placeholder:text-text-muted focus:outline-none focus:border-tinder-pink"
      />
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4">
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
          class="bg-bg-card border border-border rounded-lg overflow-hidden transition-colors border-l-4"
          :class="atomTypeColor[atom.atom_type] || 'border-l-border'"
        >
          <!-- Summary row -->
          <div class="flex items-start gap-3 p-3 active:bg-bg-hover" @click="toggleExpand(atom.id)">
            <span class="text-sm shrink-0 mt-0.5">
              {{ atomTypes.find(t => t.key === atom.atom_type)?.icon || '📄' }}
            </span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-xs font-semibold text-text-primary">{{ atomTypeLabel[atom.atom_type] || atom.atom_type }}</span>
                <span class="text-[10px] text-text-muted">{{ atom.paper_id }}</span>
              </div>
              <p class="text-sm text-text-primary leading-snug line-clamp-2">{{ atom.content }}</p>
            </div>
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-text-muted transition-transform shrink-0 mt-1" :class="expandedId === atom.id ? 'rotate-180' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </div>

          <!-- Expanded detail -->
          <Transition name="expand">
            <div v-if="expandedId === atom.id" class="px-3 pb-3 border-t border-border/50 pt-3 space-y-2">
              <!-- Evidence -->
              <div v-if="atom.evidence?.length">
                <p class="text-[10px] text-text-muted uppercase tracking-wider mb-1">证据</p>
                <div v-for="(ev, i) in atom.evidence" :key="i" class="text-xs text-text-secondary italic leading-relaxed pl-3 border-l-2 border-border mb-1">
                  "{{ ev.snippet || ev.text }}"
                  <span v-if="ev.page" class="text-[10px] text-text-muted ml-1">p.{{ ev.page }}</span>
                </div>
              </div>
              <!-- Tags -->
              <div v-if="atom.tags?.length" class="flex flex-wrap gap-1">
                <span v-for="t in atom.tags" :key="t" class="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">{{ t }}</span>
              </div>
              <!-- Delete -->
              <div class="flex justify-end pt-2">
                <button
                  class="text-xs px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 active:bg-red-500/20"
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
