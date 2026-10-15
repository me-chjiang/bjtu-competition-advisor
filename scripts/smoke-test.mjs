// AI 辅助生成（Claude Code）。用法：node scripts/smoke-test.mjs（凭证读自 lexmount-config.yaml）
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
import { Lexmount } from 'lexmount';
import { parse } from 'yaml';

const config = parse(readFileSync(new URL('../lexmount-config.yaml', import.meta.url), 'utf8'));
// 显式传参优先于 shell 里的 LEXMOUNT_* 环境变量，保证 YAML 是唯一来源
const client = new Lexmount({
  apiKey: config['api-key'],
  projectId: config['project-id'],
  baseUrl: config['base-url'],
});
let session;
let browser;
try {
  session = await client.sessions.create({ browserMode: 'normal' });
  console.log('session:', session.id);
  browser = await chromium.connectOverCDP(session.connectUrl);
  const context = browser.contexts()[0];
  const page = context.pages()[0] ?? (await context.newPage());
  await page.goto('https://example.com');
  console.log('title:', await page.title());
} finally {
  // Free 套餐只有 3 个并发、按 Browser hours 计费，异常时也必须释放云端会话
  try { await browser?.close(); } finally {
    try { await session?.close(); } finally { client.close(); }
  }
}
