<script setup lang="ts">
import { apiModes } from './api';
import LlmSettingsDialog from './components/LlmSettingsDialog.vue';
import { llmDialogOpen } from './llm-dialog';
</script>

<template>
  <header class="app-header">
    <RouterLink to="/advisor" class="brand">北交大竞赛能力匹配</RouterLink>
    <span class="row">
      <span class="modes" title="由 VITE_AGENT_API 控制">Agent：{{ apiModes.agent }}</span>
      <button type="button" @click="llmDialogOpen = true">模型设置</button>
    </span>
  </header>
  <main class="app-main">
    <RouterView />
  </main>
  <LlmSettingsDialog v-if="llmDialogOpen" @close="llmDialogOpen = false" />
</template>
