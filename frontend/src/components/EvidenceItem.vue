<script setup lang="ts">
import { computed } from 'vue';
import type { Evidence } from '../api/types';
import { formatTime } from '../labels';

const props = defineProps<{ evidence: Evidence; highlight?: boolean }>();

// 证据 URL 来自外部网页，只有 http/https 才渲染成可点击链接，防止 javascript: 等协议
const safeUrl = computed(() => {
  try {
    const url = new URL(props.evidence.url);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
});
</script>

<template>
  <article class="evidence" :class="{ highlight }" :data-evidence-id="evidence.id">
    <p>{{ evidence.excerpt }}</p>
    <div class="muted small row">
      <span>适用年度：{{ evidence.applicable_year ?? '未知' }}</span>
      <span>范围：{{ evidence.scope ?? '未知' }}</span>
      <span>读取于 {{ formatTime(evidence.fetched_at) }}</span>
    </div>
    <a v-if="safeUrl" :href="safeUrl" target="_blank" rel="noopener noreferrer" class="small">{{ evidence.url }}</a>
    <span v-else class="small muted">{{ evidence.url }}</span>
  </article>
</template>

<style scoped>
.evidence { border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px; word-break: break-all; }
.evidence.highlight { border-color: var(--primary); background: var(--primary-weak); }
</style>
