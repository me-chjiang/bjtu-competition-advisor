import type { Basis, Confidence, Registration, SkillLevel, Stage, Tier } from './api/types';

export const STAGE_LABELS: Record<Stage, string> = {
  profile: 'R0 画像',
  screen: 'R1 粗筛',
  review: 'R2 精查',
  route: 'R4 路线',
  done: '完成',
};

export const CONFIRM_LABELS: Partial<Record<Stage, string>> = {
  profile: '确认画像，开始粗筛',
  screen: '确认候选，开始精查',
  review: '用勾选的竞赛生成路线',
  route: '确认路线，完成推荐',
};

export const TIER_LABELS: Record<Tier, string> = { high: '高', medium: '中', low: '低', unknown: '未知' };

export const BASIS_LABELS: Record<Basis, string> = {
  official: '官方明确',
  inferred: '根据材料推断',
  insufficient: '信息不足',
};

export const CONFIDENCE_LABELS: Record<Confidence, string> = { high: '高', medium: '中', low: '低' };

export const REGISTRATION_LABELS: Record<Registration, string> = {
  open: '正在报名',
  not_open: '尚未开放',
  closed: '已截止',
  unknown: '时间未知',
};

export const SKILL_LEVEL_LABELS: Record<SkillLevel, string> = { basic: '入门', proficient: '熟练', expert: '精通' };

export const TEAM_LABELS = { individual: '个人', team: '组队', either: '都可以' } as const;

export const DISCIPLINES = ['理学', '工学', '文史', '经管', '艺术', '其他'];

export const formatTime = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
      })
    : '';
