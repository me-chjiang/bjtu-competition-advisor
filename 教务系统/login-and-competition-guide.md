# 北交大教务系统：登录与竞赛详情查看

> AI 辅助生成（Claude，2026-10-13 用 Playwright MCP 实测）

账号密码统一存在项目根目录的 `lexmount-config.yaml`（已 git-ignore），键名：

| 键 | 含义 |
|---|---|
| `bjtu-entry-url` | 竞赛报名页 `https://aa.bjtu.edu.cn/innovation/cpitem_round/signup/` |
| `bjtu-username` | MIS 学号 |
| `bjtu-password` | MIS 密码 |

脚本读取方式与 `scripts/smoke-test.mjs` 一致：`parse(readFileSync('lexmount-config.yaml'))`。不要把值打印到终端或写进文档。

## 1. 登录

### 结论：必须走 MIS 统一身份认证（CAS），不要用教务系统自带登录页

| 入口 | URL | 结果 |
|---|---|---|
| 教务系统本地登录 | `https://aa.bjtu.edu.cn/client/login/?next=...` | ❌ 提示「密码错误，登录失败」——该页面账号体系与 MIS 不同 |
| MIS 统一认证 | `https://cas.bjtu.edu.cn/auth/login/...` | ✅ 成功 |

直接访问 `https://aa.bjtu.edu.cn/innovation/cpitem_round/signup/` 未登录时会被重定向到上面的**本地登录页**，别在这里填，容易误触发账号锁定。

### 实测步骤

1. 打开 `https://mis.bjtu.edu.cn/`，自动跳转到 `cas.bjtu.edu.cn/auth/login/?next=/o/authorize/...`（OAuth2 授权码流程）。
2. 填表：
   - 用户名：`getByRole('textbox', { name: 'Loginname' })`
   - 密码：`getByRole('textbox', { name: 'Password' })`
   - 验证码：`#id_captcha_1`
3. **验证码是算术题图片**（如 `7×8=`、`7-4=`），图片元素为 `getByRole('img', { name: 'captcha' })`。做法：对该元素截图 → 识别算式 → 填计算结果（本次填 `56`）。
4. 点击 `getByRole('button', { name: 'Login' })`，跳到 `https://mis.bjtu.edu.cn/home/`，登录成功。
5. 进入教务系统：在 MIS 首页点击 **「32.教务系统」**（href `/module/module/10/`）。它会在**新标签页**打开 `https://aa.bjtu.edu.cn/notice/item/`，SSO 自动完成，教务系统 session 建立。
   - 注意切换到新标签页（`browser_tabs select index=1`）。
6. 此后在该 context 中直接 `goto` 任何 `aa.bjtu.edu.cn` 页面均无需再登录。

```js
// Playwright 等价代码
await page.goto('https://mis.bjtu.edu.cn/');
await page.getByRole('textbox', { name: 'Loginname' }).fill(USER);
await page.getByRole('textbox', { name: 'Password' }).fill(PASS);
await page.getByRole('img', { name: 'captcha' }).screenshot({ path: 'captcha.png' });
// ...识别算式，得到 answer
await page.locator('#id_captcha_1').fill(answer);
await page.getByRole('button', { name: 'Login' }).click();
const [aa] = await Promise.all([
  page.context().waitForEvent('page'),
  page.getByRole('link', { name: '教务系统' }).click(),
]);
await aa.goto('https://aa.bjtu.edu.cn/innovation/cpitem_round/signup/');
```

## 2. 竞赛列表在哪里

- 导航：顶栏「实践创新」→ 左侧「学科竞赛」→ **「竞赛报名」**
- URL：`https://aa.bjtu.edu.cn/innovation/cpitem_round/signup/`（页面标题「可报名项目轮次」）
- 表头：年度 / 项目编号 / 竞赛项目名称 / 级别 / 类型 / 轮次 / 负责人 / 报名时间 / 操作
- 操作列：「查看」始终有；「报名」只在报名期内出现
- **分页**：页面分页按钮是 JS（`href="#"`），但后端支持 GET 参数，直接用
  `?page=1&perpage=500` 一次拿到全部（实测共 43 条，1 页）。
  `perpage` 可选 20/50/100/200/500。
- **筛选**：同一 URL 的 GET 表单参数
  - `competition_q` 竞赛编号/名称
  - `cpitem_q` 项目编号/名称
  - `round_q` 轮次（1-8）

左侧其他相关入口：
- 我的比赛 `/innovation/cpteam/`
- 竞赛项目 `/innovation/cpitem/`

## 3. 怎么看比赛详情

- 列表里「项目编号」「竞赛项目名称」「轮次」「查看」四个链接都指向同一个详情页：
  `https://aa.bjtu.edu.cn/innovation/cpitem_round/<round_id>/signup_view/`
  （`round_id` 是内部 ID，如全国大学生数学竞赛 = `163`，不是项目编号）
- 「报名」链接：`/innovation/cpteam/create/?cpitem_round_id=<round_id>`（会创建队伍，**只看不要点**）
- 详情页标题「可报名项目轮次详情」，含两张 `table.table-bordered-2`，结构是 `<th>键</th><td><p>值</p></td>` 成对排列：
  - **竞赛项目信息**：年度、竞赛名称、项目编号、项目名称、项目管理单位、项目级别、竞赛类别、竞赛属性、参赛形式、参赛方式、主办单位
  - **竞赛项目轮次信息**：年度、项目名称、轮次、学科竞赛负责人、承办单位、竞赛地点、最大队数、每队最大人数、每人参加最大队数、报名开始/结束时间、比赛通知
- 部分字段可能为空（例：数学竞赛的竞赛属性、参赛形式、主办单位、比赛通知均为空）。
- 示例截图：`competition-detail-example.png`

提取详情的 JS：

```js
() => Object.fromEntries(
  [...document.querySelectorAll('.main-content table th')]
    .map(th => [th.innerText.trim(), th.nextElementSibling?.innerText.trim() ?? ''])
)
```
（两张表有重名键「年度」「项目名称」，需要的话按表分别提取。）

## 4. 探索经验（踩坑记录）

1. **先看重定向落在哪个登录页。** 目标 URL 未登录时跳的是 `aa.bjtu.edu.cn/client/login/`（英文界面、无验证码），和用户给的截图（MIS 统一认证中心、带验证码）不是同一个页面。凭据属于 MIS，在本地登录页只会报「密码错误」。
2. **登录失败只试一次就换路。** 不确定是哪套账号体系时，不要在同一页面反复重试，避免触发锁定；对照截图找到正确入口再试。
3. **MIS 入口靠 `mis.bjtu.edu.cn` 自动跳 CAS**，不必手拼 `cas.bjtu.edu.cn` 的 OAuth 参数（`client_id`/`state` 是动态的）。
4. **验证码是算术图片。** 用元素截图（`scale: 'device'` 更清晰）后由模型读图计算即可；输入框没有可访问名，用 `#id_captcha_1` 定位。验证码每次刷新页面都会变，截图和提交要在同一次页面加载内完成。
5. **MIS 里的应用会开新标签页。** 点「32.教务系统」后当前页仍停在 MIS，要切到新 tab 才能看到 `aa.bjtu.edu.cn`；此后同一浏览器 context 里直接 `goto` 即可。「11.本科教学服务平台」是另一个系统，不是这里。
6. **截图/快照路径受限。** Playwright MCP 只能写项目目录和 `.playwright-mcp/`，写 `/tmp` 会被拒；相对路径以项目根目录为基准。
7. **列表分页别点按钮。** 分页链接是 `href="#"` 的 JS，直接用 `?page=&perpage=` GET 参数更稳；表单筛选同理是 GET。
8. **从 DOM 取数比读快照省事。** 用 `browser_evaluate` 直接抽 `table tbody tr` 的单元格和 `a[href]`，一次就能拿到 `round_id` 与详情链接；accessibility 快照很长，只在定位元素时用。
9. **只读操作。** 「报名」链接（`/innovation/cpteam/create/`）会建队，探索时不要点。
10. **`.playwright-mcp/` 会留下页面快照和 console 日志**（含学号、姓名等），已加入 `.gitignore`。
