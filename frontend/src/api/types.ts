// 与 docs/api-contract.md 保持同步

export interface ApiErrorBody {
  code: string;
  message: string;
}

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

export const STAGES = ['profile', 'screen', 'review', 'route', 'done'] as const;
export type Stage = (typeof STAGES)[number];

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export type SkillLevel = 'basic' | 'proficient' | 'expert';

export interface Skill {
  name: string;
  level: SkillLevel;
  evidence: string;
}

export interface Profile {
  grade: string | null;
  major: string | null;
  discipline: string | null;
  skills: Skill[];
  weekly_hours: number | null;
  goals: string[];
  team_preference: 'individual' | 'team' | 'either' | null;
  domains: string[];
  notes: string | null;
  version: number;
  confirmed: boolean;
}

export type ProfilePatch = Partial<Omit<Profile, 'version' | 'confirmed'>>;

export type Registration = 'open' | 'not_open' | 'closed' | 'unknown';

export interface CandidateCard {
  kind: 'candidate';
  id: string;
  competition_id: string;
  name: string;
  domain: string;
  reason: string;
  level: string | null;
  category: 'A' | 'B' | 'C' | null;
  registration: Registration;
  status: 'kept' | 'excluded' | 'hidden';
  exclusion: { type: 'hard' | 'user'; reason: string; evidence_ids: string[] } | null;
  stale: boolean;
}

export type Tier = 'high' | 'medium' | 'low' | 'unknown';
export type Basis = 'official' | 'inferred' | 'insufficient';
export type Confidence = 'high' | 'medium' | 'low';

export interface Dimension {
  key: 'gap' | 'value' | 'time_cost' | 'difficulty' | 'schedule' | 'team';
  label: string;
  tier: Tier;
  summary: string;
  basis: Basis;
  confidence: Confidence;
  evidence_ids: string[];
}

export type RankKey = 'goal' | 'time' | 'risk';

export interface ScorecardCard {
  kind: 'scorecard';
  id: string;
  competition_id: string;
  name: string;
  summary: string;
  dimensions: Dimension[];
  ranks: Record<RankKey, number>;
  stale: boolean;
}

export interface RouteTask {
  title: string;
  hours_per_week: number;
  acceptance: string;
  start: string | null;
  end: string | null;
  date_certainty: 'confirmed' | 'estimated' | 'unknown';
  assumptions: string[];
}

export interface RouteCard {
  kind: 'route';
  id: string;
  items: { competition_id: string; name: string; tasks: RouteTask[] }[];
  weekly_hours_total: number;
  weekly_hours_available: number | null;
  conflicts: { description: string; competition_ids: string[] }[];
  pending_checks: string[];
  stale: boolean;
}

export type Card = CandidateCard | ScorecardCard | RouteCard;

export interface Session {
  id: string;
  stage: Stage;
  messages: Message[];
  profile: Profile;
  cards: Card[];
  needs_confirmation: boolean;
}

export interface ChatResponse {
  message: Message;
  stage: Stage;
  profile: Profile;
  cards: Card[];
  needs_confirmation: boolean;
}

export interface Evidence {
  id: string;
  excerpt: string;
  url: string;
  fetched_at: string;
  applies_to_year: string | null;
  applies_to_group: string | null;
  source_type: 'mis' | 'official_site' | 'notice' | 'other';
  session_id: string | null;
}

export interface Competition {
  id: string;
  series: string;
  name: string;
  year: string;
  level: string | null;
  category: 'A' | 'B' | 'C' | null;
  organizer: string | null;
  format: string | null;
  registration: { status: Registration; start: string | null; end: string | null };
  description: string | null;
  evidence: Evidence[];
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
  createSession(): Promise<Session>;
  getSession(id: string): Promise<Session>;
  chat(id: string, content: string): Promise<ChatResponse>;
  patchProfile(id: string, patch: ProfilePatch): Promise<{ profile: Profile; cards: Card[] }>;
  confirm(id: string, stage: Stage, selectedCompetitionIds?: string[]): Promise<ChatResponse>;
  patchCandidate(id: string, candidateId: string, status: 'kept' | 'excluded'): Promise<{ card: Card }>;
  getCompetition(id: string): Promise<Competition>;
}
