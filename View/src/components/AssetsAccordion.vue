<script setup lang="ts">
import { ref } from 'vue'
import type { PaperAssets } from '../types/paper'

defineProps<{
  assets: PaperAssets
}>()

const openSections = ref<Set<string>>(new Set(['method', 'results']))

const blockLabels: Record<string, { label: string; icon: string }> = {
  background: { label: '研究背景', icon: '🏛️' },
  objective: { label: '研究目标', icon: '🎯' },
  method: { label: '方法', icon: '⚙️' },
  data: { label: '数据', icon: '📊' },
  experiment: { label: '实验设置', icon: '🧪' },
  metrics: { label: '评价指标', icon: '📏' },
  results: { label: '实验结果', icon: '📈' },
  limitations: { label: '局限性', icon: '⚠️' },
}

function toggle(key: string) {
  if (openSections.value.has(key)) {
    openSections.value.delete(key)
  } else {
    openSections.value.add(key)
  }
  openSections.value = new Set(openSections.value)
}
</script>

<template>
  <div class="space-y-2">
    <template v-for="(meta, key) in blockLabels" :key="key">
      <div
        v-if="assets.blocks?.[key as keyof typeof assets.blocks]"
        class="border border-border rounded-xl overflow-hidden"
      >
        <button
          class="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated text-left cursor-pointer border-none transition-colors hover:bg-bg-hover"
          @click="toggle(key)"
        >
          <span class="flex items-center gap-2 text-sm font-medium text-text-primary">
            <span>{{ meta.icon }}</span>
            {{ meta.label }}
          </span>
          <span
            class="text-text-muted text-xs transition-transform duration-200"
            :class="openSections.has(key) ? 'rotate-180' : ''"
          >▼</span>
        </button>

        <div v-if="openSections.has(key)" class="px-4 py-3 bg-bg-card">
          <p
            v-if="assets.blocks[key as keyof typeof assets.blocks].text"
            class="text-sm text-text-secondary leading-relaxed mb-2"
          >{{ assets.blocks[key as keyof typeof assets.blocks].text }}</p>
          <ul
            v-if="assets.blocks[key as keyof typeof assets.blocks].bullets?.length"
            class="space-y-1.5"
          >
            <li
              v-for="(bullet, idx) in assets.blocks[key as keyof typeof assets.blocks].bullets"
              :key="idx"
              class="text-xs text-text-muted leading-relaxed pl-3 border-l-2 border-border-light"
            >{{ bullet }}</li>
          </ul>
          <p
            v-if="!assets.blocks[key as keyof typeof assets.blocks].text && !assets.blocks[key as keyof typeof assets.blocks].bullets?.length"
            class="text-xs text-text-muted italic"
          >暂无数据</p>
        </div>
      </div>
    </template>
  </div>
</template>
