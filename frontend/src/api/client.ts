import type {
  AgentApi, ChatParams, CompetitionDetail, ErrorResponse, LlmSettings, MisApi, SessionSnapshot,
} from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '/api';
// 后端总预算 120 秒，前端和代理至少等 150 秒（docs/frontend-contract.md 第 5 节）
export const REQUEST_TIMEOUT_MS = 150_000;

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly retryable = false,
    readonly details: Record<string, unknown> | null = null,
    readonly requestId: string | null = null,
  ) {
    super(message);
  }
}

function parseError(res: Response, data: unknown, fallbackRequestId: string | null): ApiError {
  const body = data as Partial<ErrorResponse> | null;
  const err = body?.error;
  if (!err || typeof err.code !== 'string') {
    // CORS 预检等协议层拒绝返回纯文本，不当作业务错误解析
    return new ApiError('HTTP_ERROR', `请求失败（HTTP ${res.status}）`, res.status, false, null, fallbackRequestId);
  }
  let message = err.message || `请求失败（HTTP ${res.status}）`;
  const retryAfter = res.headers.get('Retry-After');
  if (res.status === 429 && retryAfter) message += `（约 ${retryAfter} 秒后再试）`;
  return new ApiError(
    err.code, message, res.status, err.retryable === true, err.details ?? null, body?.request_id ?? fallbackRequestId,
  );
}

async function request<T>(method: string, path: string, body?: unknown, requestId: string | null = null): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(BASE + path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (res.status === 204) return undefined as T;
    const data = await res.json().catch(() => null);
    if (!res.ok) throw parseError(res, data, requestId);
    return data as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if (timedOut) throw new ApiError('TIMEOUT', '等待后端响应超时，请先刷新确认状态', 0, false, null, requestId);
    throw new ApiError('NETWORK_ERROR', '无法连接后端，请确认后端已在 127.0.0.1:8000 启动', 0, false, null, requestId);
  } finally {
    clearTimeout(timer);
  }
}

const seg = encodeURIComponent;

export const realMisApi: MisApi = {
  status: () => request('GET', '/mis/status'),
  startLogin: () => request('POST', '/mis/login'),
  submitLogin: (loginId, values) => request('POST', `/mis/login/${seg(loginId)}/submit`, { values }),
  refreshCaptcha: (loginId) => request('POST', `/mis/login/${seg(loginId)}/captcha`),
  cancelLogin: (loginId) => request('DELETE', `/mis/login/${seg(loginId)}`),
  startCrawl: () => request('POST', '/mis/crawl'),
  crawlStatus: () => request('GET', '/mis/crawl'),
};

export const realAgentApi: AgentApi = {
  createSession: () => request<SessionSnapshot>('POST', '/sessions', {}),
  getSession: (id) => request<SessionSnapshot>('GET', `/sessions/${seg(id)}`),
  chat: (id, params: ChatParams) => {
    const requestId = params.request_id ?? crypto.randomUUID();
    return request<SessionSnapshot>(
      'POST', `/sessions/${seg(id)}/chat`, { ...params, request_id: requestId }, requestId,
    );
  },
  patchProfile: (id, expectedRevision, changes) =>
    request<SessionSnapshot>('PATCH', `/sessions/${seg(id)}/profile`, { expected_revision: expectedRevision, changes }),
  patchCandidate: (id, candidateId, expectedRevision, decision) =>
    request<SessionSnapshot>('PATCH', `/sessions/${seg(id)}/candidates/${seg(candidateId)}`, {
      expected_revision: expectedRevision, decision,
    }),
  confirm: (id, expectedRevision, stage) =>
    request<SessionSnapshot>('POST', `/sessions/${seg(id)}/confirm`, { expected_revision: expectedRevision, stage }),
  getCompetition: (id) => request<CompetitionDetail>('GET', `/competitions/${seg(id)}`),
  getLlmSettings: () => request<LlmSettings>('GET', '/settings/llm'),
  patchLlmSettings: (patch) => request<LlmSettings>('PATCH', '/settings/llm', patch),
};
