<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDates, fetchPapers } from '../api'
import type { PaperSummary } from '../types/paper'

const router = useRouter()
const dates = ref<string[]>([])
const selectedDate = ref('')
const searchQuery = ref('')
const papers = ref<PaperSummary[]>([])
const loading = ref(false)

// Sort
type SortKey = 'institution' | 'relevance_score' | 'paper_id' | 'short_title'
const sortKey = ref<SortKey>('relevance_score')
const sortAsc = ref(false)

onMounted(async () => {
  try {
    const res = await fetchDates()
    dates.value = res.dates
    if (dates.value.length > 0) {
      selectedDate.value = dates.value[0]
    }
  } catch {}
})

watch(selectedDate, async (date) => {
  if (!date) return
  loading.value = true
  try {
    const res = await fetchPapers(date)
    papers.value = res.papers
  } catch {
    papers.value = []
  } finally {
    loading.value = false
  }
})

const filteredPapers = computed(() => {
  let list = papers.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (p) =>
        p['📖标题']?.toLowerCase().includes(q) ||
        p.short_title?.toLowerCase().includes(q) ||
        p.paper_id?.toLowerCase().includes(q) ||
        p.institution?.toLowerCase().includes(q),
    )
  }
  list = [...list].sort((a, b) => {
    let va: any, vb: any
    if (sortKey.value === 'relevance_score') {
      va = a.relevance_score ?? -1; vb = b.relevance_score ?? -1
    } else if (sortKey.value === 'institution') {
      va = a.institution || ''; vb = b.institution || ''
    } else if (sortKey.value === 'short_title') {
      va = a.short_title || ''; vb = b.short_title || ''
    } else {
      va = a.paper_id || ''; vb = b.paper_id || ''
    }
    if (typeof va === 'string') {
      const cmp = va.localeCompare(vb)
      return sortAsc.value ? cmp : -cmp
    }
    return sortAsc.value ? va - vb : vb - va
  })
  return list
})

function setSort(key: SortKey) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = false }
}

function sortArrow(key: SortKey) {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? ' ↑' : ' ↓'
}

function scoreColor(score: number | null | undefined): string {
  if (score == null) return 'text-text-muted'
  if (score >= 0.7) return 'text-tag-score-high'
  if (score >= 0.4) return 'text-tag-score-mid'
  return 'text-tag-score-low'
}
</script>

<template>
  <div class="h-full flex flex-col p-6 overflow-hidden">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5 shrink-0">
      <h1 class="text-xl font-bold text-text-primary">论文列表</h1>
      <div class="flex items-center gap-3">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索标题、机构、ID..."
          class="w-72 px-4 py-2 rounded-full bg-bg-elevated border border-border text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-tinder-pink/50 transition-colors"
        />
        <select
          :value="selectedDate"
          @change="selectedDate = ($event.target as HTMLSelectElement).value"
          class="px-3 py-2 rounded-full bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none cursor-pointer"
        >
          <option v-for="d in dates" :key="d" :value="d" class="bg-bg-card">{{ d }}</option>
        </select>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <svg class="animate-spin h-8 w-8 text-tinder-pink" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-y-auto rounded-xl bg-bg-card border border-border">
      <table class="w-full text-sm">
        <thead class="sticky top-0 z-10">
          <tr class="bg-bg-sidebar border-b border-border">
            <th
              v-for="col in [
                { key: 'short_title' as SortKey, label: '标题' },
                { key: 'institution' as SortKey, label: '机构' },
                { key: 'relevance_score' as SortKey, label: '相关性' },
                { key: 'paper_id' as SortKey, label: 'Paper ID' },
              ]"
              :key="col.key"
              class="text-left px-4 py-3 font-medium text-text-muted cursor-pointer select-none hover:text-text-secondary transition-colors whitespace-nowrap"
              :class="col.key === 'relevance_score' ? 'text-center' : ''"
              @click="setSort(col.key)"
            >
              {{ col.label }}{{ sortArrow(col.key) }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="paper in filteredPapers"
            :key="paper.paper_id"
            class="border-b border-border/50 hover:bg-bg-hover cursor-pointer transition-colors"
            @click="router.push(`/papers/${paper.paper_id}`)"
          >
            <td class="px-4 py-3 max-w-xs">
              <div class="font-medium text-text-primary truncate">{{ paper.short_title || paper['📖标题'] }}</div>
              <div class="text-xs text-text-muted truncate mt-0.5">{{ paper['📖标题'] }}</div>
            </td>
            <td class="px-4 py-3 whitespace-nowrap">
              <span class="text-text-secondary">{{ paper.institution || '—' }}</span>
              <span
                v-if="paper.is_large_institution"
                class="ml-1.5 text-xs px-1.5 py-0.5 rounded-full bg-tag-large-bg text-tag-large-text font-medium"
              >大</span>
            </td>
            <td class="px-4 py-3 text-center">
              <span
                v-if="paper.relevance_score != null"
                class="font-mono text-xs font-bold"
                :class="scoreColor(paper.relevance_score)"
              >{{ (paper.relevance_score * 100).toFixed(0) }}</span>
              <span v-else class="text-text-muted">—</span>
            </td>
            <td class="px-4 py-3 font-mono text-xs text-text-muted whitespace-nowrap">{{ paper.paper_id }}</td>
          </tr>
          <tr v-if="filteredPapers.length === 0">
            <td colspan="4" class="px-4 py-12 text-center text-text-muted">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
