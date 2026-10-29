<script setup lang="ts">
import type { CandidateCard } from '../api/types';
import { BASIS_LABELS, DIMENSION_LABELS } from '../labels';

defineProps<{ cards: CandidateCard[] }>();
const emit = defineEmits<{ open: [competitionId: string, evidenceIds: string[]] }>();
</script>

<template>
  <div class="scorecards">
    <article v-for="c in cards" :key="c.competition_instance_id" class="card" :data-id="c.competition_instance_id">
      <div class="row">
        <button class="link name" type="button" @click="emit('open', c.competition_instance_id, [])">{{ c.name }}</button>
      </div>
      <table>
        <tbody>
          <tr v-for="d in c.dimensions" :key="d.name">
            <th>{{ DIMENSION_LABELS[d.name] }}</th>
            <td>
              {{ d.assessment }}
              <span class="tag" :class="d.basis">{{ BASIS_LABELS[d.basis] }}</span>
              <button
                v-if="d.evidence_ids.length"
                class="link small"
                type="button"
                @click="emit('open', c.competition_instance_id, d.evidence_ids)"
              >
                证据 {{ d.evidence_ids.length }}
              </button>
              <ul v-if="d.uncertainties.length" class="uncertainties muted small">
                <li v-for="u in d.uncertainties" :key="u">不确定：{{ u }}</li>
              </ul>
            </td>
          </tr>
        </tbody>
      </table>
    </article>

    <p class="muted small">
      不提供获奖概率，只评估差距、投入和风险；「官方」表示有本届明确来源，「推断」依据往届或相关材料，「信息不足」需要自行核实。
    </p>
  </div>
</template>

<style scoped>
.card { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 10px; }
.name { font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
th, td { text-align: left; padding: 4px 6px; border-top: 1px solid #eef1f5; vertical-align: top; }
th { width: 72px; color: var(--muted); font-weight: normal; white-space: nowrap; }
td .link { margin-left: 6px; }
.uncertainties { margin: 2px 0 0; padding-left: 16px; }
</style>
