import type {
  Basis, Decision, DimensionName, Eligibility, Feasibility, RegistrationStatus, Stage, Status, TeamPreference,
} from './api/types';

export const STAGE_LABELS: Record<Stage, string> = {
  R0: 'R0 画像',
  R1: 'R1 粗筛',
  R2: 'R2 精查',
  R4: 'R4 路线',
};

export const STATUS_LABELS: Record<Status, string> = {
  collecting: '收集中',
  awaiting_review: '待你确认',
  completed: '已完成',
};

export const DIMENSION_LABELS: Record<DimensionName, string> = {
  ability_gap: '能力差距',
  goal_value: '目标价值',
  time_cost: '投入',
  preparation_risk: '准备风险',
  team_requirement: '组队需求',
  schedule_conflict: '赛程冲突',
};

export const BASIS_LABELS: Record<Basis, string> = {
  explicit: '官方',
  inferred: '推断',
  unknown: '信息不足',
};

export const DECISION_LABELS: Record<Decision, string> = { keep: '保留', defer: '待定', exclude: '排除' };

export const ELIGIBILITY_LABELS: Record<Eligibility, string> = {
  eligible: '符合资格',
  ineligible: '不符合资格',
  unknown: '资格未知',
};

export const REGISTRATION_LABELS: Record<RegistrationStatus, string> = {
  open: '正在报名',
  upcoming: '尚未开放',
  closed: '已截止',
  unknown: '时间未知',
};

export const FEASIBILITY_LABELS: Record<Feasibility, string> = {
  feasible: '可行',
  infeasible: '不可行',
  unknown: '无法确认',
};

export const TEAM_LABELS: Record<TeamPreference, string> = { solo: '个人', team: '组队', either: '都可以' };

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

// 纯日期（YYYY-MM-DD）原样显示，避免被当作 UTC 零点换算出时间
export const formatTime = (iso: string | null | undefined) =>
  !iso
    ? ''
    : DATE_ONLY.test(iso)
      ? iso
      : new Date(iso).toLocaleString('zh-CN', {
          year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
          timeZone: 'Asia/Shanghai',
        });
