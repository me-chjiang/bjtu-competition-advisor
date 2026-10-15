# bjtu-competition-advisor

北交大竞赛「能力匹配」Agent，Lexmount「真实任务挑战」参赛作品（截止 2026-10-25 23:59，北京时间）。

## 快速开始：现有采集工具（Linux / macOS）

```bash
npm ci                                   # 需要 Node >= 20
cp lexmount-config.example.yaml lexmount-config.yaml
chmod 600 lexmount-config.yaml           # 填入自己的 Lexmount key 和 MIS 账号，不要提交
node scripts/smoke-test.mjs              # 期望输出 session ID 和 "title: Example Domain"
```

- 不需要在本地安装浏览器：Playwright 只通过 CDP 连接 Lexmount 云浏览器。
- 采集 MIS 的命令：`node collect/mis.mjs --pages 1 --perpage 20`。登录方式正在调整，见 `issue.md` #1。
- 这条 SDK + Playwright 路线较卡，只是备选；Linux 等支持的设备优先用 Lexmount 原生 MCP / CLI + Skill（见 `AGENTS.md`）。

## 业务后端方向（尚未实现）

- Python + FastAPI + LiteLLM，通过 Lexmount Python SDK 按需补全资料。
- 单进程、单 Agent、本地 JSON 数据，不使用 PostgreSQL、Redis 或独立任务队列。
- 前端通过 HTTP 接口独立对接，先完成画像 → 筛选 → 证据分析 → 备赛路线的闭环。
- 现有 Node 代码是采集与探索工具，不要求立即迁移；上面的 `npm` 命令不是 Python 后端启动命令。
- 合并后的详细设计见 [`docs/plan.md`「后端方案」](docs/plan.md#后端方案2026-10-15-合并)，实施待办见 [`docs/handoff.md`](docs/handoff.md)。

## 文档地图

| 文件 | 内容 |
|---|---|
| `docs/handoff.md` | **当前进度、待办、待决事项（交接从这里开始）** |
| `docs/plan.md` | 项目方案、最新轻量 Python 后端设计及保留的历史方案 |
| `issue.md` | 未解决的问题 |
| `docs/project-brief.md` / `docs/project-overview.html` | 给评委看的项目简介（HTML 未审核） |
| `教务系统/login-and-competition-guide.md` | MIS 登录路径、竞赛列表与详情页结构 |
| `lexmount-real-task-challenge.md` | 比赛规则、资源、API 调研汇总 |
| `real-task-challenge-product-options.md` | 早期四个选题方案的分析（已被现方案取代） |
| `AGENTS.md` | AI 编码助手（Claude Code / opencode）的项目约定 |

## 代码

- `lib/lexmount.mjs`：读取配置、管理云会话和本地隧道的生命周期
- `scripts/smoke-test.mjs`：云浏览器冒烟测试
- `collect/mis.mjs`：MIS 竞赛列表采集（未端到端跑通）
