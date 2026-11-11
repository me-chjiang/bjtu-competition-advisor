<script setup lang="ts">
import { reactive, ref } from 'vue';
import type { Profile, ProfileChanges, TeamPreference } from '../api/types';
import { TEAM_LABELS } from '../labels';
import MarkdownText from './MarkdownText.vue';

const props = defineProps<{ profile: Profile; busy: boolean; hasResults: boolean }>();
const emit = defineEmits<{ save: [changes: ProfileChanges] }>();

const MAX_CONTEXT = 2000;
const MAX_SUMMARY = 4000;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const editing = ref(false);
const errors = ref<string[]>([]);
const draft = reactive({
  grade: '',
  major: '',
  weekly_hours: '' as number | '',
  goals: '',
  team_preference: '' as TeamPreference | '',
  unavailable_dates: '',
  additional_context: '',
  summary: '',
  skills: [] as { name: string; evidence: string }[],
});

const splitList = (s: string) => s.split(/[,，、\s]+/).map((x) => x.trim()).filter(Boolean);

function startEdit() {
  const p = props.profile;
  Object.assign(draft, {
    grade: p.grade ?? '',
    major: p.major ?? '',
    weekly_hours: p.weekly_hours ?? '',
    goals: p.goals.join('、'),
    team_preference: p.team_preference ?? '',
    unavailable_dates: p.unavailable_dates.join('、'),
    additional_context: p.additional_context ?? '',
    summary: p.summary ?? '',
    skills: p.skills.map((s) => ({ name: s.name, evidence: s.evidence ?? '' })),
  });
  errors.value = [];
  editing.value = true;
}

function validate(): string[] {
  const list: string[] = [];
  const hours = draft.weekly_hours;
  if (hours !== '' && !(typeof hours === 'number' && hours > 0)) list.push('每周可投入必须大于 0，或留空表示未知');
  if (splitList(draft.unavailable_dates).some((d) => !DATE_RE.test(d))) list.push('不可用日期格式应为 YYYY-MM-DD');
  if (draft.additional_context.length > MAX_CONTEXT) list.push(`补充说明不能超过 ${MAX_CONTEXT} 字`);
  if (draft.summary.length > MAX_SUMMARY) list.push(`画像整理不能超过 ${MAX_SUMMARY} 字`);
  return list;
}

function save() {
  errors.value = validate();
  if (errors.value.length) return;
  const next: Required<ProfileChanges> = {
    grade: draft.grade.trim() || null,
    major: draft.major.trim() || null,
    skills: draft.skills.filter((s) => s.name.trim()).map((s) => ({ name: s.name.trim(), evidence: s.evidence.trim() || null })),
    weekly_hours: draft.weekly_hours === '' ? null : draft.weekly_hours,
    goals: splitList(draft.goals),
    team_preference: draft.team_preference || null,
    unavailable_dates: splitList(draft.unavailable_dates),
    additional_context: draft.additional_context.trim() || null,
    summary: draft.summary.trim() || null,
  };
  // 只提交有改动的字段；数组整体替换
  const changes: Record<string, unknown> = {};
  for (const key of Object.keys(next) as (keyof typeof next)[]) {
    if (JSON.stringify(next[key]) !== JSON.stringify(props.profile[key])) changes[key] = next[key];
  }
  if (!Object.keys(changes).length) {
    editing.value = false;
    return;
  }
  if (props.hasResults && !window.confirm('修改画像会清空已生成的候选和路线，并回到 R0 重新核对。是否继续？')) return;
  editing.value = false;
  emit('save', changes as ProfileChanges);
}

const show = (v: string | number | null | undefined) => (v === null || v === undefined || v === '' ? '未填写' : v);
</script>

<template>
  <aside class="profile panel">
    <div class="row">
      <h3>我的画像</h3>
    </div>

    <template v-if="!editing">
      <MarkdownText v-if="profile.summary" :source="profile.summary" />
      <p v-else class="muted small">在右侧聊天里介绍自己，或直接粘贴简历，AI 会整理成画像。</p>
      <details :open="!profile.summary">
        <summary class="muted small">结构化字段（用于资格与工时计算）</summary>
      <dl>
        <dt>年级 / 专业</dt><dd>{{ show(profile.grade) }} · {{ show(profile.major) }}</dd>
        <dt>每周可投入</dt><dd>{{ profile.weekly_hours === null ? '未填写' : `${profile.weekly_hours} 小时` }}</dd>
        <dt>目标</dt><dd>{{ profile.goals.join('、') || '未填写' }}</dd>
        <dt>参赛方式</dt><dd>{{ profile.team_preference ? TEAM_LABELS[profile.team_preference] : '未填写' }}</dd>
        <dt>不可用日期</dt><dd>{{ profile.unavailable_dates.join('、') || '未填写' }}</dd>
        <dt>技能</dt>
        <dd>
          <ul v-if="profile.skills.length" class="skills">
            <li v-for="s in profile.skills" :key="s.name">
              <strong>{{ s.name }}</strong>
              <div class="muted small">{{ s.evidence ?? '未提供依据' }}</div>
            </li>
          </ul>
          <span v-else>未填写</span>
        </dd>
        <dt>补充说明</dt><dd class="context">{{ show(profile.additional_context) }}</dd>
      </dl>
      </details>
      <button type="button" :disabled="busy" @click="startEdit">编辑画像</button>
    </template>

    <form v-else @submit.prevent="save">
      <label>
        <span>画像整理（Markdown，最多 {{ MAX_SUMMARY }} 字）</span>
        <textarea v-model="draft.summary" name="summary" rows="8" />
      </label>
      <label><span>年级</span><input v-model="draft.grade" name="grade" /></label>
      <label><span>专业</span><input v-model="draft.major" name="major" /></label>
      <label>
        <span>每周可投入（小时，留空表示未知）</span>
        <input v-model.number="draft.weekly_hours" name="weekly_hours" type="number" min="0" step="any" />
      </label>
      <label><span>目标（用顿号分隔）</span><input v-model="draft.goals" name="goals" /></label>
      <label>
        <span>参赛方式</span>
        <select v-model="draft.team_preference" name="team_preference">
          <option value="">未填写</option>
          <option v-for="(label, key) in TEAM_LABELS" :key="key" :value="key">{{ label }}</option>
        </select>
      </label>
      <label>
        <span>不可用日期（YYYY-MM-DD，用顿号分隔）</span>
        <input v-model="draft.unavailable_dates" name="unavailable_dates" />
      </label>
      <fieldset>
        <legend class="muted">技能</legend>
        <div v-for="(s, i) in draft.skills" :key="i" class="skill-edit">
          <div class="row">
            <input v-model="s.name" name="skill_name" placeholder="技能" />
            <button type="button" class="link" @click="draft.skills.splice(i, 1)">删除</button>
          </div>
          <input v-model="s.evidence" name="skill_evidence" placeholder="依据：课程、项目、获奖" />
        </div>
        <button type="button" class="link" @click="draft.skills.push({ name: '', evidence: '' })">+ 添加技能</button>
      </fieldset>
      <label>
        <span>补充说明（最多 {{ MAX_CONTEXT }} 字）<strong class="warn-text">勿填写账号密码</strong></span>
        <textarea v-model="draft.additional_context" name="additional_context" rows="4" />
        <span class="small">{{ draft.additional_context.length }} / {{ MAX_CONTEXT }}</span>
      </label>
      <div v-for="e in errors" :key="e" class="alert error" role="alert">{{ e }}</div>
      <p class="muted small">保存有改动的画像后，已生成的候选和路线会被清空，并回到 R0 重新核对。</p>
      <div class="row">
        <button class="primary" type="submit" :disabled="busy">保存</button>
        <button type="button" @click="editing = false">取消</button>
      </div>
    </form>
  </aside>
</template>

<style scoped>
.profile { overflow-y: auto; }
dl { margin: 0 0 12px; }
dt { color: var(--muted); font-size: 12px; margin-top: 8px; }
dd { margin: 2px 0 0; }
.context { white-space: pre-wrap; word-break: break-word; }
.skills { padding-left: 16px; margin: 0; }
.skills li { margin-bottom: 4px; }
fieldset { border: 1px solid var(--border); border-radius: 6px; margin: 0 0 10px; padding: 8px; }
.skill-edit { display: grid; gap: 4px; margin-bottom: 8px; }
.skill-edit .row { flex-wrap: nowrap; }
.warn-text { color: var(--warn); margin-left: 8px; font-weight: normal; }
</style>
