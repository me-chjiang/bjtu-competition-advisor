<script setup lang="ts">
import { computed } from 'vue';
import { STAGES, type Stage } from '../api/types';
import { STAGE_LABELS } from '../labels';

const props = defineProps<{ stage: Stage }>();
const current = computed(() => STAGES.indexOf(props.stage));
</script>

<template>
  <ol class="stage-bar">
    <li
      v-for="(s, i) in STAGES"
      :key="s"
      :class="{ done: i < current, active: i === current }"
      :aria-current="i === current ? 'step' : undefined"
    >
      {{ STAGE_LABELS[s] }}
    </li>
  </ol>
</template>

<style scoped>
.stage-bar { display: flex; gap: 4px; list-style: none; padding: 0; margin: 0 0 12px; }
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
</style>
