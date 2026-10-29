import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryHistory, createRouter } from 'vue-router';
import { ApiError } from '../api/client';
import { CANDIDATES, DIMENSIONS, DRAFT_PROFILE } from '../api/mock/fixtures';
import type { CandidateCard, LoginForm, Plan, SessionSnapshot } from '../api/types';
import CandidateList from '../components/CandidateList.vue';
import DynamicForm from '../components/DynamicForm.vue';
import LlmSettingsDialog from '../components/LlmSettingsDialog.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import RoutePlan from '../components/RoutePlan.vue';
import ScorecardList from '../components/ScorecardList.vue';
import StageBar from '../components/StageBar.vue';
import { llmDialogOpen } from '../llm-dialog';
import AdvisorView from '../views/AdvisorView.vue';

const api = vi.hoisted(() => ({
  createSession: vi.fn(),
  getSession: vi.fn(),
  chat: vi.fn(),
  patchProfile: vi.fn(),
  patchCandidate: vi.fn(),
  confirm: vi.fn(),
  getCompetition: vi.fn(),
  getLlmSettings: vi.fn(),
  patchLlmSettings: vi.fn(),
}));
vi.mock('../api', () => ({ agentApi: api, apiModes: { mis: 'mock', agent: 'mock' } }));

const loginForm = (extra: Partial<LoginForm> = {}): LoginForm => ({
  state: 'form',
  login_id: 'l1',
  fields: [
    { name: 'user_x', label: '账号', kind: 'text' },
    { name: 'pwd_y', label: '口令', kind: 'password' },
    { name: 'cap_z', label: '算式结果', kind: 'captcha' },
  ],
  captcha: 'data:image/png;base64,AAAA',
  error: null,
  attempts_left: 3,
  ...extra,
});

const cards = (): CandidateCard[] => structuredClone(CANDIDATES);
const analysed = (): CandidateCard[] =>
  cards().map((c) => ({ ...c, dimensions: structuredClone(DIMENSIONS[c.competition_instance_id] ?? []) }));

function snap(over: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    session_id: 's1',
    revision: 3,
    stage: 'R1',
    status: 'awaiting_review',
    processing: false,
    last_request_id: null,
    message: '请确认粗筛结果',
    messages: [],
    profile: structuredClone(DRAFT_PROFILE),
    cards: cards(),
    plan: null,
    needs_confirmation: true,
    ...over,
  };
}

const plan = (over: Partial<Plan> = {}): Plan => ({
  selected_competition_ids: ['c-algo'],
  tasks: [{
    id: 't1', competition_instance_id: 'c-algo', title: '专题训练', estimated_hours: 12,
    acceptance_criteria: '完成 40 道题', start_date: '2026-11-02', due_date: null,
  }],
  weekly_load: [
    { week_start: '2026-11-02', estimated_hours: 9, budget_hours: 8 },
    { week_start: '2026-11-09', estimated_hours: null, budget_hours: null },
  ],
  conflicts: ['2026-11-02 起一周计划 9 小时，超过每周预算 8 小时'],
  assumptions: ['按任务跨越的周数平均分配'],
  feasibility: 'infeasible',
  ...over,
});

describe('DynamicForm', () => {
  it('按后端提供的字段渲染，不写死字段名', () => {
    const w = mount(DynamicForm, { props: { form: loginForm(), busy: false } });
    expect(w.findAll('input').map((i) => i.attributes('name'))).toEqual(['user_x', 'pwd_y', 'cap_z']);
    expect(w.find('input[name="pwd_y"]').attributes('type')).toBe('password');
    expect(w.find('img').attributes('src')).toBe('data:image/png;base64,AAAA');
    expect(w.text()).toContain('算式结果');
  });

  it('提交时带上所有字段值', async () => {
    const w = mount(DynamicForm, { props: { form: loginForm(), busy: false } });
    await w.find('input[name="user_x"]').setValue('alice');
    await w.find('input[name="pwd_y"]').setValue('secret');
    await w.find('input[name="cap_z"]').setValue('56');
    await w.find('form').trigger('submit');
    expect(w.emitted('submit')![0]).toEqual([{ user_x: 'alice', pwd_y: 'secret', cap_z: '56' }]);
  });

  it('失败后显示 CAS 错误，保留用户名并清空密码和验证码', async () => {
    const w = mount(DynamicForm, { props: { form: loginForm(), busy: false } });
    await w.find('input[name="user_x"]').setValue('alice');
    await w.find('input[name="pwd_y"]').setValue('secret');
    await w.find('input[name="cap_z"]').setValue('1');
    await w.setProps({ form: loginForm({ error: '验证码错误', attempts_left: 2 }) });
    expect(w.find('[role="alert"]').text()).toContain('验证码错误');
    expect(w.text()).toContain('剩余尝试次数：2');
    expect((w.find('input[name="user_x"]').element as HTMLInputElement).value).toBe('alice');
    expect((w.find('input[name="pwd_y"]').element as HTMLInputElement).value).toBe('');
    expect((w.find('input[name="cap_z"]').element as HTMLInputElement).value).toBe('');
  });
});

describe('StageBar', () => {
  it('按 R0 → R1 → R2 → R4 显示阶段，同时显示 status 和 message', () => {
    const w = mount(StageBar, { props: { stage: 'R2', status: 'awaiting_review', message: '请核对精查结果' } });
    expect(w.findAll('li').map((li) => li.text())).toEqual(['R0 画像', 'R1 粗筛', 'R2 精查', 'R4 路线']);
    expect(w.find('li[aria-current="step"]').text()).toBe('R2 精查');
    expect(w.find('[data-test="status"]').text()).toBe('待你确认');
    expect(w.find('[data-test="message"]').text()).toBe('请核对精查结果');
  });
});

describe('CandidateList', () => {
  it('按决定分组，展示报名状态、截止时间、资格和理由', () => {
    const w = mount(CandidateList, { props: { cards: cards(), busy: false } });
    expect(w.findAll('.group h4').map((h) => h.text())).toEqual(['已保留（2）', '待定（2）', '已排除（2）']);
    const algo = w.find('[data-id="c-algo"]');
    expect(algo.text()).toContain('正在报名');
    expect(algo.text()).toContain('符合资格');
    expect(algo.text()).toContain('报名截止：');
    expect(algo.text()).toContain('你有算法基础并想提升编程能力');
    expect(w.find('[data-id="c-data"]').text()).toContain('报名截止：待定');
  });

  it('eligibility 为 ineligible 时禁用「保留」，其余可用', () => {
    const w = mount(CandidateList, { props: { cards: cards(), busy: false } });
    const math = w.find('[data-id="c-math"]');
    expect(math.find('[data-decision="keep"]').attributes('disabled')).toBeDefined();
    expect(math.find('[data-decision="defer"]').attributes('disabled')).toBeUndefined();
    expect(w.find('[data-id="c-robot"] [data-decision="keep"]').attributes('disabled')).toBeUndefined();
  });

  it('点击决定按钮发出 setDecision；busy 时全部禁用', async () => {
    const w = mount(CandidateList, { props: { cards: cards(), busy: false } });
    await w.find('[data-id="c-robot"] [data-decision="keep"]').trigger('click');
    expect(w.emitted('setDecision')![0]).toEqual(['c-robot', 'keep']);
    await w.setProps({ busy: true });
    expect(w.findAll('[data-decision]').every((b) => b.attributes('disabled') !== undefined)).toBe(true);
  });

  it('只有 http/https 证据链接渲染为 <a>，其他协议显示为纯文本；模型文本不解析 HTML', () => {
    const list = cards().slice(0, 1);
    const base = list[0].evidence[0];
    list[0].evidence = [
      { ...base, id: 'e-http', url: 'https://example.com/a' },
      { ...base, id: 'e-js', url: 'javascript:alert(1)' },
      { ...base, id: 'e-data', url: 'data:text/html,<script>alert(1)</script>' },
      { ...base, id: 'e-ftp', url: 'ftp://example.com/a' },
      { ...base, id: 'e-bad', url: 'not a url' },
      { ...base, id: 'e-xss', url: 'https://example.com/b', excerpt: '<img src=x onerror=alert(1)>' },
    ];
    list[0].reason = '<b>加粗</b>';
    const w = mount(CandidateList, { props: { cards: list, busy: false } });
    const links = w.findAll('a');
    expect(links.map((a) => a.attributes('href'))).toEqual(['https://example.com/a', 'https://example.com/b']);
    expect(links.every((a) => a.attributes('rel') === 'noopener noreferrer' && a.attributes('target') === '_blank')).toBe(true);
    expect(w.find('[data-evidence-id="e-js"]').text()).toContain('javascript:alert(1)');
    expect(w.find('[data-evidence-id="e-js"] a').exists()).toBe(false);
    expect(w.find('img').exists()).toBe(false);
    expect(w.find('b').exists()).toBe(false);
    expect(w.text()).toContain('<b>加粗</b>');
  });
});

describe('ScorecardList', () => {
  it('显示 R2 维度中文标签、依据类型和不确定项', () => {
    const w = mount(ScorecardList, { props: { cards: analysed().filter((c) => c.dimensions.length).slice(0, 1) } });
    const labels = w.findAll('th').map((th) => th.text());
    expect(labels).toEqual(['能力差距', '目标价值', '投入', '准备风险', '组队需求', '赛程冲突']);
    expect(w.text()).toContain('官方');
    expect(w.text()).toContain('推断');
    expect(w.text()).toContain('不确定：今年题型未知');
    const unknown = mount(ScorecardList, { props: { cards: analysed().filter((c) => c.competition_instance_id === 'c-data') } });
    expect(unknown.text()).toContain('信息不足');
  });
});

describe('RoutePlan', () => {
  const names = { 'c-algo': '程序设计竞赛（示例）' };

  it('任务表与每周负载表：未知值显示「待定」，超预算标红', () => {
    const w = mount(RoutePlan, { props: { plan: plan(), names } });
    const row = w.find('.tasks tbody tr');
    expect(row.text()).toContain('专题训练');
    expect(row.text()).toContain('程序设计竞赛（示例）');
    expect(row.text()).toContain('12 小时');
    expect(row.text()).toContain('2026-11-02');
    expect(row.text()).toContain('待定');
    expect(row.text()).toContain('完成 40 道题');
    const weeks = w.findAll('.weeks tbody tr');
    expect(weeks[0].find('td.over').text()).toBe('9 小时');
    expect(weeks[1].text()).toContain('待定');
    expect(w.text()).toContain('冲突：');
    expect(w.text()).toContain('假设：');
  });

  it('feasible 显示正常提示；infeasible / unknown 显示原因提示', () => {
    const banner = (p: Plan) => mount(RoutePlan, { props: { plan: p, names } }).find('[data-feasibility]');
    const ok = banner(plan({ feasibility: 'feasible', conflicts: [] }));
    expect(ok.classes()).toContain('ok');
    const bad = banner(plan({ feasibility: 'infeasible' }));
    expect(bad.classes()).toContain('error');
    expect(bad.text()).toContain('不可行');
    const unknown = banner(plan({ feasibility: 'unknown', conflicts: [] }));
    expect(unknown.classes()).toContain('warn');
    expect(unknown.text()).toContain('无法确认');
  });
});

describe('ProfilePanel', () => {
  const profile = structuredClone(DRAFT_PROFILE);
  const edit = async (w: ReturnType<typeof mount>) =>
    w.findAll('button').find((b) => b.text() === '编辑画像')!.trigger('click');

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('只提交有改动的字段，数组整体替换，且不带出响应式 Proxy', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: false } });
    await edit(w);
    await w.find('input[name="weekly_hours"]').setValue('15');
    await w.find('input[name="goals"]').setValue('保研，兴趣、 奖金');
    await w.find('form').trigger('submit');
    const changes = w.emitted('save')![0][0] as Record<string, unknown>;
    expect(changes).toEqual({ weekly_hours: 15, goals: ['保研', '兴趣', '奖金'] });
    expect(() => structuredClone(changes)).not.toThrow();
  });

  it('没有改动时不发出保存', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: false } });
    await edit(w);
    await w.find('form').trigger('submit');
    expect(w.emitted('save')).toBeUndefined();
  });

  it('清空每周时长提交 null；0 或负数被拒绝', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: false } });
    await edit(w);
    await w.find('input[name="weekly_hours"]').setValue('0');
    await w.find('form').trigger('submit');
    expect(w.emitted('save')).toBeUndefined();
    expect(w.find('[role="alert"]').text()).toContain('大于 0');
    await w.find('input[name="weekly_hours"]').setValue('');
    await w.find('form').trigger('submit');
    expect((w.emitted('save')![0][0] as Record<string, unknown>).weekly_hours).toBeNull();
  });

  it('补充说明限 2000 字并提示勿填写账号密码；空白归一化为 null', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: false } });
    await edit(w);
    expect(w.text()).toContain('勿填写账号密码');
    await w.find('textarea[name="additional_context"]').setValue('x'.repeat(2001));
    await w.find('form').trigger('submit');
    expect(w.emitted('save')).toBeUndefined();
    expect(w.text()).toContain('不能超过 2000 字');
    await w.find('textarea[name="additional_context"]').setValue('我有 ACM 集训经历');
    await w.find('form').trigger('submit');
    expect(w.emitted('save')![0][0]).toEqual({ additional_context: '我有 ACM 集训经历' });
  });

  it('校验不可用日期格式', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: false } });
    await edit(w);
    await w.find('input[name="unavailable_dates"]').setValue('2026/12/01');
    await w.find('form').trigger('submit');
    expect(w.emitted('save')).toBeUndefined();
    await w.find('input[name="unavailable_dates"]').setValue('2026-12-01、2026-12-02');
    await w.find('form').trigger('submit');
    expect(w.emitted('save')![0][0]).toEqual({ unavailable_dates: ['2026-12-01', '2026-12-02'] });
  });

  it('已有结果时保存前确认；取消则不保存、表单保持打开', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const w = mount(ProfilePanel, { props: { profile, busy: false, hasResults: true } });
    await edit(w);
    await w.find('input[name="grade"]').setValue('大三');
    await w.find('form').trigger('submit');
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('清空'));
    expect(w.emitted('save')).toBeUndefined();
    expect(w.find('form').exists()).toBe(true);
    confirmSpy.mockReturnValue(true);
    await w.find('form').trigger('submit');
    expect(w.emitted('save')![0][0]).toEqual({ grade: '大三' });
  });
});

describe('LlmSettingsDialog', () => {
  const view = (configured: boolean) => ({
    configured,
    model: 'deepseek/deepseek-chat',
    available_models: ['deepseek/deepseek-chat', 'deepseek/deepseek-reasoner'],
  });

  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    localStorage.clear();
  });

  it('key 只发给后端：保存后清空输入，不写 localStorage，页面不回显', async () => {
    api.getLlmSettings.mockResolvedValue(view(false));
    api.patchLlmSettings.mockResolvedValue({ ...view(true), model: 'deepseek/deepseek-reasoner' });
    const w = mount(LlmSettingsDialog);
    await flushPromises();
    expect(w.text()).toContain('尚未配置');
    await w.find('select[name="model"]').setValue('deepseek/deepseek-reasoner');
    await w.find('input[name="api_key"]').setValue('  sk-secret-1  ');
    expect(w.find('input[name="api_key"]').attributes('type')).toBe('password');
    await w.find('form').trigger('submit');
    await flushPromises();
    expect(api.patchLlmSettings).toHaveBeenCalledWith({ api_key: 'sk-secret-1', model: 'deepseek/deepseek-reasoner' });
    expect((w.find('input[name="api_key"]').element as HTMLInputElement).value).toBe('');
    expect(w.html()).not.toContain('sk-secret-1');
    expect(JSON.stringify(localStorage)).not.toContain('sk-secret-1');
    expect(w.text()).toContain('已配置');
  });

  it('已配置时留空 key 只改模型；什么都没改不发请求', async () => {
    api.getLlmSettings.mockResolvedValue(view(true));
    api.patchLlmSettings.mockResolvedValue({ ...view(true), model: 'deepseek/deepseek-reasoner' });
    const w = mount(LlmSettingsDialog);
    await flushPromises();
    await w.find('form').trigger('submit');
    await flushPromises();
    expect(api.patchLlmSettings).not.toHaveBeenCalled();
    await w.find('select[name="model"]').setValue('deepseek/deepseek-reasoner');
    await w.find('form').trigger('submit');
    await flushPromises();
    expect(api.patchLlmSettings).toHaveBeenCalledWith({ model: 'deepseek/deepseek-reasoner' });
  });
});

describe('AdvisorView', () => {
  const mountView = async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/advisor/:id?', component: AdvisorView, props: true }],
    });
    const w = mount(AdvisorView, { props: { id: 's1' }, global: { plugins: [router] } });
    await flushPromises();
    return w;
  };
  const confirmButton = (w: Awaited<ReturnType<typeof mountView>>) => w.find('[data-action="confirm"]');
  const generateButton = (w: Awaited<ReturnType<typeof mountView>>) => w.find('[data-action="generate"]');

  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('模型未配置时在错误提示里给出「去配置模型」入口', async () => {
    llmDialogOpen.value = false;
    api.getSession.mockResolvedValue(snap({ status: 'collecting', needs_confirmation: false, cards: [] }));
    api.chat.mockRejectedValue(new ApiError('LLM_NOT_CONFIGURED', '模型尚未配置或凭据不可用。', 503));
    const w = await mountView();
    await generateButton(w).trigger('click');
    await flushPromises();
    const link = w.findAll('button').find((b) => b.text() === '去配置模型');
    expect(link).toBeDefined();
    await link!.trigger('click');
    expect(llmDialogOpen.value).toBe(true);
  });

  it('双击「确认本阶段」只发出一个请求，期间按钮禁用', async () => {
    api.getSession.mockResolvedValue(snap());
    let resolve!: (s: SessionSnapshot) => void;
    api.confirm.mockReturnValue(new Promise<SessionSnapshot>((r) => { resolve = r; }));
    const w = await mountView();
    const button = confirmButton(w).element as HTMLButtonElement;
    button.click();
    button.click();
    await flushPromises();
    expect(api.confirm).toHaveBeenCalledTimes(1);
    expect(api.confirm).toHaveBeenCalledWith('s1', 3, 'R1');
    expect(confirmButton(w).attributes('disabled')).toBeDefined();
    resolve(snap({ revision: 4, stage: 'R2', status: 'collecting', needs_confirmation: false }));
    await flushPromises();
    expect(api.confirm).toHaveBeenCalledTimes(1);
  });

  it('confirm 后只显示「生成本阶段结果」，不会自动 generate；点击后发送 generate 且 content 为 null', async () => {
    api.getSession.mockResolvedValue(snap());
    api.confirm.mockResolvedValue(snap({ revision: 4, stage: 'R2', status: 'collecting', needs_confirmation: false }));
    const w = await mountView();
    await confirmButton(w).trigger('click');
    await flushPromises();
    expect(api.chat).not.toHaveBeenCalled();
    expect(confirmButton(w).exists()).toBe(false);
    expect(generateButton(w).exists()).toBe(true);

    api.chat.mockResolvedValue(snap({ revision: 5, stage: 'R2', cards: analysed() }));
    await generateButton(w).trigger('click');
    await flushPromises();
    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(api.chat).toHaveBeenCalledWith('s1', { expected_revision: 4, action: 'generate', content: null });
    expect(generateButton(w).exists()).toBe(false);
    expect(confirmButton(w).exists()).toBe(true);
  });

  it('R0 阶段没有生成按钮，只能聊天', async () => {
    api.getSession.mockResolvedValue(snap({ stage: 'R0', status: 'collecting', needs_confirmation: false, cards: [] }));
    const w = await mountView();
    expect(generateButton(w).exists()).toBe(false);
    expect(confirmButton(w).exists()).toBe(false);
  });

  it('发送消息使用当前 revision，成功后清空输入', async () => {
    api.getSession.mockResolvedValue(snap({ stage: 'R0', status: 'collecting', needs_confirmation: false, cards: [] }));
    api.chat.mockResolvedValue(snap({
      revision: 4, stage: 'R0',
      messages: [
        { id: 'm1', role: 'user', content: '我是大二', created_at: '2026-10-29T10:00:00+08:00' },
        { id: 'm2', role: 'assistant', content: '收到', created_at: '2026-10-29T10:00:01+08:00' },
      ],
    }));
    const w = await mountView();
    await w.find('textarea').setValue('我是大二');
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click');
    await flushPromises();
    expect(api.chat).toHaveBeenCalledWith('s1', { expected_revision: 3, action: 'message', content: '我是大二' });
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('');
    expect(w.text()).toContain('收到');
  });

  it('比当前更旧的回放快照不会覆盖新状态', async () => {
    api.getSession.mockResolvedValue(snap({ revision: 5, message: '最新消息' }));
    api.chat.mockResolvedValue(snap({ revision: 3, message: '过期回放' }));
    const w = await mountView();
    await w.find('textarea').setValue('你好');
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click');
    await flushPromises();
    expect(w.find('[data-test="message"]').text()).toBe('最新消息');
  });

  it('REVISION_CONFLICT：GET 最新快照并提示，不自动重发', async () => {
    api.getSession.mockResolvedValueOnce(snap());
    api.confirm.mockRejectedValue(new ApiError('REVISION_CONFLICT', '会话已更新，请刷新后重试。', 409, false, { current_revision: 6 }));
    const w = await mountView();
    api.getSession.mockResolvedValueOnce(snap({ revision: 6, message: '另一个标签页的结果' }));
    await confirmButton(w).trigger('click');
    await flushPromises();
    expect(w.find('[role="alert"]').text()).toContain('会话已更新，请检查后重试');
    expect(w.find('[data-test="message"]').text()).toBe('另一个标签页的结果');
    expect(api.confirm).toHaveBeenCalledTimes(1);
    expect(api.getSession).toHaveBeenCalledTimes(2);
  });

  it('chat 超时：快照的 last_request_id 等于自己的 ID 时直接采用，且不重发', async () => {
    api.getSession.mockResolvedValueOnce(snap());
    api.chat.mockRejectedValue(new ApiError('TIMEOUT', '等待后端响应超时', 0, false, null, 'req-mine'));
    const w = await mountView();
    api.getSession.mockResolvedValueOnce(snap({ revision: 4, last_request_id: 'req-mine', message: '已在后端完成' }));
    await w.find('textarea').setValue('你好');
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click');
    await flushPromises();
    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(w.find('[data-test="message"]').text()).toBe('已在后端完成');
    expect(w.find('[role="alert"]').exists()).toBe(false);
  });

  it.each([
    ['NETWORK_ERROR', 0],
    ['UPSTREAM_TIMEOUT', 504],
  ])('chat 遇到 %s：last_request_id 不是自己的 ID 则提示失败，保留输入', async (code, status) => {
    api.getSession.mockResolvedValueOnce(snap());
    api.chat.mockRejectedValue(new ApiError(code, '请求没有完成', status, true, null, 'req-mine'));
    const w = await mountView();
    api.getSession.mockResolvedValueOnce(snap({ revision: 3, last_request_id: 'someone-else' }));
    await w.find('textarea').setValue('你好');
    await w.findAll('button').find((b) => b.text() === '发送')!.trigger('click');
    await flushPromises();
    expect(api.chat).toHaveBeenCalledTimes(1);
    expect(w.find('[role="alert"]').text()).toContain('本次请求未生效');
    expect((w.find('textarea').element as HTMLTextAreaElement).value).toBe('你好');
  });

  it('加载时 processing 为 true：每 3 秒轮询 GET，直到 processing 为 false', async () => {
    vi.useFakeTimers();
    api.getSession
      .mockResolvedValueOnce(snap({ processing: true }))
      .mockResolvedValueOnce(snap({ processing: true }))
      .mockResolvedValueOnce(snap({ revision: 4, processing: false, message: '处理完成' }));
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/advisor/:id?', component: AdvisorView, props: true }] });
    const w = mount(AdvisorView, { props: { id: 's1' }, global: { plugins: [router] } });
    await vi.advanceTimersByTimeAsync(0);
    expect(api.getSession).toHaveBeenCalledTimes(1);
    expect(confirmButton(w).attributes('disabled')).toBeDefined();

    await vi.advanceTimersByTimeAsync(2999);
    expect(api.getSession).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(api.getSession).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.getSession).toHaveBeenCalledTimes(3);
    expect(w.find('[data-test="message"]').text()).toBe('处理完成');
    expect(confirmButton(w).attributes('disabled')).toBeUndefined();

    await vi.advanceTimersByTimeAsync(9000);
    expect(api.getSession).toHaveBeenCalledTimes(3);
  });

  it('REQUEST_IN_PROGRESS：GET 后发现 processing，则开始轮询', async () => {
    vi.useFakeTimers();
    api.getSession.mockResolvedValueOnce(snap());
    api.confirm.mockRejectedValue(new ApiError('REQUEST_IN_PROGRESS', '会话正在处理', 409));
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/advisor/:id?', component: AdvisorView, props: true }] });
    const w = mount(AdvisorView, { props: { id: 's1' }, global: { plugins: [router] } });
    await vi.advanceTimersByTimeAsync(0);
    api.getSession.mockResolvedValueOnce(snap({ processing: true }));
    api.getSession.mockResolvedValueOnce(snap({ revision: 4, processing: false }));
    await confirmButton(w).trigger('click');
    await vi.advanceTimersByTimeAsync(0);
    expect(api.getSession).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(api.getSession).toHaveBeenCalledTimes(3);
    expect(api.confirm).toHaveBeenCalledTimes(1);
  });

  it('R2/R4 修改候选前 window.confirm；取消则不发请求，确认后发送', async () => {
    api.getSession.mockResolvedValue(snap({ stage: 'R2', cards: analysed() }));
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const w = await mountView();
    expect(w.find('.candidate').exists()).toBe(false);
    await w.findAll('.tabs button').find((b) => b.text().startsWith('候选'))!.trigger('click');
    await w.find('[data-id="c-data"] [data-decision="exclude"]').trigger('click');
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('回到 R1'));
    expect(api.patchCandidate).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    api.patchCandidate.mockResolvedValue(snap({ revision: 4, stage: 'R1' }));
    await w.find('[data-id="c-data"] [data-decision="exclude"]').trigger('click');
    await flushPromises();
    expect(api.patchCandidate).toHaveBeenCalledWith('s1', 'c-data', 3, 'exclude');
  });

  it('R1 修改候选不弹确认', async () => {
    api.getSession.mockResolvedValue(snap());
    const confirmSpy = vi.spyOn(window, 'confirm');
    api.patchCandidate.mockResolvedValue(snap({ revision: 4 }));
    const w = await mountView();
    await w.find('[data-id="c-robot"] [data-decision="keep"]').trigger('click');
    await flushPromises();
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(api.patchCandidate).toHaveBeenCalledWith('s1', 'c-robot', 3, 'keep');
  });

  it('R4 方案不可行时显示原因，且不能确认', async () => {
    api.getSession.mockResolvedValue(snap({ stage: 'R4', cards: analysed(), plan: plan() }));
    const w = await mountView();
    expect(w.find('[data-feasibility="infeasible"]').exists()).toBe(true);
    expect(confirmButton(w).attributes('disabled')).toBeDefined();
  });

  it('不显示任何日历入口', async () => {
    api.getSession.mockResolvedValue(snap({ stage: 'R4', status: 'completed', needs_confirmation: false, cards: analysed(), plan: plan({ feasibility: 'feasible', conflicts: [] }) }));
    const w = await mountView();
    expect(w.html()).not.toMatch(/日历|calendar|\.ics/i);
  });
});
