# 交接：进度与待办（2026-10-15）

> AI 辅助生成（Claude Code / OpenCode），根据截至 10-15 的工作记录和用户讨论整理；后端方向已更新，相关功能尚未实现。

截止：2026-10-25 23:59（北京时间），计划 10-24 提交。方案见 `docs/plan.md`，原定 10-14 的决策门槛目前只完成了一部分。

## 已完成 / 已验证

| 事项 | 状态 | 位置 |
|---|---|---|
| 比赛规则、资源、API 调研 | 完成 | `lexmount-real-task-challenge.md` |
| 选题与方案 | 10-13 确认 | `docs/plan.md` |
| 轻量后端技术方向 | 10-15 用户明确采用 Python + LiteLLM、Lexmount Python SDK；FastAPI 和本地 JSON 为合并的实现建议，尚未实现 | `docs/plan.md`「后端方案」 |
| Lexmount 云浏览器冒烟测试 | 10-13 通过（创建会话 → 打开网页 → 关闭） | `scripts/smoke-test.mjs` |
| Lexmount 本地隧道 | 10-13 开通成功，项目已有 `custom_proxy` 权限 | `lib/lexmount.mjs` 的 `withTunnel()` |
| MIS 登录路径与页面结构 | 10-13 用本地 Playwright 实测 | `教务系统/login-and-competition-guide.md` |
| MIS 当前是否需要 VPN | 10-15 确认不需要；隧道保留为可选通道 | — |
| SDK + Playwright 采集路线 | 能用但很卡，10-15 定为备选路线；Linux 优先用原生 MCP | `collect/mis.mjs` |
| 给评委的项目简介 | brief 已审；HTML **未审**（10-15 决定先保持现状） | `docs/project-brief.md`、`docs/project-overview.html` |

## 进行中 / 待办（按方案中的分工：A 采集与云端，B Agent 与评分，C Demo、材料与用户测试）

### A：采集与云端
- [ ] 在 Linux 上验证 Lexmount 原生 MCP / CLI + Skill 的接入（首选路线），记录接入步骤。SDK + Playwright 只作为不兼容设备的备选。
- [ ] **`issue.md` #1**（备选路线）：去掉 `inspectUrl` 弹窗登录（延迟太高），改为「本地前端输入账号 → 后端用 Lexmount 登录」。隧道改为可选开关。
- [ ] `collect/mis.mjs` 端到端跑通 1 页，再全量采集约 700 条及详情页；去重。
  - 代码已写好，但没有成功跑过。
  - 采集对象是「竞赛项目」页 `/innovation/cpitem/`；这个页面是否支持 `perpage` 参数还没验证（「竞赛报名」页支持）。
- [ ] `enrich/fetch.mjs`：分层抓取，先用 WebFetch，失败再用云浏览器；用必应搜索补全竞赛官网和章程。WebFetch 的接口和额度待确认。

### B：Agent 与评分
- 后端由本次讨论的用户主要负责，采用 Python + FastAPI + LiteLLM + Lexmount Python SDK；详见 `docs/plan.md`「后端方案」。单进程、单 Agent、本地 JSON，不引入 PostgreSQL、Redis 或独立 Worker。
- [ ] 确认模型 key 的安全读取方式，搭建 `backend/`，通过 LiteLLM 跑通结构化输出和工具调用；不再开发原计划的 `lib/deepseek.mjs`。
- [ ] 用少量审核数据跑通 R0 访谈 → R1 粗筛 → R2 证据卡片 → R4 路线，并支持用户修改和确认。
- [ ] 与采集侧约定竞赛实例、通知和证据的 JSON 格式；首轮建议深度验证 30–50 个实例，不把约 700 条原始记录等同于不同竞赛。
- [ ] 用 Python 函数检查资格、每周工时和日期冲突，补充工具失败、引用和会话恢复测试。
- [ ] 在主线稳定后接入 Lexmount Python SDK 在线补全；`.ics` 和流式输出按 MVP 决策安排。R3、实时插话和复杂权重滑块后置，不作为主线前置条件。
- 现有 Node 采集脚本保留；Python 后端 SDK 接入不等于采集脚本已迁移或已经验证。

### C：Demo、材料与用户测试
- [ ] 用活动页报名，领取 2 个月 Pro（Free 只有 3 个并发，Browser hours 也少）。
- [ ] 登录投稿页，查看表单字段（未登录时看不到）。
- [ ] 独立前端通过 FastAPI HTTP 接口对接（对话、画像编辑、候选保留/排除/恢复、阶段确认、结果与证据展示）；不再依赖原方案的 `web/server.mjs`，前端框架待定。
- [ ] `docs/project-overview.html`：10-15 决定暂不审核，先保持现状。
- [ ] 评估：
  - 人工抽检 30 条；
  - 用 3 份虚构画像检查分档；
  - 请 3–5 位同学试用。
- [ ] 提交材料：脱敏日志、session 回放、抽检表、2–3 分钟录屏。

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
