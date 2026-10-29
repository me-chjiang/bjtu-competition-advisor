<script setup lang="ts">
import { ref, watch } from 'vue';
import { agentApi } from '../api';
import type { CompetitionDetail } from '../api/types';
import { errorMessage } from '../errors';
import { formatTime, REGISTRATION_LABELS } from '../labels';
import EvidenceItem from './EvidenceItem.vue';

const props = defineProps<{ competitionId: string; highlight: string[] }>();
const emit = defineEmits<{ close: [] }>();

const competition = ref<CompetitionDetail | null>(null);
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
          <dt>年度 / 组别</dt><dd>{{ competition.year ?? '未知' }} · {{ competition.group ?? '未知' }}</dd>
          <dt>比赛阶段</dt><dd>{{ competition.stage ?? '未知' }}</dd>
          <dt>参赛资格</dt><dd>{{ competition.eligibility_description ?? '未说明' }}</dd>
          <dt>报名</dt>
          <dd>
            <span class="tag" :class="competition.registration_status">{{ REGISTRATION_LABELS[competition.registration_status] }}</span>
            {{ formatTime(competition.registration_start) || '?' }} ~ {{ formatTime(competition.registration_deadline) || '?' }}
          </dd>
          <dt>比赛时间</dt><dd>{{ formatTime(competition.competition_date) || '未知' }}</dd>
        </dl>

        <h4>证据（{{ competition.evidence.length }}）</h4>
        <EvidenceItem
          v-for="e in competition.evidence"
          :key="e.id"
          :evidence="e"
          :highlight="highlight.includes(e.id)"
        />
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
</style>
