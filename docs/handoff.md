# 交接：进度与待办（2026-10-29 更新）

> AI 辅助生成（Claude Code / OpenCode），截至 10-18：隔离工作区 Task 1–5 分任务独立审查及最终问题修复复审均通过。最终审查发现的否定画像误写、过去任务可确认及状态文档问题已关闭。本波离线全套 **426 passed**（修复前 391），验证见下方报告。真实模型/provider/SDK/MIS 联网未验收；任务与最终修复均由控制者正常 GPG 提交，不自动 push。

截止：2026-11-08（10-29 用户确认，原定 10-25 已延期）。方案见 `docs/plan.md`，原定 10-14 的决策门槛目前只完成了一部分。

## 10-16 更新（优先阅读）

- **方向调整**：核心从「MIS 采集 + 推荐」转为「公开网络上的竞赛行情调研 + 参赛方案优化」，MIS 降为可选。
  - 详见 `docs/plan.md`「方向调整（2026-10-16）」、根目录 `REQUIREMENTS.md` 和 `PLAN.md` 的「第二轮」。
  - 有 5 项待拍板，拍板前不开工。
- **第一轮已交付**（loop-dev-cycle，进度见 `CYCLE_STATE.md`）：
  - `frontend/`：Vue 3 + Vite + TS。
    - 登录页、等待页，以及 R0→R1→R2→R4 的 Agent 页（mock 模式）；
    - MIS 和 Agent 各有一个开关，可以分别在 mock 和真实后端之间切换。
    - 已在 `frontend` 分支提交。
  - 旧 MIS 后端（FastAPI + Lexmount Python SDK，`/mis/*` 代填登录与列表采集，用户本人登录后实测成功）：10-29 合并 main 时按用户决定删除，改以 main 的 Agent 后端为准；`collector.py` 与 `/mis/*` 待移植进新后端。
  - `docs/api-contract.md`：前后端接口契约。Agent 部分待用户确认，并且需要按第二轮调整，例如补上 S 类、新增 `/research` 和 `/directions` 接口。
- **运行方式**
  - 后端：见 `README.md`
  - 前端：`cd frontend && npm ci && npm run dev`
  - 默认使用 mock；要接真实 MIS 时，前面加上 `VITE_MIS_API=real`。

## 已完成 / 已验证

| 事项 | 状态 | 位置 |
|---|---|---|
| 比赛规则、资源、API 调研 | 完成 | `lexmount-real-task-challenge.md` |
| 选题与方案 | 10-13 确认 | `docs/plan.md` |
| 轻量后端主线 | Python + FastAPI + LiteLLM + JSON 已实现；Task 1–5 分任务审查通过，Python Lexmount SDK 尚未接入 | `backend/`、`README.md` |
| Lexmount 云浏览器冒烟测试 | 10-13 通过（创建会话 → 打开网页 → 关闭） | `scripts/smoke-test.mjs` |
| Lexmount 本地隧道 | 10-13 开通成功，项目已有 `custom_proxy` 权限 | `lib/lexmount.mjs` 的 `withTunnel()` |
| MIS 登录路径与页面结构 | 10-13 用本地 Playwright 实测 | `教务系统/login-and-competition-guide.md` |
| MIS 当前是否需要 VPN | 10-15 确认不需要；隧道保留为可选通道 | — |
| SDK + Playwright 采集路线 | 能用但很卡，10-15 定为备选路线；Linux 优先用原生 MCP | `collect/mis.mjs` |
| 给评委的项目简介 | brief 已审；HTML **未审**（10-15 决定先保持现状） | `docs/project-brief.md`、`docs/project-overview.html` |

## 进行中 / 待办（按方案中的分工：A 采集与云端，B Agent 与评分，C Demo、材料与用户测试）

### A：采集与云端
- [ ] 在 Linux 上验证 Lexmount 原生 MCP / CLI + Skill 的接入（首选路线），记录接入步骤。SDK + Playwright 只作为不兼容设备的备选。
- [x] **`issue.md` #1**（备选路线，10-15 已实现）：去掉 `inspectUrl` 弹窗登录（延迟太高），改为「本地前端输入账号 → 后端用 Lexmount 登录」。隧道改为可选开关。
- [x] 列表全量采集已由旧 MIS 后端 `collector.py` 完成（10-29 已随旧后端删除，待移植）（10-15：竞赛项目 724 条，可报名轮次 43 条）；详情页和 Node 脚本 `collect/mis.mjs` 未跑。
  - 代码已写好，但没有成功跑过。
  - 采集对象是「竞赛项目」页 `/innovation/cpitem/`；这个页面是否支持 `perpage` 参数还没验证（「竞赛报名」页支持）。
- [ ] `enrich/fetch.mjs`：分层抓取，先用 WebFetch，失败再用云浏览器；用必应搜索补全竞赛官网和章程。WebFetch 的接口和额度待确认。

### B：Agent 与评分
- 10-18：用户已批准[实现计划](superpowers/plans/2026-10-18-backend-mvp.md)。Task 1–5 分任务独立审查及最终问题修复复审均通过。可选 `weekly_hours` 与 `additional_context` 已纳入源码/OpenAPI；无预算不阻止画像确认/筛选，但 unknown 路线不可最终确认。
- 后端由本次讨论的用户主要负责，采用 Python + FastAPI + LiteLLM + Lexmount Python SDK；详见 `docs/plan.md`「后端方案」。单进程、单 Agent、本地 JSON，不引入 PostgreSQL、Redis 或独立 Worker。
- [x] `backend/`、环境/显式 YAML 配置、工具循环、schema、目录规则、原子存储已实施并经 Task 1–4 独立审查；默认 app 不自动读 YAML，缺 key 只在 chat 明确报错。安装/启动见 README。
- [x] Task 5 独立审查与修复复审：HTTP R0 → R1 → R2 → R4、用户修改/确认、重启重放、失败/取消/写盘异常、越权 fake 及 OpenAPI。候选重生成保留用户决定的修复已复审通过；该任务当时 HTTP 聚焦 **50 passed**、控制者完整 pytest **391 passed**，Ruff check / format --check / diff --check 通过。实施阶段的隔离单 worker Uvicorn 本机 HTTP 冒烟通过。报告保存在本工作区 `.superpowers/sdd/2026-10-18-backend-mvp/task-5-report.md`（临时材料未提交）。最终修复复审亦已通过；真实联网另行验收。
- [ ] 按 [LLM 对接约定](llm-integration.md) 执行真实 provider 的工具/JSON、时延、费用和质量验收；离线测试包含异步、tool_call_id、引用/预算/错误与 SDK 本地 mock 日志隐私回归，不是联网证明。
- [x] 最终集中修复 scoped 复审通过：年级/专业/工时改为有限肯定/更正语法，否定/冲突/不明确先核对且保留确认画像和旧有效结果；技能/删除/中文 team 保持独立。路线统一拒绝早于注入 clock 的北京时间今天的任务起点，不为该任务分配负载、不猜已完成；工具/生成/延迟确认共用规则。默认 Agent 上下文提供同 clock 的日期及时区。修复及 RED/GREEN 证据见本工作区 `.superpowers/sdd/2026-10-18-backend-mvp/final-fix-report.md`，复审见同目录 `final-fix-review.md`（临时材料未提交）。本波新增 35 项回归，全套 **426 passed**；复审独立最小选集 **42 passed**，另有 8 个内联探针通过。
- [ ] 用少量人工审核的真实竞赛数据复验主线；目前 HTTP 闭环使用 tmp_path 虚构目录、ScriptedAgent 及默认 factory LiteLLMAgent + 本地 provider 桩，网络阻断，非真实 provider 验收；最低 Python 3.10 亦未实测。
- [ ] 与采集侧约定竞赛实例、通知和证据的 JSON 格式；首轮建议深度验证 30–50 个实例，不把约 700 条原始记录等同于不同竞赛。
- [x] Python 资格/报名时效/日期证据/每周负载与冲突规则，以及工具失败/引用/JSON 恢复已离线验证；HTTP 事务/确认连接已通过 Task 5 独立审查。
- [ ] 在主线稳定后接入 Lexmount Python SDK 在线补全；`.ics` 和流式输出按 MVP 决策安排。R3、实时插话和复杂权重滑块后置，不作为主线前置条件。
- 现有 Node 采集脚本保留；Python 后端 SDK 接入不等于采集脚本已迁移或已经验证。

### C：Demo、材料与用户测试
- [ ] 用活动页报名，领取 2 个月 Pro（Free 只有 3 个并发，Browser hours 也少）。
- [ ] 登录投稿页，查看表单字段（未登录时看不到）。
- [ ] 独立前端通过 FastAPI HTTP 接口对接（对话、画像编辑、候选保留/排除/恢复、阶段确认、结果与证据展示）；不再依赖原方案的 `web/server.mjs`，前端框架待定。
- [ ] 按 [前后端契约](frontend-contract.md) 进行独立前端联调：版本冲突、重复请求、画像/候选修改后失效、错误提示。API base URL 为 `http://127.0.0.1:8000/api`，本地入口已实现并通过 Task 5 独立审查；`/openapi.json` 可查字段。日历固定 501，不显示入口。
- [ ] `docs/project-overview.html`：10-15 决定暂不审核，先保持现状。
- [ ] 评估：
  - 人工抽检 30 条；
  - 用 3 份虚构画像检查分档；
  - 请 3–5 位同学试用。
- [ ] 提交材料：脱敏日志、session 回放、抽检表、2–3 分钟录屏。

## 10-29 前端对接决定

- 契约以后端为准：`docs/frontend-contract.md` + `/openapi.json`；`docs/api-contract.md` 的 Agent 部分作废。
- MIS 登录/等待页下线路由，`/` 直接进 `/advisor`；页面代码保留，`/mis/*` 移植另排期。
- 前端 TS 类型用 `openapi-typescript` 从 `/openapi.json` 生成（`npm run gen:api`）。
- 范围：先让 R0→R1→R2→R4 接通真实后端，第二轮（方向报告、调研卡片、现场调研）随后做。
- 连接：Vite 代理 `/api` → `127.0.0.1:8000`；单开关 `VITE_AGENT_API=real|mock`。
- 画像放宽：移除年级/专业/工时/技能/组队的句式守卫，模型自由整理并输出 Markdown `summary`（前端渲染）；相关守卫测试已删除。
- 联调目录：用 Lexmount 抓取算法编程 + 数学建模约 8–10 个竞赛，整理为 `data/competitions.json`（git-ignored），需人工审核。

## 待决事项（需要团队拍板）

1. 验证码怎么处理：建议后端截图显示在前端，用户输入后一起提交（见 `issue.md` #1）。
2. 前端代填账号之后，`lexmount-config.yaml` 里的 `bjtu-username` / `bjtu-password` 还保留吗？
3. 登录页是否作为独立前端的入口，相关登录接口是否并入 FastAPI？原方案的 `web/server.mjs` 已不作为业务后端。
4. 用户主要负责后端（B）；A、C 的具体负责人和协作接口仍需确认。
5. MVP 范围（`issue.md` #2）、量化标准（#3）、保研相关性按学科大类区分（#4）、最终输出用排序列表还是组合（#5）。

## 环境注意

- **Linux / opencode 协作者**：
  - opencode 读 `AGENTS.md`，Claude Code 读 `CLAUDE.md`（它会引入 `AGENTS.md`），两边的约定一致。
  - opencode 不读 `.claude/memory/` 和 `.mcp.json`，需要知道的事实都已写进 `AGENTS.md` 和 `docs/`。
  - Linux x64 可以安装 Lexmount CLI + Skill v1.2.4；opencode 会加载 `.claude/skills/` 和 `~/.claude/skills/` 下的 skill。
- 主力开发机是 Intel Mac，不能运行 Lexmount CLI + Skill，只能用 Node SDK。
- 每个人的 `lexmount-config.yaml` 和 `.state/`（持久化 context ID）都只在本机，不共享。
- 已有的 `.playwright-mcp/` 快照含个人信息，已 git-ignore。
