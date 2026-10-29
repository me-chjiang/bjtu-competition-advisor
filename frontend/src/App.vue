<script setup lang="ts">
import { apiModes } from './api';
</script>

<template>
  <header class="app-header">
    <RouterLink to="/advisor" class="brand">北交大竞赛能力匹配</RouterLink>
    <span class="modes" title="由 VITE_AGENT_API 控制">Agent：{{ apiModes.agent }}</span>
  </header>
  <main class="app-main">
    <RouterView />
  </main>
</template>
