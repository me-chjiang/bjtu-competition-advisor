import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildRoute, mockAgentApi as api } from '../api/mock/agent';
import type { LoginForm } from '../api/types';

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers({ shouldAdvanceTime: true, advanceTimeDelta: 50 });
});

// resetModules 后 ApiError 是另一个类实例，所以按 code 判断而不是 instanceof
async function expectCode(p: Promise<unknown>, code: string) {
  await expect(p).rejects.toMatchObject({ code });
}

describe('mock agent 主线', () => {
  it('R0 → R1 → R2 → R4 → done，刷新后可恢复', async () => {
    const s = await api.createSession();
    expect(s.stage).toBe('profile');

    let r = await api.chat(s.id, '大二计算机，会 Python');
    expect(r.needs_confirmation).toBe(true);
    expect(r.profile.major).toBe('计算机科学与技术');

    r = await api.confirm(s.id, 'profile');
    expect(r.stage).toBe('screen');
    expect(r.profile.confirmed).toBe(true);

    await api.patchCandidate(s.id, 'cand-robot', 'kept');
    r = await api.confirm(s.id, 'screen');
    expect(r.stage).toBe('review');
    const scorecardIds = r.cards.filter((c) => c.kind === 'scorecard').map((c) => c.competition_id);
    expect(scorecardIds).toContain('c-robot');
    expect(scorecardIds).not.toContain('c-design');

    await expectCode(api.confirm(s.id, 'review', []), 'VALIDATION_ERROR');
    r = await api.confirm(s.id, 'review', ['c-algo', 'c-model']);
    expect(r.stage).toBe('route');
    const route = r.cards.find((c) => c.kind === 'route');
    expect(route?.kind === 'route' && route.items.map((i) => i.competition_id)).toEqual(['c-algo', 'c-model']);

    r = await api.confirm(s.id, 'route');
    expect(r.stage).toBe('done');
    expect(r.needs_confirmation).toBe(false);

    const restored = await api.getSession(s.id);
    expect(restored.stage).toBe('done');
    expect(restored.messages.length).toBe(s.messages.length + 2 + 4);
  });

  it('重复确认同一阶段返回 STAGE_MISMATCH', async () => {
    const s = await api.createSession();
    await api.chat(s.id, 'hi');
    await api.confirm(s.id, 'profile');
    await expectCode(api.confirm(s.id, 'profile'), 'STAGE_MISMATCH');
  });

  it('修改画像后结果标记为待更新，再次对话后清除', async () => {
    const s = await api.createSession();
    await api.chat(s.id, 'hi');
    await api.confirm(s.id, 'profile');
    const { profile, cards } = await api.patchProfile(s.id, { weekly_hours: 3 });
    expect(profile.weekly_hours).toBe(3);
    expect(cards.every((c) => c.stale)).toBe(true);
    const r = await api.chat(s.id, '请更新');
    expect(r.cards.some((c) => c.stale)).toBe(false);
  });

  it('路线阶段重新生成后所有卡片都不再待更新', async () => {
    const s = await api.createSession();
    await api.chat(s.id, 'hi');
    await api.confirm(s.id, 'profile');
    await api.confirm(s.id, 'screen');
    await api.confirm(s.id, 'review', ['c-algo', 'c-model']);
    await api.patchProfile(s.id, { weekly_hours: 15 });
    const r = await api.chat(s.id, '请更新');
    expect(r.cards.some((c) => c.stale)).toBe(false);
    const route = r.cards.find((c) => c.kind === 'route');
    expect(route?.kind === 'route' && route.conflicts).toEqual([]);
  });

  it('硬性排除的候选不能恢复', async () => {
    const s = await api.createSession();
    await api.chat(s.id, 'hi');
    await api.confirm(s.id, 'profile');
    await expectCode(api.patchCandidate(s.id, 'cand-math', 'kept'), 'CANDIDATE_LOCKED');
  });

  it('不存在的会话返回 SESSION_NOT_FOUND', async () => {
    await expectCode(api.getSession('nope'), 'SESSION_NOT_FOUND');
  });
});

describe('buildRoute', () => {
  it('统计高峰周投入并标出超出可投入时间的冲突', () => {
    const route = buildRoute(['c-algo', 'c-model'], 8);
    // 11-01 那一周：图论 4h + 论文 3h + 模拟 5h
    expect(route.weekly_hours_total).toBe(12);
    expect(route.conflicts.length).toBeGreaterThan(0);
    expect(route.conflicts[0].competition_ids).toEqual(['c-algo', 'c-model']);
  });

  it('未知日期的任务列入待核实，不计入每周总投入', () => {
    const route = buildRoute(['c-data'], 8);
    expect(route.weekly_hours_total).toBe(0);
    expect(route.conflicts).toEqual([]);
    expect(route.pending_checks[0]).toContain('日期待定');
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
