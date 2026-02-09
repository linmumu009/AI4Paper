<script setup lang="ts">
import Navbar from './components/Navbar.vue'
</script>

<template>
  <div class="h-screen flex flex-col bg-bg">
    <!-- Top nav bar -->
    <Navbar />
    <!-- Main content -->
    <main class="flex-1 overflow-hidden">
      <router-view />
    </main>
  </div>
</template>
