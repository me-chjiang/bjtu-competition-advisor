# Plan

> AI 辅助生成（Claude Code），loop-dev-cycle Phase 1 产出。
> - 第二轮（2026-10-16）是草案，`REQUIREMENTS.md` 中的「待拍板」事项确认后才开工。
> - 第一轮（2026-10-15 确认）保留在后半部分。
> - 接口契约见 `docs/api-contract.md`。

# 第二轮：竞赛行情调研与参赛方案优化（草案）

## 架构

```text
Vue 前端：画像对话 │ 方向报告 │ 调研卡片 + 现场调研 │ 方案 │ MIS 登录（可选）
   │ HTTP
FastAPI 单进程
   ├─ /mis/*         collector.py   ✅ 第一轮已完成
   ├─ /research/*    research.py    调研任务（进程内 asyncio，限制并发）
   ├─ /directions/*  report.py      方向行情报告汇总
   ├─ /sessions/*    agent.py       LiteLLM：画像对话、卡片分析、路线起草（用户负责）
   └─ /competitions/*
Lexmount：调研会话开录制，不用持久化 context（公开站点无需登录）；MIS 会话沿用第一轮实现
数据：data/public/  公开调研结果（摘录 + 链接）
      data/mis/     校内数据（私有）
```

## 单个竞赛的调研管线

1. **种子**：竞赛名称，可选附带官网地址。
2. **搜索**：云浏览器打开必应，用 4 类固定查询：官网、当年通知/章程、获奖名单、备赛经验。
3. **选页**：由代码挑选要打开的链接。
   - 优先官网、`edu.cn`、`gov.cn` 和白名单里的经验站点；
   - 每个竞赛最多 8 页，只处理 HTML 和 PDF，并限制大小。
4. **抓取**：在页面内提取正文，保存截断后的摘录、URL、读取时间、session ID 和每一步的截图。
5. **抽取**：LiteLLM 结构化输出卡片字段，并引用证据 ID。
   - 代码校验：引用必须存在、日期格式正确、年度一致。
   - 这一步模型没有任何工具。
6. **抽检**：人工抽检 30 条。

## Lexmount 使用点

- 运行需要 JS 渲染的页面和搜索引擎。
- 用多个并发会话批量调研。
- 下载章程 PDF。
- 录制回放，加上自存的过程截图，作为过程证据。
- MIS 代填登录：验证码截图回显，登录会话不录制。
- 待验证：SDK 能否导出录像。评委看不到我们的控制台，回放不能只留在控制台里。

## ADR

| # | 决策 | 原因 | 替代方案 |
|---|---|---|---|
| 5 | 核心从 MIS 采集转为公开网络调研 | 评委无法登录 MIS；公开调研才能体现 Lexmount 的价值，也可以复现 | 继续以 MIS 为核心 |
| 6 | 去哪些页面由代码决定，模型只做抽取 | 网页内容不可信，防止提示注入和越界访问 | 让模型自主浏览 |
| 7 | 方案优化（工时、冲突、技能复用、排序）由代码计算 | 结果确定、可解释，可以写进「过程可信」 | 由模型直接给出排序 |
| 8 | 提前批量调研 + 现场调研单个竞赛 | 单个竞赛要几十秒到几分钟，全部现场跑延迟太高；只用提前调研的数据，又看不到云浏览器实时工作 | 全部现场调研；全部提前调研 |

## 排期（10-16 → 10-24）

| 日期 | Claude Code | 用户 |
|---|---|---|
| 10-16 | 方案落盘；定卡片和证据的数据结构；更新契约；核实种子目录；验证能否导出录像 | 确认方向和分工 |
| 10-17～18 | `research.py`：先跑通单个竞赛，再做批量 | `agent.py`：画像对话、LiteLLM 工具循环 |
| 10-19 | 批量调研 30–50 个竞赛 + 抽检 + 方向报告 | 卡片分析、路线起草 |
| 10-20 | 前端：报告页、调研卡片、现场调研进度 | 接入前端 |
| 10-21 | 方案优化计算；联调 | 联调 |
| 10-22～23 | 3–5 人试用，修正问题 | 试用与修正 |
| 10-24 | 录屏、准备材料、提交 | |

## 风险

| 风险 | 缓解 |
|---|---|
| 必应在云浏览器中触发反爬或验证码 | 低频访问；失败后换查询或来源；用提前调研的数据兜底 |
| 知乎等经验站点有登录墙 | 只用公开可访问的页面，其余标「信息不足」 |
| 抽取时模型编造信息 | 引用校验 + 人工抽检；没有证据的结论不展示 |
| 评委看不到回放 | 自存过程截图和访问日志 |
| 并发数和 Browser hours 额度不够 | 领取 Pro；批量调研并发 3–5 |
| 版权 | 只保存摘录和链接 |
| 只剩 8 天 | 关键路径是调研管线和 Agent，两条线并行 |

---

# 第一轮：前端 + MIS 登录/采集（2026-10-15 确认）

## 架构

```text
浏览器 ──▶ frontend/（Vite dev，127.0.0.1:5173）
              │  /mis /sessions /competitions 代理到后端
              ▼
           backend/（FastAPI，127.0.0.1:8000）
              ├── /mis/*：collector.py ──▶ Lexmount Python SDK + Playwright(CDP) ──▶ MIS/CAS
              │                              └─▶ data/mis/*.json（被 git-ignore）
              └── /sessions/*、/competitions/*：用户按契约实现（Agent）
```

- 前端通过 `VITE_MIS_API` 和 `VITE_AGENT_API` 两个开关，分别决定 MIS 接口和 Agent 接口走 `mock` 还是 `real`。
- mock 是一个在内存里运行的参考后端，返回的数据结构与契约一致。

```text
frontend/
  src/api/types.ts      契约类型
  src/api/client.ts     fetch 封装，统一的 {code,message} 错误
  src/api/mock/         mock 后端 + 虚构 fixtures
  src/views/            LoginView、LoginWaitView、AdvisorView（hash 路由）
  src/components/       StageBar、ChatPanel、ProfilePanel、CandidateList、
                        ScorecardList、RoutePlan、CompetitionDrawer、DynamicForm
backend/                uv 项目，Python ≥3.11
  main.py      FastAPI app：/mis/* 路由，lifespan 中关闭会话，422 脱敏
  collector.py 读取配置；LoginSession 跨请求持有云会话；采集逻辑
  schemas.py   MIS 相关的 Pydantic 模型
  storage.py   原子写 JSON
  tests/
```

## 复用

- `collect/mis.mjs`：
  - 页面内的 `readTable` JS 原样复用；
  - `toRecords` 和 `DROP_COLUMNS` 的逻辑改写为 Python；
  - 复用 `needsLogin` 的判断方式、SSO 新标签页的处理流程，以及两个 URL 常量。
- `lib/lexmount.mjs`：
  - 沿用配置键名 `api-key`、`project-id`、`base-url`；
  - 沿用关闭顺序：先关浏览器，再关会话。
- `.state/mis-context.json` 与 Node 脚本共用。
- `教务系统/login-and-competition-guide.md` 里的 CAS 选择器，作为动态提取失败时的兜底。

## ADR

| # | 决策 | 原因 | 替代方案 |
|---|---|---|---|
| 1 | Vue 3 + Vite + TS，只额外引入 vue-router，不用 UI 库 | 多个面板的状态用组件管理更清楚；依赖少 | React（团队没有偏好）；纯 HTML（面板多了以后状态混乱） |
| 2 | 登录会话跨 HTTP 请求持有：单例 `LoginSession` 加闲置计时器 | 验证码必须和账号密码在同一次页面加载中提交 | 在一次请求里阻塞等用户输入：长时间占用连接，超时难处理 |
| 3 | 采集用进程内的单个 asyncio 任务，前端轮询进度 | plan 要求不搭后台任务系统；等待页需要显示进度 | 同步长请求：约 1 分钟没有任何进度 |
| 4 | 以契约文档为准，TS 类型手写；`cards` 用 `kind` 区分类型；卡片带 `ranks` 字段，前端据此排序 | 后端还没写，需要一份共同遵守的约定 | 等后端写完再对接：前端无法独立开发 |

## 任务

| # | 任务 | 复杂度 | 依赖 |
|---|---|---|---|
| 1 | 落盘 REQUIREMENTS、PLAN、CYCLE_STATE 和 `docs/api-contract.md` | 中 | — |
| 2 | 前端脚手架：types、client、mock、路由 | 低 | 1 |
| 3 | 登录页和等待页（DynamicForm、验证码、错误展示），接 mock | 中 | 2 |
| 4 | Agent 页：R0 → R1 → R2（排序、多选）→ R4，加详情抽屉和刷新恢复 | 高 | 2 |
| 5 | 前端测试 | 中 | 3、4 |
| 6 | 后端小样验证：用 Python SDK 建一个不录制的会话，经 CDP 连上后关闭 | 低 | — |
| 7 | `collector.py`（登录状态机 + 采集）和 `main.py` | 高 | 6 |
| 8 | 后端测试 | 中 | 7 |
| 9 | 联调；用户本人真实登录一次 | 中 | 5、8 |
| 10 | 更新 issue、handoff、AGENTS 和 `.gitignore` | 低 | 9 |

## 风险

| 风险 | 缓解 |
|---|---|
| Python SDK 接口与 Node 版不一致，或不支持关闭录制 | 先做任务 6 的小样验证；不一致就停下来汇报 |
| 从 CAS 页面动态提取输入框不稳定 | 兜底用已知选择器；字段 `name` 由后端提供，前端不写死 |
| 登录会话没关，持续计费 | 单例 + 180 秒闲置自动关闭 + lifespan 中关闭 + `finally` |
| 账号被锁 | 不自动重试；每个 login_id 最多 3 次 |
| `/innovation/cpitem/` 不支持 `perpage` 参数 | 按实际返回的行数翻页，设页数上限 |
| 契约与用户写的后端不一致 | 契约文档先交用户确认 |

## 迭代策略

1. 完成任务 1–5 后汇报：此时前端可以纯 mock 演示。
2. 完成任务 6–8 后汇报：此时后端单测通过。
3. 完成任务 9–10 后进入 Phase 3。
