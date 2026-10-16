// 虚构示例数据，仅供 mock 演示，不代表任何真实竞赛的信息
import type { CandidateCard, Competition, Profile, RouteTask, ScorecardCard } from '../types';

const EX = 'https://example.com/competitions';
const FETCHED = '2026-10-15T10:00:00+08:00';

export const DRAFT_PROFILE: Omit<Profile, 'version' | 'confirmed'> = {
  grade: '大二',
  major: '计算机科学与技术',
  discipline: '工学',
  skills: [
    { name: 'Python', level: 'proficient', evidence: '课程大作业：爬虫 + 数据分析（示例）' },
    { name: '数据结构与算法', level: 'basic', evidence: '课程成绩良好，刷题约 80 道（示例）' },
    { name: '高等数学', level: 'proficient', evidence: '期末 90 分（示例）' },
  ],
  weekly_hours: 8,
  goals: ['保研', '简历'],
  team_preference: 'either',
  domains: ['算法编程', '数学建模'],
  notes: null,
};

function competition(
  id: string,
  name: string,
  extra: Partial<Competition> & Pick<Competition, 'registration'>,
): Competition {
  return {
    id,
    series: name.replace('（示例）', ''),
    name,
    year: '2026',
    level: '国家级',
    category: 'A',
    organizer: '示例主办单位',
    format: '组队 / 线下',
    description: `${name}的示例说明文字。`,
    evidence: [
      {
        id: `${id}-e1`,
        excerpt: `【MIS】${name}，级别：国家级，报名时间见通知（示例摘录）`,
        url: `${EX}/${id}/mis`,
        fetched_at: FETCHED,
        applies_to_year: '2026',
        applies_to_group: '本科组',
        source_type: 'mis',
        session_id: 'mock-session-001',
      },
      {
        id: `${id}-e2`,
        excerpt: `【官网】往届赛题以综合应用为主，需团队协作（示例摘录）`,
        url: `${EX}/${id}/official`,
        fetched_at: FETCHED,
        applies_to_year: '2025',
        applies_to_group: null,
        source_type: 'official_site',
        session_id: null,
      },
    ],
    ...extra,
  };
}

export const COMPETITIONS: Competition[] = [
  competition('c-algo', '程序设计竞赛（示例）', {
    registration: { status: 'open', start: '2026-10-01', end: '2026-10-30' },
  }),
  competition('c-model', '数学建模竞赛（示例）', {
    format: '3 人组队 / 线上',
    registration: { status: 'not_open', start: '2026-11-10', end: null },
  }),
  competition('c-data', '数据分析挑战赛（示例）', {
    level: '省部级',
    category: 'B',
    format: '个人或组队 / 线上',
    registration: { status: 'unknown', start: null, end: null },
  }),
  competition('c-robot', '智能机器人竞赛（示例）', {
    category: 'B',
    registration: { status: 'open', start: '2026-10-05', end: '2026-11-05' },
  }),
  competition('c-math', '数学竞赛（示例）', {
    category: 'A',
    format: '个人 / 线下',
    registration: { status: 'closed', start: '2026-09-01', end: '2026-09-30' },
  }),
  competition('c-design', '工业设计大赛（示例）', {
    level: '省部级',
    category: 'C',
    registration: { status: 'open', start: '2026-10-10', end: '2026-12-01' },
  }),
];

const base = { kind: 'candidate', status: 'kept', exclusion: null, stale: false } as const;

export const CANDIDATES: CandidateCard[] = [
  { ...base, id: 'cand-algo', competition_id: 'c-algo', name: '程序设计竞赛（示例）', domain: '算法编程',
    reason: '你有算法基础并想提升编程能力', level: '国家级', category: 'A', registration: 'open' },
  { ...base, id: 'cand-data', competition_id: 'c-data', name: '数据分析挑战赛（示例）', domain: '算法编程',
    reason: 'Python 数据分析经验可直接复用', level: '省部级', category: 'B', registration: 'unknown' },
  { ...base, id: 'cand-model', competition_id: 'c-model', name: '数学建模竞赛（示例）', domain: '数学建模',
    reason: '数学成绩好，且偏好组队', level: '国家级', category: 'A', registration: 'not_open' },
  { ...base, id: 'cand-robot', competition_id: 'c-robot', name: '智能机器人竞赛（示例）', domain: '工程实践',
    reason: '与编程相关，但需要硬件经验', level: '国家级', category: 'B', registration: 'open', status: 'hidden' },
  { ...base, id: 'cand-math', competition_id: 'c-math', name: '数学竞赛（示例）', domain: '数学建模',
    reason: '数学基础较好', level: '国家级', category: 'A', registration: 'closed', status: 'excluded',
    exclusion: { type: 'hard', reason: '本年度报名已于 2026-09-30 截止', evidence_ids: ['c-math-e1'] } },
  { ...base, id: 'cand-design', competition_id: 'c-design', name: '工业设计大赛（示例）', domain: '设计创意',
    reason: '领域相关性较弱，供参考', level: '省部级', category: 'C', registration: 'open', status: 'hidden' },
];

type Dim = ScorecardCard['dimensions'][number];
const dim = (key: Dim['key'], label: string, tier: Dim['tier'], summary: string,
  basis: Dim['basis'], confidence: Dim['confidence'], evidence_ids: string[] = []): Dim =>
  ({ key, label, tier, summary, basis, confidence, evidence_ids });

export const SCORECARDS: Record<string, Omit<ScorecardCard, 'kind' | 'stale'>> = {
  'c-algo': {
    id: 'sc-algo', competition_id: 'c-algo', name: '程序设计竞赛（示例）',
    summary: '与目标高度相关，主要差距在图论与动态规划',
    ranks: { goal: 1, time: 3, risk: 3 },
    dimensions: [
      dim('gap', '能力差距', 'medium', '需补图论、动态规划', 'inferred', 'medium', ['c-algo-e2']),
      dim('value', '目标价值', 'high', 'MIS 标注国家级 A 类', 'official', 'high', ['c-algo-e1']),
      dim('time_cost', '时间成本', 'high', '预计每周 6 小时以上', 'inferred', 'medium'),
      dim('difficulty', '准备难度', 'high', '往届题目难度较高', 'inferred', 'low', ['c-algo-e2']),
      dim('schedule', '赛程冲突', 'low', '与期末考试不重叠', 'official', 'medium', ['c-algo-e1']),
      dim('team', '组队需求', 'medium', '3 人一队，需要找队友', 'official', 'high', ['c-algo-e2']),
    ],
  },
  'c-data': {
    id: 'sc-data', competition_id: 'c-data', name: '数据分析挑战赛（示例）',
    summary: '技能匹配度最高，但报名时间未知',
    ranks: { goal: 3, time: 1, risk: 2 },
    dimensions: [
      dim('gap', '能力差距', 'low', 'Python 数据分析可直接复用', 'inferred', 'medium'),
      dim('value', '目标价值', 'medium', '省部级 B 类', 'official', 'high', ['c-data-e1']),
      dim('time_cost', '时间成本', 'low', '预计每周 3 小时', 'inferred', 'medium'),
      dim('difficulty', '准备难度', 'medium', '赛题开放，评审标准未公开', 'insufficient', 'low'),
      dim('schedule', '赛程冲突', 'unknown', '今年赛程尚未公布', 'insufficient', 'low'),
      dim('team', '组队需求', 'low', '可个人参赛', 'official', 'high', ['c-data-e1']),
    ],
  },
  'c-model': {
    id: 'sc-model', competition_id: 'c-model', name: '数学建模竞赛（示例）',
    summary: '数学基础匹配，需要补建模论文写作',
    ranks: { goal: 2, time: 2, risk: 1 },
    dimensions: [
      dim('gap', '能力差距', 'medium', '需补论文写作与常用模型', 'inferred', 'medium', ['c-model-e2']),
      dim('value', '目标价值', 'high', 'MIS 标注国家级 A 类', 'official', 'high', ['c-model-e1']),
      dim('time_cost', '时间成本', 'medium', '赛前集训约 4 周', 'inferred', 'medium'),
      dim('difficulty', '准备难度', 'medium', '入门资料丰富', 'inferred', 'medium'),
      dim('schedule', '赛程冲突', 'low', '比赛在 11 月，不与考试重叠', 'inferred', 'low'),
      dim('team', '组队需求', 'high', '必须 3 人组队', 'official', 'high', ['c-model-e2']),
    ],
  },
  'c-robot': {
    id: 'sc-robot', competition_id: 'c-robot', name: '智能机器人竞赛（示例）',
    summary: '需要硬件经验，差距较大',
    ranks: { goal: 4, time: 4, risk: 4 },
    dimensions: [
      dim('gap', '能力差距', 'high', '缺少嵌入式和硬件经验', 'inferred', 'medium'),
      dim('value', '目标价值', 'medium', '国家级 B 类', 'official', 'high', ['c-robot-e1']),
      dim('time_cost', '时间成本', 'high', '需要长期实验室投入', 'inferred', 'low'),
      dim('difficulty', '准备难度', 'high', '需要实物调试', 'inferred', 'medium'),
      dim('schedule', '赛程冲突', 'unknown', '决赛时间未公布', 'insufficient', 'low'),
      dim('team', '组队需求', 'high', '5 人团队', 'official', 'medium', ['c-robot-e2']),
    ],
  },
  'c-design': {
    id: 'sc-design', competition_id: 'c-design', name: '工业设计大赛（示例）',
    summary: '领域相关性弱，仅作探索',
    ranks: { goal: 5, time: 5, risk: 5 },
    dimensions: [
      dim('gap', '能力差距', 'high', '缺少设计作品集', 'inferred', 'medium'),
      dim('value', '目标价值', 'low', '省部级 C 类', 'official', 'high', ['c-design-e1']),
      dim('time_cost', '时间成本', 'medium', '作品制作约 3 周', 'inferred', 'low'),
      dim('difficulty', '准备难度', 'medium', '评审偏主观', 'insufficient', 'low'),
      dim('schedule', '赛程冲突', 'low', '截止 12 月初', 'official', 'medium', ['c-design-e1']),
      dim('team', '组队需求', 'low', '可个人参赛', 'official', 'medium'),
    ],
  },
};

export const ROUTE_TASKS: Record<string, RouteTask[]> = {
  'c-algo': [
    { title: '图论与动态规划专题训练', hours_per_week: 4, acceptance: '完成 40 道专题题，独立 AC 率 ≥ 60%',
      start: '2026-10-20', end: '2026-11-30', date_certainty: 'estimated', assumptions: ['每周可稳定投入 4 小时'] },
    { title: '组队并完成 3 场模拟赛', hours_per_week: 3, acceptance: '模拟赛排名进入前 50%',
      start: '2026-12-01', end: '2026-12-20', date_certainty: 'estimated', assumptions: ['比赛日期沿用往年，待核实'] },
  ],
  'c-data': [
    { title: '复习 pandas 与可视化，完成 1 个完整分析报告', hours_per_week: 3, acceptance: '报告包含数据清洗、建模和结论',
      start: null, end: null, date_certainty: 'unknown', assumptions: ['今年赛程未公布'] },
  ],
  'c-model': [
    { title: '学习常用模型并精读 3 篇优秀论文', hours_per_week: 3, acceptance: '能独立写出模型假设与求解章节',
      start: '2026-10-20', end: '2026-11-10', date_certainty: 'estimated', assumptions: ['报名开放时间按 MIS 显示'] },
    { title: '组队完成 1 次 72 小时模拟', hours_per_week: 5, acceptance: '提交完整论文并互评',
      start: '2026-11-01', end: '2026-11-10', date_certainty: 'estimated', assumptions: ['已找到 2 名队友'] },
  ],
  'c-robot': [
    { title: '学习嵌入式基础并加入实验室', hours_per_week: 6, acceptance: '完成 1 个小车控制实验',
      start: '2026-10-20', end: '2027-01-15', date_certainty: 'estimated', assumptions: ['实验室接收新成员'] },
  ],
  'c-design': [
    { title: '完成 1 件设计作品', hours_per_week: 4, acceptance: '作品说明书与效果图齐全',
      start: '2026-11-01', end: '2026-12-01', date_certainty: 'confirmed', assumptions: [] },
  ],
};
