<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { to: '/', icon: '🔥', label: '发现' },
  { to: '/papers', icon: '📋', label: '列表' },
]
</script>

<template>
  <nav class="h-14 flex items-center justify-between px-5 bg-bg-sidebar border-b border-border">
    <!-- Logo -->
    <router-link to="/" class="flex items-center gap-2 no-underline">
      <span class="text-xl gradient-text font-bold tracking-tight">ArxivPaper</span>
    </router-link>

    <!-- Center nav icons -->
    <div class="flex items-center gap-1">
      <router-link
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :title="item.label"
        class="w-10 h-10 flex items-center justify-center rounded-full no-underline text-lg transition-all duration-200"
        :class="route.path === item.to
          ? 'bg-bg-elevated text-text-primary scale-110'
          : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'"
      >
        {{ item.icon }}
      </router-link>
    </div>

    <!-- Right spacer for symmetry -->
    <div class="w-24"></div>
  </nav>
</template>
