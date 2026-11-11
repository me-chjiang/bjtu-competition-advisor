// 行为对照 docs/frontend-contract.md 第 3–5 节和 backend/service.py；模型回答是固定脚本，不做真实分析
import { ApiError } from '../client';
import type {
  AgentApi, CandidateCard, ChatParams, LlmSettings, Message, Plan, PlanTask, SessionSnapshot, Stage, WeeklyLoad,
} from '../types';
import { CANDIDATES, COMPETITIONS, DIMENSIONS, DRAFT_PROFILE, EMPTY_PROFILE, TASK_SPECS } from './fixtures';
import { addDays, clone, daysFromToday, delay, mondayOf } from './util';

const STORE_KEY = 'mock-agent-sessions';

type ReplayParams = Pick<ChatParams, 'expected_revision' | 'action' | 'content'>;
interface MockRecord {
  snapshot: SessionSnapshot;
  requests: Record<string, { params: ReplayParams; snapshot: SessionSnapshot }>;
}
type Store = Record<string, MockRecord>;

const load = (): Store => JSON.parse(localStorage.getItem(STORE_KEY) ?? '{}') as Store;
const save = (store: Store) => localStorage.setItem(STORE_KEY, JSON.stringify(store));

const llmSettings: LlmSettings = {
  configured: false,
  model: 'deepseek/deepseek-chat',
  available_models: ['deepseek/deepseek-chat', 'deepseek/deepseek-reasoner'],
};

const NEXT_STAGE: Record<Exclude<Stage, 'R4'>, Stage> = { R0: 'R1', R1: 'R2', R2: 'R4' };

const MESSAGES = {
  start: '请介绍你的专业、年级和想参加竞赛的目标。',
  R0: '我整理了一份画像草案，请在左侧核对或直接修改。确认无误后点击「确认本阶段」。',
  R1: '我粗筛出以下候选。你可以保留、待定或排除；确认后进入精查。',
  R2: '这是保留候选的精查结果，每个维度都标明了依据和不确定项。确认后生成备赛路线。',
  R4: '这是备赛路线草案，已检查每周投入。确认后完成本次推荐。',
  confirmed: '当前结果已确认，请生成下一阶段草案。',
  completed: '方案已确认。',
  profile: '画像已更新，请重新核对后继续。',
  candidate: '候选已更新，请重新确认筛选结果。',
} as const;

function get(store: Store, id: string): MockRecord {
  const rec = store[id];
  if (!rec) throw new ApiError('SESSION_NOT_FOUND', '会话不存在或已过期', 404);
  return rec;
}

function checkRevision(snapshot: SessionSnapshot, expected: number) {
  if (snapshot.revision !== expected) {
    throw new ApiError(
      'REVISION_CONFLICT', '会话已更新，请刷新后重试。', 409, false, { current_revision: snapshot.revision },
    );
  }
}

const message = (role: Message['role'], content: string): Message => ({
  id: crypto.randomUUID(), role, content, created_at: new Date().toISOString(),
});

function commit(store: Store, rec: MockRecord): SessionSnapshot {
  rec.snapshot.revision += 1;
  save(store);
  return clone(rec.snapshot);
}

const hasAnalysis = (cards: CandidateCard[]) => cards.some((c) => c.dimensions.length > 0);

// 对照 backend 的 evaluate_plan：未知工时或日期不计入负载，只能得到 unknown，不能当作可行
export function buildPlan(cards: CandidateCard[], budget: number | null): Plan {
  const selected = cards.filter((c) => c.decision === 'keep' && c.dimensions.length > 0)
    .map((c) => c.competition_instance_id);
  const tasks: PlanTask[] = selected.flatMap((id) => (TASK_SPECS[id] ?? []).map((t, i) => ({
    id: `${id}-t${i + 1}`,
    competition_instance_id: id,
    title: t.title,
    estimated_hours: t.hours,
    acceptance_criteria: t.acceptance,
    start_date: t.startOffset === null ? null : daysFromToday(t.startOffset),
    due_date: t.dueOffset === null ? null : daysFromToday(t.dueOffset),
  })));

  const load = new Map<string, number>();
  const assumptions = ['任务工时是 mock 估算，按任务跨越的周数平均分配'];
  for (const t of tasks) {
    if (t.estimated_hours === null || !t.start_date || !t.due_date) {
      assumptions.push(`「${t.title}」的工时或日期待定，未计入每周负载`);
      continue;
    }
    const weeks: string[] = [];
    for (let w = mondayOf(t.start_date); w <= t.due_date; w = addDays(w, 7)) weeks.push(w);
    for (const w of weeks) load.set(w, (load.get(w) ?? 0) + t.estimated_hours / weeks.length);
  }

  const weekly_load: WeeklyLoad[] = [...load.entries()].sort(([a], [b]) => a.localeCompare(b))
    .map(([week_start, hours]) => ({
      week_start, estimated_hours: Math.round(hours * 10) / 10, budget_hours: budget,
    }));
  const conflicts = budget === null ? [] : weekly_load
    .filter((w) => w.estimated_hours! > budget)
    .map((w) => `${w.week_start} 起一周计划 ${w.estimated_hours} 小时，超过每周预算 ${budget} 小时`);
  const incomplete = budget === null || assumptions.length > 1;
  return {
    selected_competition_ids: selected,
    tasks,
    weekly_load,
    conflicts,
    assumptions,
    feasibility: conflicts.length ? 'infeasible' : incomplete ? 'unknown' : 'feasible',
  };
}

function invalid(msg: string): never {
  throw new ApiError('VALIDATION_ERROR', msg, 422);
}

export const mockAgentApi: AgentApi = {
  async createSession() {
    await delay();
    const store = load();
    const snapshot: SessionSnapshot = {
      session_id: `mock-${crypto.randomUUID().slice(0, 8)}`,
      revision: 0,
      stage: 'R0',
      status: 'collecting',
      processing: false,
      last_request_id: null,
      message: MESSAGES.start,
      messages: [],
      profile: clone(EMPTY_PROFILE),
      cards: [],
      plan: null,
      needs_confirmation: false,
    };
    store[snapshot.session_id] = { snapshot, requests: {} };
    save(store);
    return clone(snapshot);
  },

  async getSession(id) {
    await delay(150);
    return clone(get(load(), id).snapshot);
  },

  async chat(id, params) {
    await delay(700);
    const requestId = params.request_id ?? crypto.randomUUID();
    const body: ReplayParams = {
      expected_revision: params.expected_revision, action: params.action, content: params.content,
    };
    const store = load();
    const rec = get(store, id);
    const cached = rec.requests[requestId];
    if (cached) {
      if (JSON.stringify(cached.params) !== JSON.stringify(body)) {
        throw new ApiError('REQUEST_ID_REUSED', '请求 ID 已用于不同请求。', 409, false, null, requestId);
      }
      return clone(cached.snapshot);
    }
    const s = rec.snapshot;
    try {
      checkRevision(s, params.expected_revision);
    } catch (e) {
      if (e instanceof ApiError) throw new ApiError(e.code, e.message, e.status, e.retryable, e.details, requestId);
      throw e;
    }
    if (params.action === 'message' && !params.content?.trim()) invalid('消息不能为空');
    if (params.action === 'generate' && (params.content !== null || s.stage === 'R0')) {
      invalid('R0 阶段只能通过对话生成画像');
    }

    let reply: string;
    if (params.action === 'message') {
      if (s.stage === 'R0') {
        const p = s.profile;
        s.profile = {
          ...p,
          grade: p.grade ?? DRAFT_PROFILE.grade,
          major: p.major ?? DRAFT_PROFILE.major,
          skills: p.skills.length ? p.skills : clone(DRAFT_PROFILE.skills),
          weekly_hours: p.weekly_hours ?? DRAFT_PROFILE.weekly_hours,
          goals: p.goals.length ? p.goals : clone(DRAFT_PROFILE.goals),
          team_preference: p.team_preference ?? DRAFT_PROFILE.team_preference,
        };
        s.status = 'awaiting_review';
        s.needs_confirmation = true;
        reply = MESSAGES.R0;
      } else {
        reply = `收到：「${params.content}」。（mock 不做真实分析）`;
      }
      s.messages.push(message('user', params.content!));
    } else if (s.stage === 'R1') {
      const previous = new Map(s.cards.map((c) => [c.competition_instance_id, c.decision]));
      s.cards = clone(CANDIDATES).map((c) => ({ ...c, decision: previous.get(c.competition_instance_id) ?? c.decision }));
      s.plan = null;
      reply = MESSAGES.R1;
    } else if (s.stage === 'R2') {
      s.cards = s.cards.map((c) => ({ ...c, dimensions: clone(DIMENSIONS[c.competition_instance_id] ?? []) }));
      s.plan = null;
      reply = MESSAGES.R2;
    } else {
      s.plan = buildPlan(s.cards, s.profile.weekly_hours);
      reply = MESSAGES.R4;
    }
    if (params.action === 'generate') {
      s.status = 'awaiting_review';
      s.needs_confirmation = true;
    }
    s.message = reply;
    s.messages.push(message('assistant', reply));
    s.last_request_id = requestId;
    const result = commit(store, rec);
    rec.requests[requestId] = { params: body, snapshot: clone(result) };
    save(store);
    return result;
  },

  async patchProfile(id, expectedRevision, changes) {
    await delay();
    const store = load();
    const rec = get(store, id);
    const s = rec.snapshot;
    checkRevision(s, expectedRevision);
    const changed = (Object.keys(changes) as (keyof typeof changes)[])
      .filter((k) => JSON.stringify(changes[k]) !== JSON.stringify(s.profile[k]));
    if (!changed.length) return clone(s);
    const { skills, ...rest } = clone(changes);
    s.profile = {
      ...s.profile,
      ...rest,
      ...(skills && { skills: skills.map((k) => ({ name: k.name, evidence: k.evidence ?? null })) }),
    };
    s.stage = 'R0';
    s.status = 'collecting';
    s.needs_confirmation = false;
    s.cards = [];
    s.plan = null;
    s.message = MESSAGES.profile;
    return commit(store, rec);
  },

  async patchCandidate(id, candidateId, expectedRevision, decision) {
    await delay(200);
    const store = load();
    const rec = get(store, id);
    const s = rec.snapshot;
    checkRevision(s, expectedRevision);
    if (s.stage === 'R0') throw new ApiError('INVALID_STAGE', '当前阶段不能修改候选。', 409);
    const card = s.cards.find((c) => c.competition_instance_id === candidateId);
    if (!card) throw new ApiError('COMPETITION_NOT_FOUND', '当前候选不存在。', 404);
    if (decision === 'keep' && card.eligibility === 'ineligible') {
      invalid('存在明确资格冲突或报名已经截止，不能保留。');
    }
    if (card.decision === decision) return clone(s);
    card.decision = decision;
    if (s.stage !== 'R1') {
      s.cards = s.cards.map((c) => ({ ...c, dimensions: [] }));
      s.stage = 'R1';
    }
    s.plan = null;
    s.status = 'awaiting_review';
    s.needs_confirmation = true;
    s.message = MESSAGES.candidate;
    return commit(store, rec);
  },

  async confirm(id, expectedRevision, stage) {
    await delay(300);
    const store = load();
    const rec = get(store, id);
    const s = rec.snapshot;
    checkRevision(s, expectedRevision);
    if (s.stage !== stage || s.status !== 'awaiting_review') {
      throw new ApiError('INVALID_STAGE', '当前阶段没有可确认的结果。', 409);
    }
    if (stage !== 'R0') {
      const kept = s.cards.filter((c) => c.decision === 'keep');
      if (!kept.length || kept.some((c) => c.eligibility === 'ineligible')) {
        invalid('请保留至少一个没有明确资格冲突的候选。');
      }
      if ((stage === 'R2' || stage === 'R4') && !hasAnalysis(kept)) invalid('请先生成保留候选的精查结果。');
      if (stage === 'R4') {
        if (!s.plan) invalid('请先生成路线。');
        if (s.plan!.feasibility !== 'feasible') invalid('路线存在冲突或未知信息，不能确认为可行方案。');
      }
    }
    if (stage === 'R4') {
      s.status = 'completed';
      s.message = MESSAGES.completed;
    } else {
      s.stage = NEXT_STAGE[stage];
      s.status = 'collecting';
      s.message = MESSAGES.confirmed;
    }
    s.needs_confirmation = false;
    return commit(store, rec);
  },

  async getCompetition(id) {
    await delay(200);
    const c = COMPETITIONS.find((x) => x.competition_instance_id === id);
    if (!c) throw new ApiError('COMPETITION_NOT_FOUND', '竞赛不存在', 404);
    return clone(c);
  },

  async getLlmSettings() {
    await delay(100);
    return clone(llmSettings);
  },

  async patchLlmSettings(patch) {
    await delay(100);
    if (patch.model != null && !llmSettings.available_models.includes(patch.model)) {
      invalid('请求字段无效，请检查后重试。');
    }
    // mock 只记录"已配置"，不保存 key 本身
    if (patch.api_key) llmSettings.configured = true;
    if (patch.model) llmSettings.model = patch.model;
    return clone(llmSettings);
  },
};
