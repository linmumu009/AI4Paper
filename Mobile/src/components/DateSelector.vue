<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps<{
  dates: string[]
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const open = ref(false)
const triggerEl = ref<HTMLElement | null>(null)
const dropdownEl = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
}

function select(d: string) {
  emit('update:modelValue', d)
  open.value = false
}

// Format date: "2026-02-22" -> "02/22"
function shortDate(d: string) {
  const parts = d.split('-')
  return `${parts[1]}/${parts[2]}`
}

// Format date: "2026-02-22" -> "周六" (weekday)
function weekday(d: string) {
  const date = new Date(d + 'T00:00:00')
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()]
}

const displayText = computed(() => {
  if (!props.modelValue) return '选择日期'
  return `${shortDate(props.modelValue)} ${weekday(props.modelValue)}`
})

// Close dropdown when clicking outside
function onClickOutside(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node
  if (triggerEl.value?.contains(target) || dropdownEl.value?.contains(target)) return
  open.value = false
}

onMounted(() => {
  document.addEventListener('click', onClickOutside, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside, true)
})
</script>

<template>
  <div class="relative inline-flex">
    <!-- Trigger button -->
    <button
      ref="triggerEl"
      class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-bg-elevated border border-border text-sm font-medium text-text-primary transition-colors active:bg-bg-hover"
      @click="toggle"
    >
      <span>{{ displayText }}</span>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        class="transition-transform"
        :class="open ? 'rotate-180' : ''"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <!-- Backdrop -->
    <Transition name="fade">
      <div v-if="open" class="fixed inset-0 z-40" @click="open = false"></div>
    </Transition>

    <!-- Dropdown -->
    <Transition name="dropdown">
      <div
        v-if="open"
        ref="dropdownEl"
        class="absolute left-0 top-full mt-1.5 z-50 min-w-[200px] max-h-[50vh] overflow-y-auto rounded-xl bg-bg-card border border-border shadow-2xl"
      >
        <div class="py-1.5">
          <button
            v-for="d in dates"
            :key="d"
            class="w-full flex items-center justify-between px-4 py-2.5 text-left transition-colors"
            :class="d === modelValue
              ? 'text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036]'
              : 'text-text-secondary hover:bg-bg-hover active:bg-bg-hover'"
            @click="select(d)"
          >
            <span class="text-sm font-medium">{{ shortDate(d) }} {{ weekday(d) }}</span>
            <svg
              v-if="d === modelValue"
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
  transform-origin: top left;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scaleY(0.9) translateY(-4px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
