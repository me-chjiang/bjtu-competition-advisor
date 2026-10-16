<script setup lang="ts">
import { computed } from 'vue';
import type { CandidateCard } from '../api/types';
import { REGISTRATION_LABELS } from '../labels';

const props = defineProps<{ cards: CandidateCard[]; busy: boolean; editable: boolean }>();
const emit = defineEmits<{
  setStatus: [candidateId: string, status: 'kept' | 'excluded'];
  open: [competitionId: string, evidenceIds: string[]];
}>();

const kept = computed(() => {
  const groups = new Map<string, CandidateCard[]>();
  for (const c of props.cards.filter((c) => c.status === 'kept')) {
    groups.set(c.domain, [...(groups.get(c.domain) ?? []), c]);
  }
  return [...groups.entries()];
});
const hidden = computed(() => props.cards.filter((c) => c.status === 'hidden'));
const userExcluded = computed(() => props.cards.filter((c) => c.status === 'excluded' && c.exclusion?.type !== 'hard'));
const hardExcluded = computed(() => props.cards.filter((c) => c.exclusion?.type === 'hard'));
</script>

<template>
  <div class="candidates">
    <p class="muted small">已保留 {{ kept.reduce((n, [, g]) => n + g.length, 0) }} 项，按领域分组。</p>

    <section v-for="[domain, group] in kept" :key="domain" class="group">
      <h4>{{ domain }}</h4>
      <article v-for="c in group" :key="c.id" class="candidate" :data-id="c.id">
        <div class="row">
          <button class="link name" type="button" @click="emit('open', c.competition_id, [])">{{ c.name }}</button>
          <span v-if="c.level" class="tag">{{ c.level }}</span>
          <span v-if="c.category" class="tag">{{ c.category }} 类</span>
          <span class="tag" :class="c.registration">{{ REGISTRATION_LABELS[c.registration] }}</span>
          <span v-if="c.stale" class="tag stale">待更新</span>
          <span class="spacer" />
          <button v-if="editable" type="button" :disabled="busy" @click="emit('setStatus', c.id, 'excluded')">排除</button>
        </div>
        <p class="muted">{{ c.reason }}</p>
      </article>
    </section>

    <details v-if="hidden.length || userExcluded.length" open>
      <summary>暂不展示 / 已排除（{{ hidden.length + userExcluded.length }}，可恢复）</summary>
      <article v-for="c in [...hidden, ...userExcluded]" :key="c.id" class="candidate dim" :data-id="c.id">
        <div class="row">
          <button class="link name" type="button" @click="emit('open', c.competition_id, [])">{{ c.name }}</button>
          <span class="tag">{{ c.status === 'hidden' ? '相关性较低' : '你已排除' }}</span>
          <span class="spacer" />
          <button v-if="editable" type="button" :disabled="busy" @click="emit('setStatus', c.id, 'kept')">恢复</button>
        </div>
        <p class="muted">{{ c.reason }}</p>
      </article>
    </details>

    <details v-if="hardExcluded.length">
      <summary>明确冲突（{{ hardExcluded.length }}，不能恢复）</summary>
      <article v-for="c in hardExcluded" :key="c.id" class="candidate dim" :data-id="c.id">
        <div class="row">
          <button class="link name" type="button" @click="emit('open', c.competition_id, c.exclusion!.evidence_ids)">
            {{ c.name }}
          </button>
          <span class="tag closed">硬性排除</span>
        </div>
        <p class="muted">依据：{{ c.exclusion!.reason }}</p>
      </article>
    </details>
  </div>
</template>

<style scoped>
.group { margin-bottom: 12px; }
.candidate { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
.candidate.dim { background: #fafbfc; }
.name { font-weight: 600; text-align: left; }
details { margin-top: 10px; }
summary { cursor: pointer; margin-bottom: 6px; color: var(--muted); }
</style>
