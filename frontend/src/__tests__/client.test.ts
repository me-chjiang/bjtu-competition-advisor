import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, REQUEST_TIMEOUT_MS, realAgentApi as api } from '../api/client';

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });

const fetchMock = vi.fn<typeof fetch>();
const chatParams = { expected_revision: 3, action: 'message' as const, content: '你好' };

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('错误包解析', () => {
  it('解析统一错误包的 code / message / retryable / details / request_id', async () => {
    fetchMock.mockResolvedValue(json(409, {
      error: { code: 'REVISION_CONFLICT', message: '会话已更新，请刷新后重试。', retryable: false, details: { current_revision: 4 } },
      request_id: 'req-9',
    }));
    const err = await api.getSession('s1').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      code: 'REVISION_CONFLICT',
      message: '会话已更新，请刷新后重试。',
      status: 409,
      retryable: false,
      details: { current_revision: 4 },
      requestId: 'req-9',
    });
  });

  it('request_id 为 null 时，chat 回退为自己生成的 ID', async () => {
    fetchMock.mockResolvedValue(json(504, {
      error: { code: 'UPSTREAM_TIMEOUT', message: '模型超时', retryable: true, details: null },
      request_id: null,
    }));
    const err = await api.chat('s1', chatParams).catch((e) => e);
    const sent = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(err).toMatchObject({ code: 'UPSTREAM_TIMEOUT', status: 504, retryable: true, requestId: sent.request_id });
  });

  it('429 的提示带上 Retry-After', async () => {
    fetchMock.mockResolvedValue(json(
      429, { error: { code: 'RATE_LIMITED', message: '请求过于频繁', retryable: true } }, { 'Retry-After': '12' },
    ));
    await expect(api.getSession('s1')).rejects.toMatchObject({ code: 'RATE_LIMITED', message: expect.stringContaining('12') });
  });

  it('非 JSON 的错误响应（如 CORS 预检的纯文本 400）回退为通用信息', async () => {
    fetchMock.mockResolvedValue(new Response('Disallowed CORS origin', { status: 400 }));
    await expect(api.getSession('s1')).rejects.toMatchObject({
      code: 'HTTP_ERROR', status: 400, message: '请求失败（HTTP 400）', retryable: false, details: null,
    });
  });

  it('JSON 但不是错误包时同样回退', async () => {
    fetchMock.mockResolvedValue(json(500, { detail: 'oops' }));
    await expect(api.getSession('s1')).rejects.toMatchObject({ code: 'HTTP_ERROR', status: 500 });
  });

  it('网络失败抛 NETWORK_ERROR', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(api.getSession('s1')).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 });
  });

  it('超过 150 秒中止请求并抛 TIMEOUT', async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_url, init) => new Promise((_resolve, reject) => {
      init!.signal!.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    const pending = api.chat('s1', chatParams).catch((e) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS - 1);
    expect(fetchMock.mock.calls[0][1]!.signal!.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    const sent = JSON.parse(fetchMock.mock.calls[0][1]!.body as string);
    expect(await pending).toMatchObject({ code: 'TIMEOUT', requestId: sent.request_id });
    expect(REQUEST_TIMEOUT_MS).toBe(150_000);
  });
});

describe('请求格式', () => {
  it('路径基址为 /api；每次 chat 生成新的 request_id', async () => {
    fetchMock.mockImplementation(async () => json(200, { session_id: 's1' }));
    await api.chat('s1', chatParams);
    await api.chat('s1', chatParams);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/sessions/s1/chat', '/api/sessions/s1/chat']);
    const ids = fetchMock.mock.calls.map(([, init]) => JSON.parse(init!.body as string).request_id);
    expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(ids[0]).not.toBe(ids[1]);
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toMatchObject(chatParams);
  });

  it('generate 发送 content: null；其余修改接口带 expected_revision', async () => {
    fetchMock.mockImplementation(async () => json(200, { session_id: 's1' }));
    await api.chat('s1', { expected_revision: 1, action: 'generate', content: null });
    await api.patchProfile('s1', 2, { weekly_hours: 4 });
    await api.patchCandidate('s1', 'c/1', 3, 'keep');
    await api.confirm('s1', 4, 'R1');
    const calls = fetchMock.mock.calls.map(([url, init]) => [init!.method, url, JSON.parse(init!.body as string)]);
    expect(calls[0][2]).toMatchObject({ action: 'generate', content: null });
    expect(calls.slice(1)).toEqual([
      ['PATCH', '/api/sessions/s1/profile', { expected_revision: 2, changes: { weekly_hours: 4 } }],
      ['PATCH', '/api/sessions/s1/candidates/c%2F1', { expected_revision: 3, decision: 'keep' }],
      ['POST', '/api/sessions/s1/confirm', { expected_revision: 4, stage: 'R1' }],
    ]);
  });
});
