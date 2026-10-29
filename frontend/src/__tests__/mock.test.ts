import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildPlan, mockAgentApi as api } from '../api/mock/agent';
import { CANDIDATES } from '../api/mock/fixtures';
import type { CandidateCard, LoginForm, SessionSnapshot } from '../api/types';

// 模拟网络延迟只影响演示手感，测试里跳过
vi.mock('../api/mock/util', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/mock/util')>()),
  delay: () => Promise.resolve(),
}));

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers({ shouldAdvanceTime: true, advanceTimeDelta: 50 });
});

// resetModules 后 ApiError 是另一个类实例，所以按 code 判断而不是 instanceof
async function expectCode(p: Promise<unknown>, code: string) {
  await expect(p).rejects.toMatchObject({ code });
}

const say = (s: SessionSnapshot, content = '大二计算机，会 Python') =>
  api.chat(s.session_id, { expected_revision: s.revision, action: 'message', content });
const generate = (s: SessionSnapshot) =>
  api.chat(s.session_id, { expected_revision: s.revision, action: 'generate', content: null });
const confirm = (s: SessionSnapshot) => api.confirm(s.session_id, s.revision, s.stage);

// 推进到指定阶段的 collecting 状态（尚未生成该阶段结果）
async function toStage(stage: 'R1' | 'R2' | 'R4') {
  let s = await api.createSession();
  s = await confirm(await say(s));
  if (stage === 'R1') return s;
  s = await confirm(await generate(s));
  if (stage === 'R2') return s;
  return confirm(await generate(s));
}

describe('mock agent 主线', () => {
  it('R0 → R1 → R2 → R4 → completed，每步 revision 加 1，刷新后可恢复', async () => {
    let s = await api.createSession();
    expect(s).toMatchObject({ stage: 'R0', status: 'collecting', revision: 0, plan: null, cards: [] });

    s = await say(s);
    expect(s).toMatchObject({ stage: 'R0', status: 'awaiting_review', needs_confirmation: true, revision: 1 });
    expect(s.profile.major).toBe('计算机科学与技术');
    expect(s.messages.map((m) => m.role)).toEqual(['user', 'assistant']);

    s = await confirm(s);
    expect(s).toMatchObject({ stage: 'R1', status: 'collecting', needs_confirmation: false, cards: [] });
    s = await generate(s);
    expect(s).toMatchObject({ stage: 'R1', status: 'awaiting_review', needs_confirmation: true });
    expect(s.cards.length).toBe(CANDIDATES.length);

    s = await confirm(s);
    expect(s).toMatchObject({ stage: 'R2', status: 'collecting' });
    expect(s.cards.every((c) => c.dimensions.length === 0)).toBe(true);
    s = await generate(s);
    expect(s.cards.some((c) => c.dimensions.length > 0)).toBe(true);

    s = await confirm(s);
    expect(s).toMatchObject({ stage: 'R4', status: 'collecting', plan: null });
    s = await generate(s);
    expect(s.plan?.feasibility).toBe('feasible');
    s = await confirm(s);
    expect(s).toMatchObject({ stage: 'R4', status: 'completed', needs_confirmation: false });

    expect(await api.getSession(s.session_id)).toEqual(s);
  });

  it('confirm 不会自动生成下一阶段，必须显式 generate', async () => {
    const s = await toStage('R1');
    expect(s.cards).toEqual([]);
    expect(s.needs_confirmation).toBe(false);
    await expectCode(confirm(s), 'INVALID_STAGE');
  });

  it('R0 阶段不能 generate，message 内容不能为空', async () => {
    const s = await api.createSession();
    await expectCode(generate(s), 'VALIDATION_ERROR');
    await expectCode(say(s, '   '), 'VALIDATION_ERROR');
  });

  it('不存在的会话返回 SESSION_NOT_FOUND', async () => {
    await expectCode(api.getSession('nope'), 'SESSION_NOT_FOUND');
  });
});

describe('mock agent 并发与重放', () => {
  it('旧 revision 被 REVISION_CONFLICT 拒绝，并带上当前版本', async () => {
    const s0 = await api.createSession();
    await say(s0);
    await expect(say(s0)).rejects.toMatchObject({ code: 'REVISION_CONFLICT', status: 409, details: { current_revision: 1 } });
    await expectCode(api.confirm(s0.session_id, 0, 'R0'), 'REVISION_CONFLICT');
    await expectCode(api.patchProfile(s0.session_id, 0, { grade: '大三' }), 'REVISION_CONFLICT');
  });

  it('相同 request_id 重放返回缓存结果，不再次修改；请求体不同则 REQUEST_ID_REUSED', async () => {
    const s0 = await api.createSession();
    const params = { request_id: 'req-1', expected_revision: 0, action: 'message' as const, content: '你好' };
    const first = await api.chat(s0.session_id, params);
    const live = await confirm(first);
    expect(first.last_request_id).toBe('req-1');

    // 重放先于 revision 检查：用已过期的版本号重发同一请求仍得到原结果
    const replay = await api.chat(s0.session_id, params);
    expect(replay).toEqual(first);
    expect(replay.revision).toBeLessThan(live.revision);
    expect((await api.getSession(s0.session_id)).revision).toBe(live.revision);

    await expectCode(api.chat(s0.session_id, { ...params, content: '另一句' }), 'REQUEST_ID_REUSED');
  });
});

describe('mock agent 失效规则', () => {
  it('画像有改动：回到 R0 并清空候选和路线；无改动不增加 revision', async () => {
    let s = await toStage('R4');
    s = await generate(s);
    expect(s.plan).not.toBeNull();

    const same = await api.patchProfile(s.session_id, s.revision, { weekly_hours: s.profile.weekly_hours });
    expect(same.revision).toBe(s.revision);

    const next = await api.patchProfile(s.session_id, s.revision, { weekly_hours: 4, goals: ['竞赛经历'] });
    expect(next).toMatchObject({ stage: 'R0', status: 'collecting', needs_confirmation: false, cards: [], plan: null });
    expect(next.profile).toMatchObject({ weekly_hours: 4, goals: ['竞赛经历'], major: s.profile.major });
    expect(next.revision).toBe(s.revision + 1);
  });

  it('R2/R4 修改候选：回到 R1 awaiting_review，清除精查结论和方案，保留粗筛决定', async () => {
    let s = await toStage('R2');
    s = await generate(s);
    expect(s.cards.some((c) => c.dimensions.length)).toBe(true);

    s = await api.patchCandidate(s.session_id, 'c-data', s.revision, 'exclude');
    expect(s).toMatchObject({ stage: 'R1', status: 'awaiting_review', needs_confirmation: true, plan: null });
    expect(s.cards.every((c) => c.dimensions.length === 0)).toBe(true);
    expect(s.cards.find((c) => c.competition_instance_id === 'c-data')?.decision).toBe('exclude');
    expect(s.cards.find((c) => c.competition_instance_id === 'c-algo')?.decision).toBe('keep');
  });

  it('R1 修改候选仍在 R1；R0 不能修改候选', async () => {
    const r0 = await say(await api.createSession());
    await expectCode(api.patchCandidate(r0.session_id, 'c-algo', r0.revision, 'defer'), 'INVALID_STAGE');
    let s = await generate(await confirm(r0));
    s = await api.patchCandidate(s.session_id, 'c-algo', s.revision, 'defer');
    expect(s.stage).toBe('R1');
    await expectCode(api.patchCandidate(s.session_id, 'nope', s.revision, 'keep'), 'COMPETITION_NOT_FOUND');
  });

  it('资格冲突的候选不能设为 keep', async () => {
    let s = await generate(await toStage('R1'));
    const math = s.cards.find((c) => c.competition_instance_id === 'c-math')!;
    expect(math.eligibility).toBe('ineligible');
    await expectCode(api.patchCandidate(s.session_id, 'c-math', s.revision, 'keep'), 'VALIDATION_ERROR');
    s = await api.patchCandidate(s.session_id, 'c-math', s.revision, 'defer');
    expect(s.cards.find((c) => c.competition_instance_id === 'c-math')?.decision).toBe('defer');
  });

  it('没有保留候选时不能确认 R1；重新生成保留用户的决定', async () => {
    let s = await generate(await toStage('R1'));
    s = await api.patchCandidate(s.session_id, 'c-algo', s.revision, 'defer');
    s = await api.patchCandidate(s.session_id, 'c-model', s.revision, 'defer');
    await expectCode(confirm(s), 'VALIDATION_ERROR');
    s = await generate(s);
    expect(s.cards.find((c) => c.competition_instance_id === 'c-algo')?.decision).toBe('defer');
  });

  it('不可行的方案不能确认 R4', async () => {
    let s = await generate(await toStage('R1'));
    s = await api.patchCandidate(s.session_id, 'c-robot', s.revision, 'keep');
    s = await generate(await confirm(s));
    s = await generate(await confirm(s));
    expect(s.plan?.feasibility).toBe('infeasible');
    expect(s.plan?.conflicts.length).toBeGreaterThan(0);
    await expectCode(confirm(s), 'VALIDATION_ERROR');
  });
});

describe('buildPlan', () => {
  const kept = (ids: string[]): CandidateCard[] => CANDIDATES.map((c) => ({
    ...structuredClone(c),
    decision: ids.includes(c.competition_instance_id) ? 'keep' : 'exclude',
    dimensions: [{ name: 'goal_value', assessment: 'x', basis: 'inferred', evidence_ids: [], uncertainties: [] }],
  }));

  it('周一对齐，预算对比负载，超出预算判为 infeasible', () => {
    const plan = buildPlan(kept(['c-algo', 'c-robot']), 8);
    expect(plan.weekly_load.every((w) => new Date(`${w.week_start}T00:00:00Z`).getUTCDay() === 1)).toBe(true);
    expect(plan.feasibility).toBe('infeasible');
    expect(plan.conflicts.length).toBeGreaterThan(0);
  });

  it('预算或任务工时、日期未知时为 unknown，未知任务不计入负载', () => {
    expect(buildPlan(kept(['c-algo']), null).feasibility).toBe('unknown');
    const plan = buildPlan(kept(['c-data']), 8);
    expect(plan.feasibility).toBe('unknown');
    expect(plan.weekly_load).toEqual([]);
    expect(plan.tasks[0]).toMatchObject({ estimated_hours: null, start_date: null, due_date: null });
  });

  it('预算内且信息完整时为 feasible', () => {
    expect(buildPlan(kept(['c-algo', 'c-model']), 8).feasibility).toBe('feasible');
  });
});

describe('mock MIS 登录', () => {
  it('验证码错误会返回新验证码和剩余次数，用完后失败', async () => {
    vi.resetModules();
    const { mockMisApi: mis } = await import('../api/mock/mis');
    let step = await mis.startLogin();
    expect(step.state).toBe('form');
    const id = (step as LoginForm).login_id;
    for (const left of [2, 1]) {
      step = await mis.submitLogin(id, { loginname: 'u', password: 'p', captcha_1: 'wrong' });
      expect(step).toMatchObject({ state: 'form', error: '验证码错误', attempts_left: left });
    }
    step = await mis.submitLogin(id, { loginname: 'u', password: 'p', captcha_1: 'wrong' });
    expect(step.state).toBe('failed');
    await expectCode(mis.submitLogin(id, {}), 'LOGIN_NOT_FOUND');
  });

  it('登录成功后可以采集，再次登录直接复用登录态', async () => {
    vi.resetModules();
    const { mockMisApi: mis } = await import('../api/mock/mis');
    await expectCode(mis.startCrawl(), 'NOT_LOGGED_IN');
    const form = (await mis.startLogin()) as LoginForm;
    const svg = atob(form.captcha!.split(',')[1]);
    const [, a, b] = svg.match(/(\d+)×(\d+)=/)!;
    const step = await mis.submitLogin(form.login_id, {
      loginname: 'u', password: 'p', captcha_1: String(Number(a) * Number(b)),
    });
    expect(step.state).toBe('success');
    expect((await mis.startLogin()).state).toBe('already_logged_in');

    expect((await mis.startCrawl()).state).toBe('running');
    await vi.advanceTimersByTimeAsync(4000);
    expect(await mis.crawlStatus()).toMatchObject({ state: 'done', counts: { cpitem: 712, signup_rounds: 43 } });
  });
});
