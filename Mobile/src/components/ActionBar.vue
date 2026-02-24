<script setup lang="ts">
defineEmits<{
  (e: 'undo'): void
  (e: 'skip'): void
  (e: 'like'): void
  (e: 'detail'): void
}>()
</script>

<template>
  <div class="flex items-end justify-evenly py-2.5 px-2 max-w-md mx-auto w-full">
    <!-- Undo -->
    <button
      class="action-btn action-btn-sm border-tinder-gold text-tinder-gold"
      @click="$emit('undo')"
    >
      <span class="action-icon-sm">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
          <path d="M3 3v5h5"/>
        </svg>
      </span>
      <span class="action-label">撤回</span>
    </button>

    <!-- Skip / Nope -->
    <button
      class="action-btn action-btn-lg border-tinder-pink text-tinder-pink"
      @click="$emit('skip')"
    >
      <span class="action-icon-lg">
        <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </span>
      <span class="action-label">跳过</span>
    </button>

    <!-- Like / Heart -->
    <button
      class="action-btn action-btn-lg border-tinder-green text-tinder-green"
      @click="$emit('like')"
    >
      <span class="action-icon-lg">
        <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
      </span>
      <span class="action-label">感兴趣</span>
    </button>

    <!-- Detail -->
    <button
      class="action-btn action-btn-sm border-tinder-blue text-tinder-blue"
      @click="$emit('detail')"
    >
      <span class="action-icon-sm">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
      </span>
      <span class="action-label">详情</span>
    </button>
  </div>
</template>

<style scoped>
.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.15s ease;
}
.action-btn:active {
  transform: scale(0.9);
}

.action-icon-lg {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 9999px;
  border: 3px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.action-icon-sm {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 9999px;
  border: 2px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.action-label {
  font-size: 10px;
  font-weight: 500;
  line-height: 1;
  color: inherit;
  white-space: nowrap;
}
</style>
