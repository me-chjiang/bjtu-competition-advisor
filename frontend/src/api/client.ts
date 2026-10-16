import type { AgentApi, ApiErrorBody, MisApi } from './types';

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接后端，请确认后端已在 127.0.0.1:8000 启动', 0);
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data as Partial<ApiErrorBody> | null;
    throw new ApiError(err?.code ?? 'HTTP_ERROR', err?.message ?? `请求失败（HTTP ${res.status}）`, res.status);
  }
  return data as T;
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
  createSession: () => request('POST', '/sessions', {}),
  getSession: (id) => request('GET', `/sessions/${seg(id)}`),
  chat: (id, content) => request('POST', `/sessions/${seg(id)}/chat`, { content }),
  patchProfile: (id, patch) => request('PATCH', `/sessions/${seg(id)}/profile`, patch),
  confirm: (id, stage, selectedCompetitionIds) =>
    request('POST', `/sessions/${seg(id)}/confirm`, {
      stage,
      ...(selectedCompetitionIds ? { selected_competition_ids: selectedCompetitionIds } : {}),
    }),
  patchCandidate: (id, candidateId, status) =>
    request('PATCH', `/sessions/${seg(id)}/candidates/${seg(candidateId)}`, { status }),
  getCompetition: (id) => request('GET', `/competitions/${seg(id)}`),
};
