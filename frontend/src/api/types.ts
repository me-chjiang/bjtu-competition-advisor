// 字段来自后端 OpenAPI（schema.d.ts，npm run gen:api 生成），行为规则见 docs/frontend-contract.md
import type { components } from './schema';

// ---- MIS ----

export interface FormField {
  name: string;
  label: string;
  kind: 'text' | 'password' | 'captcha';
}

export type LoginStep =
  | { state: 'already_logged_in' }
  | { state: 'success' }
  | { state: 'failed'; error: string }
  | {
      state: 'form';
      login_id: string;
      fields: FormField[];
      captcha: string | null;
      error: string | null;
      attempts_left: number;
    };

export type LoginForm = Extract<LoginStep, { state: 'form' }>;

export interface CrawlStatus {
  state: 'idle' | 'running' | 'done' | 'error';
  step: string | null;
  counts: { cpitem: number; signup_rounds: number } | null;
  finished_at: string | null;
  error: string | null;
}

export interface MisStatus {
  has_context: boolean;
  crawl: CrawlStatus;
}

// ---- Agent ----

type Schemas = components['schemas'];

// 后端的默认值字段在 OpenAPI 里不是 required，但响应总会带上；Required 只处理一层，嵌套字段逐层声明
type Req<T> = Required<T>;
export type Skill = Req<Schemas['Skill']>;
export type Profile = Omit<Req<Schemas['Profile']>, 'skills'> & { skills: Skill[] };
export type ProfileChanges = Schemas['ProfileChanges'];
export type Evidence = Req<Schemas['Evidence']>;
export type Dimension = Req<Schemas['Dimension']>;
export type CandidateCard = Omit<Req<Schemas['CandidateCard']>, 'dimensions' | 'evidence'> & {
  dimensions: Dimension[];
  evidence: Evidence[];
};
export type WeeklyLoad = Req<Schemas['WeeklyLoad']>;
export type PlanTask = Req<Schemas['PlanTask']>;
export type Plan = Omit<Req<Schemas['Plan']>, 'tasks' | 'weekly_load'> & {
  tasks: PlanTask[];
  weekly_load: WeeklyLoad[];
};
export type Message = Schemas['Message'];
export type CompetitionDetail = Omit<Req<Schemas['CompetitionDetail']>, 'evidence'> & { evidence: Evidence[] };
export type ErrorResponse = Schemas['ErrorResponse'];
export type LlmSettings = Schemas['LLMSettingsView'];
export type LlmSettingsPatch = Schemas['LLMSettingsPatch'];
export type SessionSnapshot = Omit<Req<Schemas['SessionSnapshot']>, 'profile' | 'cards' | 'plan'> & {
  profile: Profile;
  cards: CandidateCard[];
  plan: Plan | null;
};

export type Stage = SessionSnapshot['stage'];
export type Status = SessionSnapshot['status'];
export type Decision = CandidateCard['decision'];
export type Eligibility = CandidateCard['eligibility'];
export type RegistrationStatus = CandidateCard['registration_status'];
export type DimensionName = Dimension['name'];
export type Basis = Dimension['basis'];
export type Feasibility = Plan['feasibility'];
export type TeamPreference = NonNullable<Profile['team_preference']>;
export type ChatAction = Schemas['ChatRequest']['action'];

export const STAGES = ['R0', 'R1', 'R2', 'R4'] as const satisfies readonly Stage[];

export interface ChatParams {
  expected_revision: number;
  action: ChatAction;
  content: string | null;
  // 不传则由 client 生成；传入只用于需要自己掌握 ID 的调用方和测试
  request_id?: string;
}

export interface MisApi {
  status(): Promise<MisStatus>;
  startLogin(): Promise<LoginStep>;
  submitLogin(loginId: string, values: Record<string, string>): Promise<LoginStep>;
  refreshCaptcha(loginId: string): Promise<LoginStep>;
  cancelLogin(loginId: string): Promise<void>;
  startCrawl(): Promise<CrawlStatus>;
  crawlStatus(): Promise<CrawlStatus>;
}

export interface AgentApi {
  createSession(): Promise<SessionSnapshot>;
  getSession(id: string): Promise<SessionSnapshot>;
  // 失败时 ApiError.requestId 为本次请求的 ID，调用方据此对照快照的 last_request_id
  chat(id: string, params: ChatParams): Promise<SessionSnapshot>;
  patchProfile(id: string, expectedRevision: number, changes: ProfileChanges): Promise<SessionSnapshot>;
  patchCandidate(id: string, candidateId: string, expectedRevision: number, decision: Decision): Promise<SessionSnapshot>;
  confirm(id: string, expectedRevision: number, stage: Stage): Promise<SessionSnapshot>;
  getCompetition(id: string): Promise<CompetitionDetail>;
  getLlmSettings(): Promise<LlmSettings>;
  // key 只发给本机后端内存，前端不保存
  patchLlmSettings(patch: LlmSettingsPatch): Promise<LlmSettings>;
}
