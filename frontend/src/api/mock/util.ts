export const delay = (ms = 300) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export const clone = <T>(value: T): T => structuredClone(value);

const DAY_MS = 86_400_000;

// 后端按 Asia/Shanghai 的日期判断任务是否已过期，mock 的「今天」也按此计算
export const today = () => new Date().toLocaleDateString('sv', { timeZone: 'Asia/Shanghai' });

// 纯日期（YYYY-MM-DD）统一按 UTC 零点做加减，避免本机时区影响
export const addDays = (date: string, n: number) =>
  new Date(Date.parse(`${date}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);

export const daysFromToday = (n: number) => addDays(today(), n);

// week_start 固定为周一
export function mondayOf(date: string): string {
  const weekday = new Date(`${date}T00:00:00Z`).getUTCDay();
  return addDays(date, -((weekday + 6) % 7));
}
