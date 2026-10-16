import { ApiError } from '../client';
import type { CrawlStatus, LoginStep, MisApi } from '../types';
import { delay } from './util';

const LOGGED_IN_KEY = 'mock-mis-logged-in';
const CRAWL_KEY = 'mock-mis-crawl';
const MAX_ATTEMPTS = 3;
const CRAWL_STEPS = ['竞赛项目列表 第 1 页', '竞赛项目列表 第 2 页', '可报名轮次列表 第 1 页'];

interface PendingLogin {
  id: string;
  answer: string;
  attemptsLeft: number;
}

let pending: PendingLogin | null = null;
let crawl: CrawlStatus = loadCrawl();

function loadCrawl(): CrawlStatus {
  const saved = localStorage.getItem(CRAWL_KEY);
  if (saved) return JSON.parse(saved) as CrawlStatus;
  return { state: 'idle', step: null, counts: null, finished_at: null, error: null };
}

function captchaImage(): { image: string; answer: string } {
  const a = 2 + Math.floor(Math.random() * 8);
  const b = 2 + Math.floor(Math.random() * 8);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40">`
    + `<rect width="120" height="40" fill="#eef"/>`
    + `<text x="12" y="28" font-size="22" font-family="monospace">${a}×${b}=</text></svg>`;
  return { image: `data:image/svg+xml;base64,${btoa(svg)}`, answer: String(a * b) };
}

function form(p: PendingLogin, error: string | null): LoginStep {
  const { image, answer } = captchaImage();
  p.answer = answer;
  return {
    state: 'form',
    login_id: p.id,
    fields: [
      { name: 'loginname', label: '用户名（示例 CAS 字段）', kind: 'text' },
      { name: 'password', label: '密码', kind: 'password' },
      { name: 'captcha_1', label: '验证码', kind: 'captcha' },
    ],
    captcha: image,
    error,
    attempts_left: p.attemptsLeft,
  };
}

function requirePending(loginId: string): PendingLogin {
  if (!pending || pending.id !== loginId) throw new ApiError('LOGIN_NOT_FOUND', '登录流程已超时，请重新开始', 404);
  return pending;
}

export const mockMisApi: MisApi = {
  async status() {
    await delay();
    return { has_context: localStorage.getItem(LOGGED_IN_KEY) === '1', crawl };
  },

  async startLogin() {
    await delay(600);
    if (localStorage.getItem(LOGGED_IN_KEY) === '1') return { state: 'already_logged_in' };
    pending = { id: `mock-login-${Date.now()}`, answer: '', attemptsLeft: MAX_ATTEMPTS };
    return form(pending, null);
  },

  async submitLogin(loginId, values) {
    await delay(800);
    const p = requirePending(loginId);
    let error: string | null = null;
    if (values.captcha_1?.trim() !== p.answer) error = '验证码错误';
    else if (!values.loginname?.trim() || !values.password) error = '用户名或密码错误';
    if (!error) {
      pending = null;
      localStorage.setItem(LOGGED_IN_KEY, '1');
      return { state: 'success' };
    }
    p.attemptsLeft -= 1;
    if (p.attemptsLeft <= 0) {
      pending = null;
      return { state: 'failed', error: `${error}；尝试次数已用完，请稍后再试` };
    }
    return form(p, error);
  },

  async refreshCaptcha(loginId) {
    await delay();
    return form(requirePending(loginId), null);
  },

  async cancelLogin(loginId) {
    await delay();
    requirePending(loginId);
    pending = null;
  },

  async startCrawl() {
    await delay();
    if (crawl.state === 'running') throw new ApiError('CRAWL_RUNNING', '采集正在进行', 409);
    if (localStorage.getItem(LOGGED_IN_KEY) !== '1') throw new ApiError('NOT_LOGGED_IN', '尚未登录 MIS', 409);
    crawl = { state: 'running', step: CRAWL_STEPS[0], counts: null, finished_at: null, error: null };
    CRAWL_STEPS.forEach((step, i) => {
      setTimeout(() => {
        crawl = { ...crawl, step };
      }, i * 1000);
    });
    setTimeout(() => {
      crawl = {
        state: 'done',
        step: null,
        counts: { cpitem: 712, signup_rounds: 43 },
        finished_at: new Date().toISOString(),
        error: null,
      };
      localStorage.setItem(CRAWL_KEY, JSON.stringify(crawl));
    }, CRAWL_STEPS.length * 1000);
    return crawl;
  },

  async crawlStatus() {
    await delay(100);
    return crawl;
  },
};
