<script setup lang="ts">
import { computed } from 'vue';
import { STAGES, type Stage, type Status } from '../api/types';
import { STAGE_LABELS, STATUS_LABELS } from '../labels';

const props = defineProps<{ stage: Stage; status: Status; message: string }>();
const current = computed(() => STAGES.indexOf(props.stage));
const finished = computed(() => props.status === 'completed');
</script>

<template>
  <div class="stage-wrap">
    <ol class="stage-bar">
      <li
        v-for="(s, i) in STAGES"
        :key="s"
        :class="{ done: i < current || finished, active: i === current && !finished }"
        :aria-current="i === current ? 'step' : undefined"
      >
        {{ STAGE_LABELS[s] }}
      </li>
    </ol>
    <div class="status row">
      <span class="tag" :class="status" data-test="status">{{ STATUS_LABELS[status] }}</span>
      <span data-test="message">{{ message }}</span>
    </div>
  </div>
</template>

<style scoped>
.stage-wrap { margin-bottom: 12px; }
.stage-bar { display: flex; gap: 4px; list-style: none; padding: 0; margin: 0 0 8px; }
.stage-bar li {
  flex: 1;
  text-align: center;
  padding: 6px 0;
  border-radius: 6px;
  background: #eef1f5;
  color: var(--muted);
}
.stage-bar li.done { background: var(--ok-weak); color: var(--ok); }
.stage-bar li.active { background: var(--primary); color: #fff; font-weight: 600; }
.tag.awaiting_review { background: var(--warn-weak); color: var(--warn); }
.tag.completed { background: var(--ok-weak); color: var(--ok); }
</style>
