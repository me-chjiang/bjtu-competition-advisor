import { ApiError } from './api/client';

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    // 500 不展示原始异常，只给请求 ID 方便排查
    if (e.code === 'INTERNAL_ERROR') return `${e.message}${e.requestId ? `（请求 ID：${e.requestId}）` : ''}`;
    return e.message;
  }
  console.error(e);
  return '发生未知错误，请重试';
}
