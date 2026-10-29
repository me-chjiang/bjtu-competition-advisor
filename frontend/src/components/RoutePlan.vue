<script setup lang="ts">
import { computed } from 'vue';
import type { Plan } from '../api/types';

const props = defineProps<{ plan: Plan; names: Record<string, string> }>();
const emit = defineEmits<{ open: [competitionId: string, evidenceIds: string[]] }>();

const pending = (v: string | number | null) => v ?? '待定';
const nameOf = (id: string) => props.names[id] ?? id;
const over = (hours: number | null, budget: number | null) => hours !== null && budget !== null && hours > budget;
const banner = computed(() => ({
  feasible: { cls: 'ok', text: '方案通过了可行性检查：每周投入未超出预算，任务日期明确。' },
  infeasible: { cls: 'error', text: '方案不可行：存在冲突或超出每周预算，请调整后重新生成，不能确认为可行方案。' },
  unknown: { cls: 'warn', text: '方案可行性无法确认：每周预算、任务工时或日期有未知项，不能当作已验证的方案。' },
}[props.plan.feasibility]));
</script>

<template>
  <div class="route">
    <div :class="['alert', banner.cls]" :data-feasibility="plan.feasibility" role="status">{{ banner.text }}</div>

    <div v-if="plan.conflicts.length" class="alert error">
      冲突：
      <ul><li v-for="c in plan.conflicts" :key="c">{{ c }}</li></ul>
    </div>
    <div v-if="plan.assumptions.length" class="alert info">
      假设：
      <ul><li v-for="a in plan.assumptions" :key="a">{{ a }}</li></ul>
    </div>

    <h4>任务</h4>
    <table class="tasks">
      <thead>
        <tr><th>任务</th><th>竞赛</th><th>预计投入</th><th>开始</th><th>截止</th><th>验收标准</th></tr>
      </thead>
      <tbody>
        <tr v-for="t in plan.tasks" :key="t.id">
          <td>{{ t.title }}</td>
          <td>
            <button class="link" type="button" @click="emit('open', t.competition_instance_id, [])">
              {{ nameOf(t.competition_instance_id) }}
            </button>
          </td>
          <td :class="{ pending: t.estimated_hours === null }">
            {{ t.estimated_hours === null ? '待定' : `${t.estimated_hours} 小时` }}
          </td>
          <td :class="{ pending: t.start_date === null }">{{ pending(t.start_date) }}</td>
          <td :class="{ pending: t.due_date === null }">{{ pending(t.due_date) }}</td>
          <td>{{ t.acceptance_criteria }}</td>
        </tr>
      </tbody>
    </table>

    <h4>每周负载</h4>
    <table v-if="plan.weekly_load.length" class="weeks">
      <thead><tr><th>周起始（周一）</th><th>预计投入</th><th>预算</th></tr></thead>
      <tbody>
        <tr v-for="w in plan.weekly_load" :key="w.week_start">
          <td>{{ w.week_start }}</td>
          <td :class="{ over: over(w.estimated_hours, w.budget_hours), pending: w.estimated_hours === null }">
            {{ w.estimated_hours === null ? '待定' : `${w.estimated_hours} 小时` }}
          </td>
          <td :class="{ pending: w.budget_hours === null }">
            {{ w.budget_hours === null ? '待定' : `${w.budget_hours} 小时` }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">没有可计入的每周负载。</p>
  </div>
</template>

<style scoped>
h4 { margin-top: 14px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 6px; border-top: 1px solid #eef1f5; vertical-align: top; }
th { color: var(--muted); font-weight: normal; white-space: nowrap; }
td.pending { color: var(--warn); }
td.over { color: var(--danger); font-weight: 600; }
ul { margin: 4px 0 0; padding-left: 18px; }
</style>
