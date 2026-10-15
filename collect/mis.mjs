// AI 辅助生成（Claude Code）。
// 用法：本机连上学校 VPN 后 `node collect/mis.mjs --pages 1 --perpage 20`（凭证读自 lexmount-config.yaml）
// 云浏览器经本地隧道访问 MIS；需要登录时在本机打开云浏览器窗口，由用户手动登录。
import { execFile } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { withClient, withCloudBrowser, withTunnel } from '../lib/lexmount.mjs';

const LIST_URL = 'https://aa.bjtu.edu.cn/innovation/cpitem/';
const MIS_URL = 'https://mis.bjtu.edu.cn/';
const STATE_DIR = new URL('../.state/', import.meta.url);
const STATE_FILE = new URL('mis-context.json', STATE_DIR);
const DATA_DIR = new URL('../data/', import.meta.url);
const LOGIN_TIMEOUT_MS = 5 * 60_000;
const PAGE_DELAY_MS = 2_000;
const DROP_COLUMNS = new Set(['负责人', '操作']);
const OPENER = { darwin: 'open', win32: 'explorer' }[process.platform] ?? 'xdg-open';

const { values } = parseArgs({
  options: {
    pages: { type: 'string', default: '1' },
    perpage: { type: 'string', default: '20' },
  },
});
const maxPages = Number(values.pages);
const perPage = Number(values.perpage);
const listUrl = (n) => `${LIST_URL}?page=${n}&perpage=${perPage}`;

async function loadContextId(client) {
  try {
    return JSON.parse(await readFile(STATE_FILE, 'utf8')).contextId;
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
  const context = await client.contexts.create({ description: 'BJTU MIS login' });
  await mkdir(STATE_DIR, { recursive: true });
  await writeFile(STATE_FILE, JSON.stringify({ contextId: context.id }));
  return context.id;
}

// 未登录时 aa.bjtu.edu.cn 会跳到它自己的本地登录页，那套账号体系不是 MIS，不能在那里登录
const needsLogin = (page) => page.url().includes('/client/login');

async function ensureLoggedIn(page, session) {
  await page.goto(listUrl(1), { waitUntil: 'domcontentloaded' });
  if (!needsLogin(page)) return;

  await page.goto(MIS_URL, { waitUntil: 'domcontentloaded' });
  console.log('需要登录：已在本机浏览器打开云浏览器窗口，请在 5 分钟内手动登录 MIS 统一身份认证');
  // inspectUrl 可接管会话，只交给本机浏览器打开，不打印、不落盘
  execFile(OPENER, [session.inspectUrl], (err) => {
    if (err) console.error(`无法用 ${OPENER} 打开本机浏览器，需在有图形界面的机器上运行（替代方案见 issue.md #1）`);
  });
  await page.waitForURL(/mis\.bjtu\.edu\.cn\/home/, { timeout: LOGIN_TIMEOUT_MS });

  // 点 MIS 首页的「教务系统」才会在新标签页完成 aa.bjtu.edu.cn 的 SSO
  const [aa] = await Promise.all([
    page.context().waitForEvent('page'),
    page.getByRole('link', { name: '教务系统' }).first().click(),
  ]);
  await aa.waitForLoadState('domcontentloaded');
  await aa.close();

  await page.goto(listUrl(1), { waitUntil: 'domcontentloaded' });
  if (needsLogin(page)) throw new Error('SSO 后仍未进入教务系统');
}

function readTable() {
  const tables = [...document.querySelectorAll('table')];
  const table = tables.sort((a, b) => b.rows.length - a.rows.length)[0];
  if (!table) return { headers: [], rows: [] };
  const headers = [...table.querySelectorAll('th')].map((th) => th.innerText.trim());
  const rows = [...table.querySelectorAll('tr')]
    .filter((tr) => tr.querySelector('td'))
    .map((tr) => [...tr.querySelectorAll('td')].map((td) => ({
      text: td.innerText.trim(),
      links: [...td.querySelectorAll('a[href]')].map((a) => ({ text: a.innerText.trim(), href: a.href })),
    })));
  return { headers, rows };
}

function toRecords({ headers, rows }, meta) {
  return rows.map((cells) => {
    const record = { fields: {}, links: [], ...meta };
    cells.forEach((cell, i) => {
      const name = headers[i] ?? `col${i}`;
      if (name === '操作') record.links.push(...cell.links);
      if (!DROP_COLUMNS.has(name)) record.fields[name] = cell.text;
    });
    return record;
  });
}

await withClient(async (client) => {
  const contextId = await loadContextId(client);
  await withTunnel(client, async (tunnel) => {
    await withCloudBrowser(client, {
      proxy: { type: 'local', tunnelId: tunnel.id },
      context: { id: contextId, mode: 'readWrite' },
    }, async ({ session, page }) => {
      console.log('session:', session.id);
      await ensureLoggedIn(page, session);

      await mkdir(DATA_DIR, { recursive: true });
      const records = [];
      for (let n = 1; n <= maxPages; n++) {
        await writeFile(new URL(`mis-page-${n}.html`, DATA_DIR), await page.content());
        const table = await page.evaluate(readTable);
        if (n === 1) console.log('表头:', table.headers.join(' | '));
        records.push(...toRecords(table, {
          page: n,
          sourceUrl: page.url(),
          sessionId: session.id,
          fetchedAt: new Date().toISOString(),
        }));
        console.log(`第 ${n} 页：${table.rows.length} 行`);

        if (n === maxPages || table.rows.length < perPage) break;
        await page.waitForTimeout(PAGE_DELAY_MS);
        await page.goto(listUrl(n + 1), { waitUntil: 'domcontentloaded' });
      }

      const out = new URL('mis-raw.jsonl', DATA_DIR);
      await writeFile(out, records.map((r) => JSON.stringify(r)).join('\n') + '\n');
      console.log(`写入 ${records.length} 条 → data/mis-raw.jsonl`);
    });
  });
});
