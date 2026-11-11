<script setup lang="ts">
import { computed } from 'vue';
import type { CandidateCard, Decision } from '../api/types';
import { DECISION_LABELS, ELIGIBILITY_LABELS, formatTime, REGISTRATION_LABELS } from '../labels';
import EvidenceItem from './EvidenceItem.vue';

const props = defineProps<{ cards: CandidateCard[]; busy: boolean }>();
const emit = defineEmits<{
  setDecision: [candidateId: string, decision: Decision];
  open: [competitionId: string, evidenceIds: string[]];
}>();

const DECISIONS: Decision[] = ['keep', 'defer', 'exclude'];
const GROUP_TITLES: Record<Decision, string> = { keep: '已保留', defer: '待定', exclude: '已排除' };

const groups = computed(() => DECISIONS.map((d) => ({
  decision: d,
  cards: props.cards.filter((c) => c.decision === d),
})).filter((g) => g.cards.length));
</script>

<template>
  <div class="candidates">
    <section v-for="g in groups" :key="g.decision" class="group">
      <h4>{{ GROUP_TITLES[g.decision] }}（{{ g.cards.length }}）</h4>
      <article
        v-for="c in g.cards"
        :key="c.competition_instance_id"
        class="candidate"
        :data-id="c.competition_instance_id"
      >
        <div class="row">
          <button class="link name" type="button" @click="emit('open', c.competition_instance_id, [])">{{ c.name }}</button>
          <span class="tag" :class="c.registration_status">{{ REGISTRATION_LABELS[c.registration_status] }}</span>
          <span class="tag" :class="c.eligibility">{{ ELIGIBILITY_LABELS[c.eligibility] }}</span>
        </div>
        <div class="muted small">
          报名截止：{{ formatTime(c.registration_deadline) || '待定' }}
        </div>
        <p>{{ c.reason }}</p>
        <div class="row decisions" role="group" :aria-label="`${c.name}的处理方式`">
          <button
            v-for="d in DECISIONS"
            :key="d"
            type="button"
            :data-decision="d"
            :class="{ active: c.decision === d }"
            :disabled="busy || c.decision === d || (d === 'keep' && c.eligibility === 'ineligible')"
            :title="d === 'keep' && c.eligibility === 'ineligible' ? '存在明确资格冲突，不能保留' : undefined"
            @click="emit('setDecision', c.competition_instance_id, d)"
          >
            {{ DECISION_LABELS[d] }}
          </button>
        </div>
        <details v-if="c.evidence.length" class="evidence-list">
          <summary class="muted small">证据（{{ c.evidence.length }}）</summary>
          <EvidenceItem v-for="e in c.evidence" :key="e.id" :evidence="e" />
        </details>
      </article>
    </section>
    <p v-if="!groups.length" class="muted">暂无候选。</p>
  </div>
</template>

<style scoped>
.group { margin-bottom: 12px; }
.candidate { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
.name { font-weight: 600; text-align: left; }
.decisions { margin: 6px 0; }
.decisions button.active { background: var(--primary-weak); border-color: var(--primary); color: var(--primary); }
.evidence-list summary { cursor: pointer; }
</style>
