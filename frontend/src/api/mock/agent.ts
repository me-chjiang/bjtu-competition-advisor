import { ApiError } from '../client';
import type {
  AgentApi, CandidateCard, Card, ChatResponse, Message, Profile, RouteCard, Session, Stage,
} from '../types';
import { STAGES } from '../types';
import { CANDIDATES, COMPETITIONS, DRAFT_PROFILE, ROUTE_TASKS, SCORECARDS } from './fixtures';
import { clone, delay } from './util';

const STORE_KEY = 'mock-agent-sessions';

const EMPTY_PROFILE: Profile = {
  grade: null, major: null, discipline: null, skills: [], weekly_hours: null, goals: [],
  team_preference: null, domains: [], notes: null, version: 0, confirmed: false,
};

const STAGE_PROMPTS: Record<Stage, string> = {
  profile: '我整理了一份画像草案，请在右侧核对或直接修改。确认无误后点击「确认」进入粗筛。',
  screen: '根据已确认的画像，我粗筛出以下候选，按领域分组。你可以保留、排除或恢复；确认后进入精查。',
  review: '这是保留候选的证据卡片。可以切换排序依据，勾选想要准备的竞赛，确认后生成备赛路线。',
  route: '这是针对所选竞赛的备赛路线，已检查每周总投入和日期冲突。确认后完成本次推荐。',
  done: '本次推荐已完成。你仍然可以修改画像，修改后相关结果会标记为待更新。',
};

type Store = Record<string, Session & { selected: string[] }>;

const load = (): Store => JSON.parse(localStorage.getItem(STORE_KEY) ?? '{}') as Store;
const save = (store: Store) => localStorage.setItem(STORE_KEY, JSON.stringify(store));

function getStored(store: Store, id: string) {
  const s = store[id];
  if (!s) throw new ApiError('SESSION_NOT_FOUND', '会话不存在或已过期', 404);
  return s;
}

function message(role: Message['role'], content: string): Message {
  return { id: crypto.randomUUID(), role, content, created_at: new Date().toISOString() };
}

function candidateCards(): CandidateCard[] {
  return clone(CANDIDATES);
}

function scorecardCards(candidates: CandidateCard[]): Card[] {
  return candidates
    .filter((c) => c.status === 'kept')
    .map((c) => ({ kind: 'scorecard' as const, stale: false, ...clone(SCORECARDS[c.competition_id]) }))
    .filter((c) => c.id);
}

// 参考 plan.md 中的 check_plan_feasibility：按「每个任务开始的那一周」统计并行投入
export function buildRoute(selected: string[], weeklyAvailable: number | null): RouteCard {
  const items = selected.map((id) => ({
    competition_id: id,
    name: COMPETITIONS.find((c) => c.id === id)?.name ?? id,
    tasks: clone(ROUTE_TASKS[id] ?? []),
  }));
  const dated = items.flatMap((item) => item.tasks
    .filter((t) => t.start && t.end)
    .map((t) => ({ ...t, competition_id: item.competition_id, name: item.name })));

  let peak = 0;
  const conflicts: RouteCard['conflicts'] = [];
  const seen = new Set<string>();
  for (const week of [...new Set(dated.map((t) => t.start!))].sort()) {
    const active = dated.filter((t) => t.start! <= week && week <= t.end!);
    const load = active.reduce((sum, t) => sum + t.hours_per_week, 0);
    peak = Math.max(peak, load);
    const ids = [...new Set(active.map((t) => t.competition_id))];
    const key = ids.sort().join(',');
    if (weeklyAvailable !== null && load > weeklyAvailable && !seen.has(key)) {
      seen.add(key);
      const names = [...new Set(active.map((t) => t.name))].join('、');
      conflicts.push({
        description: `${week} 起：${names} 合计每周 ${load} 小时，超过可投入的 ${weeklyAvailable} 小时`,
        competition_ids: ids,
      });
    }
  }

  const pending_checks = items.flatMap((item) => item.tasks
    .filter((t) => t.date_certainty === 'unknown')
    .map((t) => `${item.name}：「${t.title}」日期待定，未计入每周总投入`));

  return {
    kind: 'route', id: 'route', items, weekly_hours_total: peak,
    weekly_hours_available: weeklyAvailable, conflicts, pending_checks, stale: false,
  };
}

function cardsFor(stage: Stage, s: Session & { selected: string[] }): Card[] {
  const candidates = s.cards
    .filter((c): c is CandidateCard => c.kind === 'candidate')
    .map((c) => ({ ...c, stale: false }));
  if (stage === 'screen') return candidates.length ? candidates : candidateCards();
  if (stage === 'review') return [...candidates, ...scorecardCards(candidates)];
  if (stage === 'route' || stage === 'done') {
    const keep = s.cards.filter((c) => c.kind !== 'route').map((c) => ({ ...c, stale: false }));
    return [...keep, buildRoute(s.selected, s.profile.weekly_hours)];
  }
  return [];
}

function respond(s: Session, msg: Message): ChatResponse {
  return { message: msg, stage: s.stage, profile: s.profile, cards: s.cards, needs_confirmation: s.needs_confirmation };
}

export const mockAgentApi: AgentApi = {
  async createSession() {
    await delay();
    const store = load();
    const session = {
      id: `mock-${crypto.randomUUID().slice(0, 8)}`,
      stage: 'profile' as Stage,
      messages: [message('assistant',
        '你好！我会帮你从北交大 MIS 上的竞赛中找到适合你的。先简单介绍一下自己吧：年级、专业、掌握的技能、每周能投入多少时间，以及参赛目标（如保研、简历）。')],
      profile: clone(EMPTY_PROFILE),
      cards: [],
      needs_confirmation: false,
      selected: [],
    };
    store[session.id] = session;
    save(store);
    return clone(session);
  },

  async getSession(id) {
    await delay(150);
    return clone(getStored(load(), id));
  },

  async chat(id, content) {
    await delay(700);
    const store = load();
    const s = getStored(store, id);
    s.messages.push(message('user', content));
    let reply: string;
    if (s.stage === 'profile') {
      s.profile = { ...s.profile, ...clone(DRAFT_PROFILE), notes: content, version: s.profile.version + 1 };
      s.needs_confirmation = true;
      reply = STAGE_PROMPTS.profile;
    } else if (s.cards.some((c) => c.stale)) {
      s.cards = cardsFor(s.stage, s);
      reply = '已根据最新画像更新当前阶段的结果。';
    } else {
      reply = `收到：「${content}」。（mock 不做真实分析）${STAGE_PROMPTS[s.stage]}`;
    }
    const msg = message('assistant', reply);
    s.messages.push(msg);
    save(store);
    return clone(respond(s, msg));
  },

  async patchProfile(id, patch) {
    await delay();
    const store = load();
    const s = getStored(store, id);
    s.profile = { ...s.profile, ...clone(patch), version: s.profile.version + 1 };
    s.cards = s.cards.map((c) => ({ ...c, stale: true }));
    save(store);
    return clone({ profile: s.profile, cards: s.cards });
  },

  async confirm(id, stage, selectedCompetitionIds) {
    await delay(700);
    const store = load();
    const s = getStored(store, id);
    if (stage !== s.stage || !s.needs_confirmation) {
      throw new ApiError('STAGE_MISMATCH', '当前阶段已变化，请刷新后重试', 409);
    }
    if (stage === 'review') {
      if (!selectedCompetitionIds?.length) throw new ApiError('VALIDATION_ERROR', '请至少勾选一项竞赛', 422);
      s.selected = [...selectedCompetitionIds];
    }
    if (stage === 'profile') s.profile.confirmed = true;
    s.stage = STAGES[STAGES.indexOf(stage) + 1];
    s.cards = cardsFor(s.stage, s);
    s.needs_confirmation = s.stage !== 'done';
    const msg = message('assistant', STAGE_PROMPTS[s.stage]);
    s.messages.push(msg);
    save(store);
    return clone(respond(s, msg));
  },

  async patchCandidate(id, candidateId, status) {
    await delay(200);
    const store = load();
    const s = getStored(store, id);
    const card = s.cards.find((c): c is CandidateCard => c.kind === 'candidate' && c.id === candidateId);
    if (!card) throw new ApiError('CANDIDATE_NOT_FOUND', '候选不存在', 404);
    if (card.exclusion?.type === 'hard') throw new ApiError('CANDIDATE_LOCKED', '该候选因明确冲突被排除，不能恢复', 409);
    card.status = status;
    card.exclusion = status === 'excluded' ? { type: 'user', reason: '用户排除', evidence_ids: [] } : null;
    save(store);
    return clone({ card });
  },

  async getCompetition(id) {
    await delay(200);
    const c = COMPETITIONS.find((x) => x.id === id);
    if (!c) throw new ApiError('COMPETITION_NOT_FOUND', '竞赛不存在', 404);
    return clone(c);
  },
};
