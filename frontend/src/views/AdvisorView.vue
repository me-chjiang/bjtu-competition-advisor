<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { agentApi } from '../api';
import { ApiError } from '../api/client';
import type { Decision, ProfileChanges, SessionSnapshot, Stage } from '../api/types';
import CandidateList from '../components/CandidateList.vue';
import ChatPanel from '../components/ChatPanel.vue';
import CompetitionDrawer from '../components/CompetitionDrawer.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import RoutePlan from '../components/RoutePlan.vue';
import ScorecardList from '../components/ScorecardList.vue';
import StageBar from '../components/StageBar.vue';
import { errorMessage } from '../errors';

type Tab = 'screen' | 'review' | 'route';

const POLL_MS = 3000;

const props = defineProps<{ id?: string }>();
const router = useRouter();

const snapshot = ref<SessionSnapshot | null>(null);
const loading = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const notFound = ref(false);
const pendingText = ref<string | null>(null);
const userTab = ref<Tab | null>(null);
const drawer = ref<{ competitionId: string; highlight: string[] } | null>(null);

const cards = computed(() => snapshot.value?.cards ?? []);
const plan = computed(() => snapshot.value?.plan ?? null);
const analysed = computed(() => cards.value.filter((c) => c.dimensions.length > 0));
const keptCards = computed(() => cards.value.filter((c) => c.decision === 'keep'));
const names = computed(() => Object.fromEntries(cards.value.map((c) => [c.competition_instance_id, c.name])));
// 同一会话同一时间只允许一个修改请求：本地请求进行中，或后端仍在处理（含刷新页面后）
const locked = computed(() => busy.value || snapshot.value?.processing === true);

const tabs = computed(() => {
  const list: { key: Tab; label: string }[] = [];
  if (cards.value.length) list.push({ key: 'screen', label: `候选（${cards.value.length}）` });
  if (analysed.value.length) list.push({ key: 'review', label: `精查（${analysed.value.length}）` });
  if (plan.value) list.push({ key: 'route', label: '备赛路线' });
  return list;
});
const STAGE_TAB: Partial<Record<Stage, Tab>> = { R1: 'screen', R2: 'review', R4: 'route' };
const activeTab = computed<Tab | null>(() => {
  const available = tabs.value.map((t) => t.key);
  if (userTab.value && available.includes(userTab.value)) return userTab.value;
  const t = snapshot.value && STAGE_TAB[snapshot.value.stage];
  return t && available.includes(t) ? t : (available[0] ?? null);
});

const hasStageResult = computed(() => {
  switch (snapshot.value?.stage) {
    case 'R1': return cards.value.length > 0;
    case 'R2': return analysed.value.length > 0;
    case 'R4': return plan.value !== null;
    default: return true;
  }
});
// 确认后进入新阶段只是 collecting，是否生成由用户显式触发，前端不自动调用
const canGenerate = computed(() =>
  snapshot.value?.status === 'collecting' && snapshot.value.stage !== 'R0' && !hasStageResult.value);
const confirmDisabledReason = computed(() => {
  const s = snapshot.value;
  if (!s || s.stage === 'R0') return null;
  if (!keptCards.value.length) return '请至少保留一个候选';
  if (s.stage === 'R4' && plan.value && plan.value.feasibility !== 'feasible') {
    return '方案不是「可行」状态，不能确认，请调整后重新生成';
  }
  return null;
});

// 重放结果的 revision 可能比当前旧，不能用它覆盖更新的状态
function accept(next: SessionSnapshot): boolean {
  const cur = snapshot.value;
  if (cur && cur.session_id === next.session_id && next.revision < cur.revision) return false;
  if (cur && cur.stage !== next.stage) userTab.value = null;
  snapshot.value = next;
  return true;
}

async function refresh() {
  accept(await agentApi.getSession(snapshot.value!.session_id));
}

let pollToken = 0;
let polling = false;
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

async function poll() {
  if (polling) return;
  polling = true;
  const token = ++pollToken;
  try {
    while (token === pollToken && snapshot.value?.processing) {
      await sleep(POLL_MS);
      if (token !== pollToken) break;
      try {
        await refresh();
      } catch (e) {
        error.value = errorMessage(e);
        if (e instanceof ApiError && e.code === 'SESSION_NOT_FOUND') break;
      }
    }
  } finally {
    if (token === pollToken) polling = false;
  }
}

function stopPolling() {
  pollToken++;
  polling = false;
}

watch(() => snapshot.value?.processing, (p) => {
  if (p) {
    notice.value = '后端正在处理，完成后会自动刷新。';
    poll();
  } else {
    stopPolling();
    notice.value = null;
  }
});
onBeforeUnmount(stopPolling);

async function load(id: string | undefined) {
  stopPolling();
  notFound.value = false;
  snapshot.value = null;
  error.value = null;
  loading.value = true;
  try {
    if (!id) {
      const created = await agentApi.createSession();
      snapshot.value = created;
      router.replace(`/advisor/${created.session_id}`);
    } else {
      snapshot.value = await agentApi.getSession(id);
    }
  } catch (e) {
    if (e instanceof ApiError && e.code === 'SESSION_NOT_FOUND') notFound.value = true;
    error.value = errorMessage(e);
  } finally {
    loading.value = false;
  }
}

watch(() => props.id, (id) => {
  if (!snapshot.value || snapshot.value.session_id !== id) load(id);
}, { immediate: true });

const UNCERTAIN = new Set(['TIMEOUT', 'NETWORK_ERROR']);

async function recover(e: unknown, isChat: boolean) {
  if (!(e instanceof ApiError)) {
    error.value = errorMessage(e);
    return;
  }
  try {
    if (e.code === 'REVISION_CONFLICT') {
      await refresh();
      error.value = '会话已更新，请检查后重试';
    } else if (e.code === 'REQUEST_IN_PROGRESS') {
      await refresh();
      if (!snapshot.value?.processing) error.value = '上一个请求刚处理完，请检查后重试';
    } else if (UNCERTAIN.has(e.code) || e.status === 504) {
      // 请求可能已在后端提交：先查快照，不自动重发（重发会重复调用模型）
      await refresh();
      if (isChat && e.requestId && snapshot.value?.last_request_id === e.requestId) {
        notice.value = '连接中断，但请求已完成，已显示最新结果。';
      } else {
        error.value = `${e.message}（已刷新为服务端最新状态，本次请求未生效，请检查后重试）`;
      }
    } else {
      error.value = errorMessage(e);
      if (e.code === 'SESSION_NOT_FOUND') notFound.value = true;
    }
  } catch (refreshError) {
    error.value = errorMessage(refreshError);
  }
}

async function mutate(run: (s: SessionSnapshot) => Promise<SessionSnapshot>, isChat = false) {
  const s = snapshot.value;
  if (!s || locked.value) return;
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    accept(await run(s));
  } catch (e) {
    await recover(e, isChat);
  } finally {
    busy.value = false;
    pendingText.value = null;
  }
}

const send = (content: string) => {
  pendingText.value = content;
  return mutate((s) => agentApi.chat(s.session_id, {
    expected_revision: s.revision, action: 'message', content,
  }), true);
};

const generate = () => mutate((s) => agentApi.chat(s.session_id, {
  expected_revision: s.revision, action: 'generate', content: null,
}), true);

const confirm = () => mutate((s) => agentApi.confirm(s.session_id, s.revision, s.stage));

const saveProfile = (changes: ProfileChanges) =>
  mutate((s) => agentApi.patchProfile(s.session_id, s.revision, changes));

function setDecision(candidateId: string, decision: Decision) {
  const stage = snapshot.value?.stage;
  if ((stage === 'R2' || stage === 'R4') && !window.confirm('精查结论和路线将失效，回到 R1。是否继续？')) return;
  return mutate((s) => agentApi.patchCandidate(s.session_id, candidateId, s.revision, decision));
}

const open = (competitionId: string, highlight: string[]) => {
  drawer.value = { competitionId, highlight };
};
</script>

<template>
  <div v-if="notFound" class="centered panel">
    <div class="alert error">会话不存在或已过期。</div>
    <button class="primary" type="button" @click="router.push('/advisor')">新建会话</button>
  </div>

  <div v-else-if="snapshot" class="advisor">
    <StageBar :stage="snapshot.stage" :status="snapshot.status" :message="snapshot.message" />
    <div v-if="error" class="alert error" role="alert">
      {{ error }} <button class="link" type="button" @click="error = null">知道了</button>
    </div>
    <div v-if="notice" class="alert info" role="status">{{ notice }}</div>

    <div class="layout">
      <ProfilePanel :profile="snapshot.profile" :busy="locked" :has-results="cards.length > 0 || plan !== null" @save="saveProfile" />

      <ChatPanel
        :messages="snapshot.messages"
        :busy="locked"
        :pending="pendingText"
        :can-confirm="snapshot.needs_confirmation"
        :confirm-disabled-reason="confirmDisabledReason"
        :can-generate="canGenerate"
        @send="send"
        @confirm="confirm"
        @generate="generate"
      />

      <section class="results panel">
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
          :cards="cards"
          :busy="locked"
          @set-decision="setDecision"
          @open="open"
        />
        <ScorecardList v-else-if="activeTab === 'review'" :cards="analysed" @open="open" />
        <RoutePlan v-else-if="activeTab === 'route' && plan" :plan="plan" :names="names" @open="open" />
        <div v-else class="muted empty">
          <p v-if="canGenerate">点击对话框下方的「生成本阶段结果」。</p>
          <template v-else>
            <p>在左侧对话中介绍自己，我会整理出画像草案。</p>
            <p>画像确认后，这里会依次显示候选竞赛、精查结果和备赛路线。</p>
          </template>
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
    <p v-else-if="loading" class="muted">加载会话中…</p>
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
