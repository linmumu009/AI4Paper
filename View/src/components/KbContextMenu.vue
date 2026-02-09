<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { KbMenuItem } from '../types/paper'

const props = defineProps<{
  items: KbMenuItem[]
  x: number
  y: number
}>()

const emit = defineEmits<{
  select: [key: string]
  close: []
}>()

const menuRef = ref<HTMLDivElement | null>(null)

function onClickOutside(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    emit('close')
  }
}

onMounted(() => {
  nextTick(() => {
    document.addEventListener('mousedown', onClickOutside, true)
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onClickOutside, true)
})

function handleSelect(key: string) {
  emit('select', key)
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuRef"
      class="fixed z-[9999] min-w-[140px] py-1 bg-bg-elevated border border-border rounded-lg shadow-xl"
      :style="{ left: `${x}px`, top: `${y}px` }"
    >
      <button
        v-for="item in items"
        :key="item.key"
        class="w-full text-left px-3 py-2 text-xs cursor-pointer bg-transparent border-none transition-colors"
        :class="item.danger
          ? 'text-tinder-pink hover:bg-tinder-pink/10'
          : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'"
        @click="handleSelect(item.key)"
      >
        {{ item.label }}
      </button>
    </div>
  </Teleport>
</template>
