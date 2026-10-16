import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import type { CandidateCard, LoginForm, ScorecardCard } from '../api/types';
import { CANDIDATES, DRAFT_PROFILE, SCORECARDS } from '../api/mock/fixtures';
import CandidateList from '../components/CandidateList.vue';
import DynamicForm from '../components/DynamicForm.vue';
import ProfilePanel from '../components/ProfilePanel.vue';
import ScorecardList from '../components/ScorecardList.vue';

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

describe('CandidateList', () => {
  const cards = structuredClone(CANDIDATES) as CandidateCard[];

  it('隐藏和用户排除的候选可以恢复，硬性排除的不能', async () => {
    const w = mount(CandidateList, { props: { cards, busy: false, editable: true } });
    const hidden = w.find('[data-id="cand-robot"]');
    await hidden.findAll('button').find((b) => b.text() === '恢复')!.trigger('click');
    expect(w.emitted('setStatus')![0]).toEqual(['cand-robot', 'kept']);

    const hard = w.find('[data-id="cand-math"]');
    expect(hard.text()).toContain('依据：本年度报名已于 2026-09-30 截止');
    expect(hard.findAll('button').some((b) => b.text() === '恢复')).toBe(false);
  });

  it('保留的候选按领域分组', () => {
    const w = mount(CandidateList, { props: { cards, busy: false, editable: true } });
    expect(w.findAll('.group h4').map((h) => h.text())).toEqual(['算法编程', '数学建模']);
  });

  it('非粗筛阶段只读', () => {
    const w = mount(CandidateList, { props: { cards, busy: false, editable: false } });
    expect(w.findAll('button').some((b) => ['排除', '恢复'].includes(b.text()))).toBe(false);
  });
});

describe('ScorecardList', () => {
  const cards: ScorecardCard[] = ['c-algo', 'c-data', 'c-model'].map((id) => ({
    kind: 'scorecard', stale: false, ...structuredClone(SCORECARDS[id]),
  }));
  const names = (w: ReturnType<typeof mount>) => w.findAll('.card .name').map((n) => n.text());

  it('切换排序依据会改变顺序', async () => {
    const w = mount(ScorecardList, { props: { cards, selectable: true, selected: [] } });
    expect(names(w)[0]).toBe('程序设计竞赛（示例）');
    await w.find('input[value="time"]').setValue();
    expect(names(w)[0]).toBe('数据分析挑战赛（示例）');
    await w.find('input[value="risk"]').setValue();
    expect(names(w)[0]).toBe('数学建模竞赛（示例）');
  });

  it('勾选更新 selected，并显示依据类型', async () => {
    const w = mount(ScorecardList, {
      props: { cards, selectable: true, selected: [], 'onUpdate:selected': (v: string[]) => w.setProps({ selected: v }) },
    });
    await w.find('input[aria-label="选择 数据分析挑战赛（示例）"]').setValue(true);
    expect(w.props('selected')).toEqual(['c-data']);
    expect(w.text()).toContain('信息不足');
    expect(w.text()).toContain('官方明确');
  });
});

describe('ProfilePanel', () => {
  const profile = { ...structuredClone(DRAFT_PROFILE), version: 1, confirmed: true };

  it('编辑后提交数字类型的每周时长和拆分后的列表', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false } });
    await w.findAll('button').find((b) => b.text() === '编辑画像')!.trigger('click');
    await w.find('input[name="weekly_hours"]').setValue('15');
    await w.find('input[name="goals"]').setValue('保研，兴趣、 奖金');
    await w.find('form').trigger('submit');
    const patch = w.emitted('save')![0][0] as Record<string, unknown>;
    expect(patch.weekly_hours).toBe(15);
    expect(patch.goals).toEqual(['保研', '兴趣', '奖金']);
    // 不能带出响应式 Proxy，否则 mock 的 structuredClone 会抛错
    expect(() => structuredClone(patch)).not.toThrow();
  });

  it('清空每周时长时提交 null', async () => {
    const w = mount(ProfilePanel, { props: { profile, busy: false } });
    await w.findAll('button').find((b) => b.text() === '编辑画像')!.trigger('click');
    await w.find('input[name="weekly_hours"]').setValue('');
    await w.find('form').trigger('submit');
    expect((w.emitted('save')![0][0] as Record<string, unknown>).weekly_hours).toBeNull();
  });
});
