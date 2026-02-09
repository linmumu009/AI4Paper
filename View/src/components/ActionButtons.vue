<script setup lang="ts">
defineEmits<{
  undo: []
  skip: []
  superlike: []
  like: []
  detail: []
}>()
</script>

<template>
  <div class="flex items-center justify-center gap-3 py-4">
    <!-- Undo -->
    <button
      class="w-12 h-12 rounded-full border-2 border-tinder-gold/40 flex items-center justify-center text-tinder-gold hover:bg-tinder-gold/10 hover:border-tinder-gold hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
      title="撤回"
      @click="$emit('undo')"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
    </button>

    <!-- Skip / Nope -->
    <button
      class="w-14 h-14 rounded-full border-2 border-tinder-pink/40 flex items-center justify-center text-tinder-pink hover:bg-tinder-pink/10 hover:border-tinder-pink hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
      title="跳过"
      @click="$emit('skip')"
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
    </button>

    <!-- Super Like -->
    <button
      class="w-12 h-12 rounded-full border-2 border-tinder-blue/40 flex items-center justify-center text-tinder-blue hover:bg-tinder-blue/10 hover:border-tinder-blue hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
      title="详细信息"
      @click="$emit('detail')"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
    </button>

    <!-- Like -->
    <button
      class="w-14 h-14 rounded-full border-2 border-tinder-green/40 flex items-center justify-center text-tinder-green hover:bg-tinder-green/10 hover:border-tinder-green hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
      title="感兴趣"
      @click="$emit('like')"
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
    </button>

    <!-- Open PDF -->
    <button
      class="w-12 h-12 rounded-full border-2 border-tinder-purple/40 flex items-center justify-center text-tinder-purple hover:bg-tinder-purple/10 hover:border-tinder-purple hover:scale-110 transition-all duration-200 cursor-pointer bg-transparent"
      title="打开 PDF"
      @click="$emit('superlike')"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
    </button>
  </div>
</template>
