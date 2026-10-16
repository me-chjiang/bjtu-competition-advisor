<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { agentApi } from '../api';
import { ApiError } from '../api/client';
import type {
  CandidateCard, ChatResponse, ProfilePatch, RouteCard, ScorecardCard, Session, Stage,
} from '../api/types';
import CandidateList from '../components/CandidateList.vue';
import ChatPanel from '../components/ChatPanel.vue';
import CompetitionDrawer from '../components/CompetitionDrawer.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import RoutePlan from '../components/RoutePlan.vue';
import ScorecardList from '../components/ScorecardList.vue';
import StageBar from '../components/StageBar.vue';
import { errorMessage } from '../errors';
import { CONFIRM_LABELS } from '../labels';

type Tab = 'screen' | 'review' | 'route';

const props = defineProps<{ id?: string }>();
const router = useRouter();

const session = ref<Session | null>(null);
const busy = ref(false);
const error = ref<string | null>(null);
const notFound = ref(false);
const selected = ref<string[]>([]);
const userTab = ref<Tab | null>(null);
const drawer = ref<{ competitionId: string; highlight: string[] } | null>(null);

const candidates = computed(() =>
  (session.value?.cards ?? []).filter((c): c is CandidateCard => c.kind === 'candidate'));
const scorecards = computed(() =>
  (session.value?.cards ?? []).filter((c): c is ScorecardCard => c.kind === 'scorecard'));
const route = computed(() =>
  (session.value?.cards ?? []).find((c): c is RouteCard => c.kind === 'route') ?? null);
const hasStale = computed(() => (session.value?.cards ?? []).some((c) => c.stale));

const tabs = computed(() => {
  const list: { key: Tab; label: string }[] = [];
  if (candidates.value.length) list.push({ key: 'screen', label: `候选（${candidates.value.length}）` });
  if (scorecards.value.length) list.push({ key: 'review', label: `证据卡片（${scorecards.value.length}）` });
  if (route.value) list.push({ key: 'route', label: '备赛路线' });
  return list;
});
const stageTab = (stage: Stage): Tab | null =>
  stage === 'screen' || stage === 'review' ? stage : stage === 'route' || stage === 'done' ? 'route' : null;
const activeTab = computed<Tab | null>(() => {
  const available = tabs.value.map((t) => t.key);
  if (userTab.value && available.includes(userTab.value)) return userTab.value;
  const t = session.value && stageTab(session.value.stage);
  return t && available.includes(t) ? t : (available[0] ?? null);
});

const stage = computed(() => session.value?.stage ?? 'profile');
const confirmLabel = computed(() =>
  session.value?.needs_confirmation ? (CONFIRM_LABELS[stage.value] ?? null) : null);
const confirmDisabled = computed(() => stage.value === 'review' && selected.value.length === 0);

async function guarded(action: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = null;
  try {
    await action();
  } catch (e) {
    error.value = errorMessage(e);
  } finally {
    busy.value = false;
  }
}

async function load(id: string | undefined) {
  notFound.value = false;
  session.value = null;
  await guarded(async () => {
    if (!id) {
      const created = await agentApi.createSession();
      session.value = created;
      router.replace(`/advisor/${created.id}`);
      return;
    }
    try {
      session.value = await agentApi.getSession(id);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SESSION_NOT_FOUND') notFound.value = true;
      throw e;
    }
  });
}

watch(() => props.id, (id) => {
  if (!session.value || session.value.id !== id) load(id);
}, { immediate: true });

function apply(res: ChatResponse) {
  const s = session.value!;
  if (res.stage !== s.stage) userTab.value = null;
  Object.assign(s, {
    stage: res.stage,
    profile: res.profile,
    cards: res.cards,
    needs_confirmation: res.needs_confirmation,
  });
  s.messages.push(res.message);
}

const send = (content: string) => guarded(async () => {
  const s = session.value!;
  s.messages.push({ id: `local-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() });
  apply(await agentApi.chat(s.id, content));
});

const confirm = () => guarded(async () => {
  const s = session.value!;
  const ids = s.stage === 'review' ? selected.value : undefined;
  apply(await agentApi.confirm(s.id, s.stage, ids));
});

const saveProfile = (patch: ProfilePatch) => guarded(async () => {
  const s = session.value!;
  const res = await agentApi.patchProfile(s.id, patch);
  s.profile = res.profile;
  s.cards = res.cards;
});

const setCandidate = (candidateId: string, status: 'kept' | 'excluded') => guarded(async () => {
  const s = session.value!;
  const { card } = await agentApi.patchCandidate(s.id, candidateId, status);
  s.cards = s.cards.map((c) => (c.kind === card.kind && c.id === card.id ? card : c));
});

const open = (competitionId: string, highlight: string[]) => {
  drawer.value = { competitionId, highlight };
};

watch(scorecards, (cards) => {
  const ids = new Set(cards.map((c) => c.competition_id));
  selected.value = selected.value.filter((id) => ids.has(id));
});
</script>

<template>
  <div v-if="notFound" class="centered panel">
    <div class="alert error">会话不存在或已过期。</div>
    <button class="primary" type="button" @click="router.push('/advisor')">新建会话</button>
  </div>

  <div v-else-if="session" class="advisor">
    <StageBar :stage="session.stage" />
    <div v-if="error" class="alert error" role="alert">
      {{ error }} <button class="link" type="button" @click="error = null">知道了</button>
    </div>

    <div class="layout">
      <ProfilePanel :profile="session.profile" :busy="busy" @save="saveProfile" />

      <ChatPanel
        :messages="session.messages"
        :busy="busy"
        :confirm-label="confirmLabel"
        :confirm-disabled="confirmDisabled"
        @send="send"
        @confirm="confirm"
      />

      <section class="results panel">
        <div v-if="hasStale" class="alert warn row">
          画像已修改，部分结果待更新。
          <button class="link" type="button" :disabled="busy" @click="send('请根据最新画像更新当前结果')">重新生成</button>
        </div>

        <nav v-if="tabs.length" class="tabs">
          <button
            v-for="t in tabs"
            :key="t.key"
            type="button"
            :class="{ active: activeTab === t.key }"
            @click="userTab = t.key"
          >
            {{ t.label }}
          </button>
        </nav>

        <CandidateList
          v-if="activeTab === 'screen'"
          :cards="candidates"
          :busy="busy"
          :editable="session.stage === 'screen'"
          @set-status="setCandidate"
          @open="open"
        />
        <ScorecardList
          v-else-if="activeTab === 'review'"
          v-model:selected="selected"
          :cards="scorecards"
          :selectable="session.stage === 'review'"
          @open="open"
        />
        <RoutePlan v-else-if="activeTab === 'route' && route" :route="route" @open="open" />
        <div v-else class="muted empty">
          <p>在左侧对话中介绍自己，我会整理出画像草案。</p>
          <p>画像确认后，这里会依次显示候选竞赛、证据卡片和备赛路线。</p>
        </div>
      </section>
    </div>

    <CompetitionDrawer
      v-if="drawer"
      :competition-id="drawer.competitionId"
      :highlight="drawer.highlight"
      @close="drawer = null"
    />
  </div>

  <div v-else class="centered">
    <div v-if="error" class="alert error">{{ error }}</div>
    <p v-else class="muted">加载会话中…</p>
  </div>
</template>

<style scoped>
.advisor { display: flex; flex-direction: column; height: calc(100vh - 76px); }
.layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 260px minmax(320px, 1fr) minmax(420px, 1.3fr);
  gap: 12px;
}
.results { overflow-y: auto; }
.tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.tabs button.active { background: var(--primary-weak); border-color: var(--primary); color: var(--primary); }
.empty { padding: 20px 4px; }
</style>
