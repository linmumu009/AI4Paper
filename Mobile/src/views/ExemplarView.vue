<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { fetchIdeaExemplars, deleteIdeaExemplar } from '../api'
import type { IdeaExemplar } from '../types/paper'
import { ensureAuthInitialized, isAuthenticated } from '../stores/auth'

defineOptions({ name: 'ExemplarView' })

const exemplars = ref<IdeaExemplar[]>([])
const loading = ref(false)
const error = ref('')

async function loadExemplars() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchIdeaExemplars({ limit: 500 })
    exemplars.value = res.exemplars
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await ensureAuthInitialized()
  if (isAuthenticated.value) await loadExemplars()
})

watch(() => isAuthenticated.value, (authed) => {
  if (authed) loadExemplars()
  else exemplars.value = []
})

async function handleDelete(id: number) {
  if (!confirm('确定要删除这个范例吗？')) return
  try {
    await deleteIdeaExemplar(id)
    exemplars.value = exemplars.value.filter((e) => e.id !== id)
  } catch {}
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Content -->
    <div class="flex-1 overflow-y-auto p-4">
      <div v-if="loading" class="flex items-center justify-center min-h-[200px]">
        <div class="relative w-12 h-12 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#fd267a] border-r-[#ff6036] animate-spin" />
          <span class="text-xl">⭐</span>
        </div>
      </div>

      <div v-else-if="error" class="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
        {{ error }}
      </div>

      <div v-else-if="exemplars.length === 0" class="flex items-center justify-center min-h-[200px]">
        <div class="text-center">
          <p class="text-3xl mb-3">⭐</p>
          <p class="text-sm text-text-muted">还没有范例。在灵感详情页中标记优质灵感为范例。</p>
        </div>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="ex in exemplars"
          :key="ex.id"
          class="bg-bg-card border border-border rounded-xl p-4"
        >
          <div class="flex items-start justify-between gap-3 mb-2">
            <div class="flex items-center gap-2">
              <span class="text-lg">⭐</span>
              <span class="text-xs text-text-muted">#{{ ex.id }}</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span v-if="ex.score" class="text-xs font-semibold" :class="ex.score >= 8 ? 'text-green-400' : ex.score >= 6 ? 'text-yellow-400' : 'text-text-muted'">
                {{ ex.score.toFixed(1) }}
              </span>
              <button
                class="text-xs px-2 py-1 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 active:bg-red-500/20"
                @click="handleDelete(ex.id)"
              >
                删除
              </button>
            </div>
          </div>

          <p v-if="ex.notes" class="text-sm text-text-secondary leading-relaxed mb-3">{{ ex.notes }}</p>

          <div v-if="ex.pattern && Object.keys(ex.pattern).length" class="text-xs text-text-muted bg-bg-elevated rounded-lg p-3 mb-3 space-y-1">
            <div v-for="(val, key) in ex.pattern" :key="String(key)">
              <span class="font-medium text-text-secondary">{{ key }}:</span> {{ val }}
            </div>
          </div>

          <div class="flex items-center justify-between text-[10px] text-text-muted">
            <span v-if="ex.candidate_id">灵感 #{{ ex.candidate_id }}</span>
            <span>{{ new Date(ex.created_at).toLocaleDateString('zh-CN') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
