<script setup lang="ts">
import { reactive, ref } from 'vue';
import type { Profile, ProfilePatch, Skill } from '../api/types';
import { DISCIPLINES, SKILL_LEVEL_LABELS, TEAM_LABELS } from '../labels';

const props = defineProps<{ profile: Profile; busy: boolean }>();
const emit = defineEmits<{ save: [patch: ProfilePatch] }>();

const editing = ref(false);
const draft = reactive({
  grade: '',
  major: '',
  discipline: '',
  weekly_hours: '' as number | '',
  goals: '',
  domains: '',
  team_preference: '' as Profile['team_preference'] | '',
  skills: [] as Skill[],
});

const splitList = (s: string) => s.split(/[,，、]/).map((x) => x.trim()).filter(Boolean);

function startEdit() {
  const p = props.profile;
  Object.assign(draft, {
    grade: p.grade ?? '',
    major: p.major ?? '',
    discipline: p.discipline ?? '',
    weekly_hours: p.weekly_hours ?? '',
    goals: p.goals.join('、'),
    domains: p.domains.join('、'),
    team_preference: p.team_preference ?? '',
    skills: p.skills.map((s) => ({ ...s })),
  });
  editing.value = true;
}

function save() {
  emit('save', {
    grade: draft.grade.trim() || null,
    major: draft.major.trim() || null,
    discipline: draft.discipline || null,
    weekly_hours: draft.weekly_hours === '' ? null : draft.weekly_hours,
    goals: splitList(draft.goals),
    domains: splitList(draft.domains),
    team_preference: draft.team_preference || null,
    skills: draft.skills.filter((s) => s.name.trim()).map((s) => ({ ...s })),
  });
  editing.value = false;
}

const show = (v: string | number | null | undefined) => (v === null || v === undefined || v === '' ? '未填写' : v);
</script>

<template>
  <aside class="profile panel">
    <div class="row">
      <h3>我的画像</h3>
      <span class="spacer" />
      <span v-if="profile.version" class="tag" :class="{ official: profile.confirmed }">
        v{{ profile.version }} · {{ profile.confirmed ? '已确认' : '草案' }}
      </span>
    </div>

    <template v-if="!editing">
      <dl>
        <dt>年级 / 专业</dt><dd>{{ show(profile.grade) }} · {{ show(profile.major) }}</dd>
        <dt>学科大类</dt><dd>{{ show(profile.discipline) }}</dd>
        <dt>每周可投入</dt><dd>{{ profile.weekly_hours === null ? '未填写' : `${profile.weekly_hours} 小时` }}</dd>
        <dt>目标</dt><dd>{{ profile.goals.join('、') || '未填写' }}</dd>
        <dt>倾向领域</dt><dd>{{ profile.domains.join('、') || '未填写' }}</dd>
        <dt>参赛方式</dt><dd>{{ profile.team_preference ? TEAM_LABELS[profile.team_preference] : '未填写' }}</dd>
        <dt>技能</dt>
        <dd>
          <ul v-if="profile.skills.length" class="skills">
            <li v-for="s in profile.skills" :key="s.name">
              <strong>{{ s.name }}</strong> <span class="tag">{{ SKILL_LEVEL_LABELS[s.level] }}</span>
              <div class="muted small">{{ s.evidence }}</div>
            </li>
          </ul>
          <span v-else>未填写</span>
        </dd>
      </dl>
      <button type="button" :disabled="busy" @click="startEdit">编辑画像</button>
    </template>

    <form v-else @submit.prevent="save">
      <label><span>年级</span><input v-model="draft.grade" name="grade" /></label>
      <label><span>专业</span><input v-model="draft.major" name="major" /></label>
      <label>
        <span>学科大类</span>
        <select v-model="draft.discipline" name="discipline">
          <option value="">未填写</option>
          <option v-for="d in DISCIPLINES" :key="d" :value="d">{{ d }}</option>
        </select>
      </label>
      <label><span>每周可投入（小时）</span><input v-model.number="draft.weekly_hours" name="weekly_hours" type="number" min="0" /></label>
      <label><span>目标（用顿号分隔）</span><input v-model="draft.goals" name="goals" /></label>
      <label><span>倾向领域（用顿号分隔）</span><input v-model="draft.domains" name="domains" /></label>
      <label>
        <span>参赛方式</span>
        <select v-model="draft.team_preference" name="team_preference">
          <option value="">未填写</option>
          <option v-for="(label, key) in TEAM_LABELS" :key="key" :value="key">{{ label }}</option>
        </select>
      </label>
      <fieldset>
        <legend class="muted">技能</legend>
        <div v-for="(s, i) in draft.skills" :key="i" class="skill-edit">
          <div class="row">
            <input v-model="s.name" placeholder="技能" />
            <select v-model="s.level" style="width: 90px">
              <option v-for="(label, key) in SKILL_LEVEL_LABELS" :key="key" :value="key">{{ label }}</option>
            </select>
            <button type="button" class="link" @click="draft.skills.splice(i, 1)">删除</button>
          </div>
          <input v-model="s.evidence" placeholder="证据：课程、项目、获奖" />
        </div>
        <button type="button" class="link" @click="draft.skills.push({ name: '', level: 'basic', evidence: '' })">
          + 添加技能
        </button>
      </fieldset>
      <p class="muted small">保存后，已有的候选、卡片和路线会标记为待更新。</p>
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
.skills { padding-left: 16px; margin: 0; }
.skills li { margin-bottom: 4px; }
fieldset { border: 1px solid var(--border); border-radius: 6px; margin: 0 0 10px; padding: 8px; }
.skill-edit { display: grid; gap: 4px; margin-bottom: 8px; }
.skill-edit .row { flex-wrap: nowrap; }
</style>
