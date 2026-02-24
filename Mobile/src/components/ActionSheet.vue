<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import type { KbMenuItem } from '../types/paper'

defineProps<{
  items: KbMenuItem[]
  title?: string
}>()

const emit = defineEmits<{
  (e: 'select', key: string): void
  (e: 'close'): void
}>()

const visible = ref(false)

onMounted(() => {
  // Animate in
  requestAnimationFrame(() => {
    visible.value = true
  })
})

function close() {
  visible.value = false
  setTimeout(() => emit('close'), 200)
}

function select(key: string) {
  visible.value = false
  setTimeout(() => {
    emit('select', key)
    emit('close')
  }, 200)
}
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div
      class="fixed inset-0 z-[9998] transition-opacity duration-200"
      :class="visible ? 'bg-black/50' : 'bg-transparent'"
      @click="close"
    />

    <!-- Sheet -->
    <div
      class="fixed left-0 right-0 bottom-0 z-[9999] transition-transform duration-200 ease-out"
      :class="visible ? 'translate-y-0' : 'translate-y-full'"
    >
      <div class="mx-3 mb-3 space-y-2">
        <!-- Actions group -->
        <div class="bg-bg-card rounded-2xl overflow-hidden">
          <!-- Title -->
          <div v-if="title" class="px-4 py-3 text-center border-b border-border">
            <span class="text-sm font-semibold text-text-secondary">{{ title }}</span>
          </div>
          <!-- Items -->
          <button
            v-for="item in items"
            :key="item.key"
            class="w-full px-4 py-3.5 text-center text-base font-medium border-none bg-transparent active:bg-bg-hover transition-colors border-b border-border last:border-b-0"
            :class="item.danger ? 'text-tinder-pink' : 'text-text-primary'"
            @click="select(item.key)"
          >
            {{ item.label }}
          </button>
        </div>

        <!-- Cancel button -->
        <button
          class="w-full px-4 py-3.5 text-center text-base font-semibold text-text-primary bg-bg-card rounded-2xl border-none active:bg-bg-hover transition-colors"
          @click="close"
        >
          取消
        </button>
      </div>
    </div>
  </Teleport>
</template>
