// AI 辅助生成的虚构示例数据，仅供 mock 演示，不代表任何真实竞赛的信息
import type {
  CandidateCard, CompetitionDetail, Decision, Dimension, Evidence, Profile, RegistrationStatus,
} from '../types';
import { daysFromToday } from './util';

const EX = 'https://example.com/competitions';
const FETCHED = '2026-10-15T10:00:00+08:00';
const THIS_YEAR_SCOPE = 'applies-to/v1:{"stage":"校内选拔","group":"本科组"}';

export const DRAFT_PROFILE: Profile = {
  grade: '大二',
  major: '计算机科学与技术',
  skills: [
    { name: 'Python', evidence: '课程大作业：爬虫 + 数据分析（示例）' },
    { name: '数据结构与算法', evidence: '课程成绩良好，刷题约 80 道（示例）' },
    { name: '高等数学', evidence: '期末 90 分（示例）' },
  ],
  weekly_hours: 8,
  goals: ['保研', '简历'],
  team_preference: 'either',
  unavailable_dates: [],
  additional_context: null,
  summary: [
    '## 基本情况',
    '- 大二，计算机科学与技术（示例）',
    '- 每周可投入约 8 小时，个人或组队均可',
    '',
    '## 技能与经历',
    '- **Python**：课程大作业，爬虫 + 数据分析',
    '- **数据结构与算法**：课程成绩良好，刷题约 80 道',
    '- **高等数学**：期末 90 分',
    '',
    '## 目标',
    '- 保研加分、丰富简历',
  ].join('\n'),
};

export const EMPTY_PROFILE: Profile = {
  grade: null, major: null, skills: [], weekly_hours: null, goals: [],
  team_preference: null, unavailable_dates: [], additional_context: null, summary: null,
};

function evidence(id: string, name: string): Evidence[] {
  return [
    {
      id: `${id}-e1`,
      url: `${EX}/${id}/notice`,
      excerpt: `${name}本届通知：本科生可报名，报名时间见通知（示例摘录）`,
      fetched_at: FETCHED,
      applicable_year: 2026,
      scope: THIS_YEAR_SCOPE,
    },
    {
      id: `${id}-e2`,
      url: `${EX}/${id}/archive`,
      excerpt: '往届赛题以综合应用为主，需团队协作（示例摘录）',
      fetched_at: FETCHED,
      applicable_year: 2025,
      scope: '往届校内选拔',
    },
  ];
}

interface Spec {
  id: string;
  name: string;
  status: RegistrationStatus;
  deadlineOffset: number | null;
  eligibility: CandidateCard['eligibility'];
  decision: Decision;
  reason: string;
}

const SPECS: Spec[] = [
  { id: 'c-algo', name: '程序设计竞赛（示例）', status: 'open', deadlineOffset: 20, eligibility: 'eligible',
    decision: 'keep', reason: '你有算法基础并想提升编程能力' },
  { id: 'c-model', name: '数学建模竞赛（示例）', status: 'upcoming', deadlineOffset: 45, eligibility: 'eligible',
    decision: 'keep', reason: '数学成绩好，且不排斥组队' },
  { id: 'c-data', name: '数据分析挑战赛（示例）', status: 'unknown', deadlineOffset: null, eligibility: 'unknown',
    decision: 'defer', reason: 'Python 数据分析经验可直接复用，但本届报名资格和时间尚未核实' },
  { id: 'c-robot', name: '智能机器人竞赛（示例）', status: 'open', deadlineOffset: 14, eligibility: 'eligible',
    decision: 'defer', reason: '与编程相关，但需要硬件经验' },
  { id: 'c-design', name: '工业设计大赛（示例）', status: 'open', deadlineOffset: 60, eligibility: 'eligible',
    decision: 'exclude', reason: '领域相关性较弱，供参考' },
  { id: 'c-math', name: '数学竞赛（示例）', status: 'closed', deadlineOffset: -10, eligibility: 'ineligible',
    decision: 'exclude', reason: '本届报名已截止，不能再报名' },
];

const deadlineOf = (offset: number | null) => (offset === null ? null : `${daysFromToday(offset)}T23:59:00+08:00`);

export const CANDIDATES: CandidateCard[] = SPECS.map((s) => ({
  competition_instance_id: s.id,
  name: s.name,
  registration_status: s.status,
  registration_deadline: deadlineOf(s.deadlineOffset),
  eligibility: s.eligibility,
  decision: s.decision,
  reason: s.reason,
  dimensions: [],
  evidence: evidence(s.id, s.name),
}));

export const COMPETITIONS: CompetitionDetail[] = SPECS.map((s) => ({
  competition_instance_id: s.id,
  name: s.name,
  series_id: s.id.replace('c-', 's-'),
  year: 2026,
  group: '本科组',
  stage: '校内选拔',
  eligibility_description: s.eligibility === 'ineligible' ? '仅限已通过资格审核的在籍学生（示例）' : '全日制在籍本科生（示例）',
  registration_status: s.status,
  registration_start: s.status === 'upcoming' ? daysFromToday(30) : s.status === 'unknown' ? null : daysFromToday(-20),
  registration_deadline: deadlineOf(s.deadlineOffset),
  competition_date: s.status === 'unknown' ? null : daysFromToday((s.deadlineOffset ?? 0) + 30),
  evidence: evidence(s.id, s.name),
}));

const dim = (
  name: Dimension['name'], assessment: string, basis: Dimension['basis'], evidenceIds: string[] = [],
  uncertainties: string[] = [],
): Dimension => ({ name, assessment, basis, evidence_ids: evidenceIds, uncertainties });

export const DIMENSIONS: Record<string, Dimension[]> = {
  'c-algo': [
    dim('ability_gap', '需补图论、动态规划', 'inferred', ['c-algo-e2'], ['今年题型未知']),
    dim('goal_value', '与保研、简历目标高度相关', 'explicit', ['c-algo-e1']),
    dim('time_cost', '预计每周 4–6 小时', 'inferred', [], ['按往届强度估算']),
    dim('preparation_risk', '往届题目难度较高', 'inferred', ['c-algo-e2']),
    dim('team_requirement', '3 人一队，需要找队友', 'explicit', ['c-algo-e1']),
    dim('schedule_conflict', '与期末考试不重叠', 'explicit', ['c-algo-e1']),
  ],
  'c-model': [
    dim('ability_gap', '需补论文写作与常用模型', 'inferred', ['c-model-e2']),
    dim('goal_value', '与保研目标相关', 'explicit', ['c-model-e1']),
    dim('time_cost', '赛前集训约 3 周', 'inferred', [], ['集训安排未公布']),
    dim('preparation_risk', '入门资料丰富，风险中等', 'inferred'),
    dim('team_requirement', '必须 3 人组队', 'explicit', ['c-model-e1']),
    dim('schedule_conflict', '比赛时间待通知', 'unknown', [], ['本届赛程尚未公布']),
  ],
  'c-data': [
    dim('ability_gap', 'Python 数据分析可直接复用', 'inferred'),
    dim('goal_value', '与简历目标相关', 'inferred', [], ['本届规模和级别未核实']),
    dim('time_cost', '预计每周 3 小时', 'inferred'),
    dim('preparation_risk', '评审标准未公开', 'unknown', [], ['评审标准未公开']),
    dim('team_requirement', '可个人参赛', 'explicit', ['c-data-e1']),
    dim('schedule_conflict', '今年赛程尚未公布', 'unknown'),
  ],
  'c-robot': [
    dim('ability_gap', '缺少嵌入式和硬件经验', 'inferred'),
    dim('goal_value', '与保研目标有一定相关', 'explicit', ['c-robot-e1']),
    dim('time_cost', '需要长期实验室投入', 'inferred'),
    dim('preparation_risk', '需要实物调试，风险较高', 'inferred'),
    dim('team_requirement', '5 人团队', 'explicit', ['c-robot-e1']),
    dim('schedule_conflict', '决赛时间未公布', 'unknown'),
  ],
  'c-design': [
    dim('ability_gap', '缺少设计作品集', 'inferred'),
    dim('goal_value', '与目标关联较弱', 'inferred'),
    dim('time_cost', '作品制作约 3 周', 'inferred'),
    dim('preparation_risk', '评审偏主观', 'unknown'),
    dim('team_requirement', '可个人参赛', 'explicit', ['c-design-e1']),
    dim('schedule_conflict', '截止日期较晚，冲突较小', 'explicit', ['c-design-e1']),
  ],
};

export interface TaskSpec {
  title: string;
  hours: number | null;
  acceptance: string;
  startOffset: number | null;
  dueOffset: number | null;
}

// 偏移量以「今天」为基准，保证 mock 方案不会因为时间流逝变成过期任务；工时留有余量，使默认组合在任何星期几都在 8 小时预算内
export const TASK_SPECS: Record<string, TaskSpec[]> = {
  'c-algo': [
    { title: '图论与动态规划专题训练', hours: 12, acceptance: '完成 40 道专题题，独立 AC 率不低于 60%', startOffset: 1, dueOffset: 28 },
    { title: '组队并完成 3 场模拟赛', hours: 4, acceptance: '模拟赛排名进入前 50%', startOffset: 29, dueOffset: 40 },
  ],
  'c-model': [
    { title: '学习常用模型并精读 3 篇优秀论文', hours: 4, acceptance: '能独立写出模型假设与求解章节', startOffset: 1, dueOffset: 21 },
    { title: '组队完成 1 次 72 小时模拟', hours: 6, acceptance: '提交完整论文并互评', startOffset: 22, dueOffset: 30 },
  ],
  'c-data': [
    { title: '复习 pandas 与可视化，完成 1 个完整分析报告', hours: null, acceptance: '报告包含数据清洗、建模和结论', startOffset: null, dueOffset: null },
  ],
  'c-robot': [
    { title: '学习嵌入式基础并加入实验室', hours: 60, acceptance: '完成 1 个小车控制实验', startOffset: 1, dueOffset: 60 },
  ],
  'c-design': [
    { title: '完成 1 件设计作品', hours: 12, acceptance: '作品说明书与效果图齐全', startOffset: 3, dueOffset: 35 },
  ],
};
