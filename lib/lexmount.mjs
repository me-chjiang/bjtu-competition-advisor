// AI 辅助生成（Claude Code）。Lexmount 云会话与本地隧道的生命周期封装。
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
import { Lexmount } from 'lexmount';
import { parse } from 'yaml';

export function loadConfig() {
  return parse(readFileSync(new URL('../lexmount-config.yaml', import.meta.url), 'utf8'));
}

export async function withClient(fn) {
  const config = loadConfig();
  const client = new Lexmount({
    apiKey: config['api-key'],
    projectId: config['project-id'],
    baseUrl: config['base-url'],
  });
  try {
    return await fn(client);
  } finally {
    client.close();
  }
}

// 隧道必须晚于其上的会话关闭，所以会话要嵌套在 fn 内部创建
export async function withTunnel(client, fn) {
  const tunnel = await client.tunnels.open();
  try {
    return await fn(tunnel);
  } finally {
    await tunnel.close();
  }
}

// Browser hours 计费且并发有限，异常时也必须释放云端会话
export async function withCloudBrowser(client, options, fn) {
  let session;
  let browser;
  try {
    session = await client.sessions.create({
      browserMode: 'normal',
      recording: { persistent: true },
      ...options,
    });
    browser = await chromium.connectOverCDP(session.connectUrl);
    const context = browser.contexts()[0];
    const page = context.pages()[0] ?? (await context.newPage());
    return await fn({ session, browser, page });
  } finally {
    try {
      await browser?.close();
    } finally {
      await session?.close();
    }
  }
}
