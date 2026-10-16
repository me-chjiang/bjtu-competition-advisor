<script setup lang="ts">
import { ref, watch } from 'vue';
import { agentApi } from '../api';
import type { Competition } from '../api/types';
import { errorMessage } from '../errors';
import { formatTime, REGISTRATION_LABELS } from '../labels';

const props = defineProps<{ competitionId: string; highlight: string[] }>();
const emit = defineEmits<{ close: [] }>();

const SOURCE_LABELS = { mis: 'MIS', official_site: '官网', notice: '通知', other: '其他' } as const;

// 证据 URL 来自外部网页，防止 javascript: 等协议被渲染成可点击链接
const isHttpUrl = (url: string) => /^https?:\/\//i.test(url);

const competition = ref<Competition | null>(null);
const error = ref<string | null>(null);

watch(
  () => props.competitionId,
  async (id) => {
    competition.value = null;
    error.value = null;
    try {
      competition.value = await agentApi.getCompetition(id);
    } catch (e) {
      error.value = errorMessage(e);
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="backdrop" @click.self="emit('close')">
    <aside class="drawer panel" role="dialog" aria-label="竞赛详情">
      <div class="row">
        <h3>{{ competition?.name ?? '竞赛详情' }}</h3>
        <span class="spacer" />
        <button type="button" aria-label="关闭" @click="emit('close')">关闭</button>
      </div>
      <div v-if="error" class="alert error">{{ error }}</div>
      <p v-else-if="!competition" class="muted">加载中…</p>
      <template v-else>
        <dl>
          <dt>年度</dt><dd>{{ competition.year }}</dd>
          <dt>级别 / 类型</dt><dd>{{ competition.level ?? '未说明' }} · {{ competition.category ? `${competition.category} 类` : '未说明' }}</dd>
          <dt>主办</dt><dd>{{ competition.organizer ?? '未说明' }}</dd>
          <dt>形式</dt><dd>{{ competition.format ?? '未说明' }}</dd>
          <dt>报名</dt>
          <dd>
            <span class="tag" :class="competition.registration.status">{{ REGISTRATION_LABELS[competition.registration.status] }}</span>
            {{ competition.registration.start ?? '?' }} ~ {{ competition.registration.end ?? '?' }}
          </dd>
        </dl>
        <p v-if="competition.description">{{ competition.description }}</p>

        <h4>证据（{{ competition.evidence.length }}）</h4>
        <article
          v-for="e in competition.evidence"
          :key="e.id"
          class="evidence"
          :class="{ highlight: highlight.includes(e.id) }"
        >
          <p>{{ e.excerpt }}</p>
          <div class="muted small row">
            <span class="tag">{{ SOURCE_LABELS[e.source_type] }}</span>
            <span>适用：{{ e.applies_to_year ?? '年度未知' }} · {{ e.applies_to_group ?? '组别未知' }}</span>
            <span>读取于 {{ formatTime(e.fetched_at) }}</span>
            <span v-if="e.session_id">session {{ e.session_id }}</span>
          </div>
          <a v-if="isHttpUrl(e.url)" :href="e.url" target="_blank" rel="noopener noreferrer" class="small">{{ e.url }}</a>
          <span v-else class="small muted">{{ e.url }}</span>
        </article>
      </template>
    </aside>
  </div>
</template>

<style scoped>
.backdrop { position: fixed; inset: 0; background: rgb(0 0 0 / 25%); display: flex; justify-content: flex-end; z-index: 10; }
.drawer { width: min(520px, 100%); height: 100%; overflow-y: auto; border-radius: 0; }
dl { display: grid; grid-template-columns: 90px 1fr; gap: 4px 8px; }
dt { color: var(--muted); }
dd { margin: 0; }
.evidence { border: 1px solid var(--border); border-radius: 6px; padding: 8px; margin-bottom: 8px; word-break: break-all; }
.evidence.highlight { border-color: var(--primary); background: var(--primary-weak); }
</style>
