import { ApiError } from './api/client';

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  console.error(e);
  return '发生未知错误，请重试';
}
