<script setup lang="ts">
import { computed, ref } from 'vue';
import type { RankKey, ScorecardCard } from '../api/types';
import { BASIS_LABELS, CONFIDENCE_LABELS, TIER_LABELS } from '../labels';

const props = defineProps<{ cards: ScorecardCard[]; selectable: boolean }>();
const selected = defineModel<string[]>('selected', { required: true });
const emit = defineEmits<{ open: [competitionId: string, evidenceIds: string[]] }>();

const SORTS: Record<RankKey, string> = { goal: '目标价值', time: '时间成本', risk: '风险' };
const sortBy = ref<RankKey>('goal');
const sorted = computed(() => [...props.cards].sort((a, b) => a.ranks[sortBy.value] - b.ranks[sortBy.value]));

function toggle(id: string, on: boolean) {
  selected.value = on ? [...selected.value, id] : selected.value.filter((x) => x !== id);
}
</script>

<template>
  <div class="scorecards">
    <div class="row toolbar">
      <span class="muted">排序依据：</span>
      <label v-for="(label, key) in SORTS" :key="key" class="sort-option">
        <input v-model="sortBy" type="radio" name="sort" :value="key" /> {{ label }}
      </label>
      <span class="spacer" />
      <span v-if="selectable" class="muted small">已勾选 {{ selected.length }} 项</span>
    </div>

    <article v-for="(c, i) in sorted" :key="c.id" class="card" :data-id="c.id">
      <div class="row">
        <input
          v-if="selectable"
          type="checkbox"
          :aria-label="`选择 ${c.name}`"
          :checked="selected.includes(c.competition_id)"
          @change="toggle(c.competition_id, ($event.target as HTMLInputElement).checked)"
        />
        <span class="rank">#{{ i + 1 }}</span>
        <button class="link name" type="button" @click="emit('open', c.competition_id, [])">{{ c.name }}</button>
        <span v-if="c.stale" class="tag stale">待更新</span>
      </div>
      <p>{{ c.summary }}</p>
      <table>
        <tbody>
          <tr v-for="d in c.dimensions" :key="d.key">
            <th>{{ d.label }}</th>
            <td class="tier">{{ TIER_LABELS[d.tier] }}</td>
            <td>
              {{ d.summary }}
              <span class="tag" :class="d.basis">{{ BASIS_LABELS[d.basis] }}</span>
              <span class="muted small">置信度 {{ CONFIDENCE_LABELS[d.confidence] }}</span>
              <button
                v-if="d.evidence_ids.length"
                class="link small"
                type="button"
                @click="emit('open', c.competition_id, d.evidence_ids)"
              >
                证据 {{ d.evidence_ids.length }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </article>

    <p class="muted small">
      无历史数据时不给出获奖概率，只评估准备难度和风险。「目标价值」仅供参考：保研加分以本人学院当年的正式文件为准，请自行核对。
    </p>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 10px; }
.sort-option { display: inline-flex; align-items: center; gap: 4px; margin: 0 8px 0 0; }
.sort-option input { width: auto; }
.card { border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 10px; }
.card input[type='checkbox'] { width: auto; }
.rank { color: var(--muted); font-weight: 600; }
.name { font-weight: 600; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
th, td { text-align: left; padding: 4px 6px; border-top: 1px solid #eef1f5; vertical-align: top; }
th { width: 72px; color: var(--muted); font-weight: normal; white-space: nowrap; }
td.tier { width: 40px; font-weight: 600; }
td .link { margin-left: 6px; }
</style>
