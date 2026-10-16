<script setup lang="ts">
import type { RouteCard, RouteTask } from '../api/types';

defineProps<{ route: RouteCard }>();
const emit = defineEmits<{ open: [competitionId: string, evidenceIds: string[]] }>();

function period(t: RouteTask): string {
  if (t.date_certainty === 'unknown' || !t.start || !t.end) return '日期待定';
  return `${t.start} ~ ${t.end}${t.date_certainty === 'estimated' ? '（预估）' : ''}`;
}
</script>

<template>
  <div class="route">
    <div v-if="route.stale" class="alert warn">画像已修改，这份路线待更新。</div>

    <div class="summary row">
      <div>
        <div class="muted small">高峰周投入</div>
        <strong :class="{ over: route.weekly_hours_available !== null && route.weekly_hours_total > route.weekly_hours_available }">
          {{ route.weekly_hours_total }} 小时
        </strong>
        <span class="muted"> / 可投入 {{ route.weekly_hours_available ?? '未填写' }} 小时</span>
      </div>
    </div>

    <div v-for="c in route.conflicts" :key="c.description" class="alert error">冲突：{{ c.description }}</div>
    <div v-if="route.pending_checks.length" class="alert warn">
      待核实：
      <ul><li v-for="p in route.pending_checks" :key="p">{{ p }}</li></ul>
    </div>

    <section v-for="item in route.items" :key="item.competition_id" class="item">
      <h4><button class="link" type="button" @click="emit('open', item.competition_id, [])">{{ item.name }}</button></h4>
      <table>
        <thead><tr><th>任务</th><th>每周</th><th>时间</th><th>验收标准</th></tr></thead>
        <tbody>
          <tr v-for="t in item.tasks" :key="t.title">
            <td>
              {{ t.title }}
              <div v-for="a in t.assumptions" :key="a" class="muted small">假设：{{ a }}</div>
            </td>
            <td>{{ t.hours_per_week }}h</td>
            <td :class="{ pending: t.date_certainty === 'unknown' }">{{ period(t) }}</td>
            <td>{{ t.acceptance }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.summary { margin-bottom: 8px; }
.over { color: var(--danger); }
.item { margin-top: 12px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 6px; border-top: 1px solid #eef1f5; vertical-align: top; }
th { color: var(--muted); font-weight: normal; white-space: nowrap; }
td.pending { color: var(--warn); }
ul { margin: 4px 0 0; padding-left: 18px; }
</style>
