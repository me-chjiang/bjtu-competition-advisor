# 方案：北交大竞赛「能力匹配」Agent（Lexmount 真实任务挑战）

> AI 辅助生成（Claude Code），待团队确认。方案于 2026-10-13 确认；本文件是原方案的副本，下方「之后的变化」优先于正文。

## 之后的变化（截至 2026-10-15）

- 凭据改为放在 `lexmount-config.yaml`（模板见 `lexmount-config.example.yaml`），不再使用 `env.sh`。
- MIS 目前**不需要 VPN**，从公网就能访问；本地隧道保留为可选通道（10-13 已验证可以开通）。
- `inspectUrl` 弹窗登录延迟太高，改为本地前端输入账号后由后端代为登录，见 `issue.md` #1。
- MIS 登录路径与页面结构已实测，见 `教务系统/login-and-competition-guide.md`：
  - 竞赛项目列表在 `/innovation/cpitem/`；
  - 列表支持 `?page=&perpage=` 参数翻页；
  - 详情页在 `/innovation/cpitem_round/<id>/signup_view/`。
- Lexmount 接入路线：支持的设备（Linux）首选原生 MCP / CLI + Skill；SDK + Playwright 转接只作为备选（太卡）。
- MVP、量化标准、保研相关性、最终输出形式待讨论，见 `issue.md` #2–#5。
- 进度和交接事项见 `docs/handoff.md`。

原方案头注：截止 2026-10-25 23:59，计划 10-24 提交；团队 2–3 人。

## Context

北交大教学支撑平台（`aa.bjtu.edu.cn`）的「竞赛项目」页有 700 多条竞赛，分属不同学院，技能要求各不相同。学生难以判断自己适合参加哪些。

目标：Agent 通过对话逐步问出用户的能力和偏好，结合 MIS 竞赛数据与公开信息，评估能力差距，和用户讨论后给出参赛方案（推荐竞赛 + 备赛路线 + 时间线），以网页 Demo 交付。

约束：
- MIS 只能经客户端 VPN 访问；登录需要统一身份认证和算术验证码。
- 竞赛信息基本只在 MIS 上。

## 主办方工具的使用映射

| Lexmount 能力 | 用在哪里 | 作用 |
|---|---|---|
| CloudBrowser + **本地隧道** | MIS 采集 | 在不暴露内网的前提下让云浏览器访问 VPN 内系统 |
| **持久化 Context + fork** | 登录一次，fork 出多个已登录的 context | 并发抓取 700 条详情（Pro 25 并发），不用反复登录 |
| **Session 下载存储** | MIS 详情页附件、官网章程 PDF/Word | 取回本地后解析知识要求和赛程 |
| **WebFetch** | 静态官网和通知页批量读取 | 快、便宜；读取失败再升级到 CloudBrowser（分层抓取） |
| CloudBrowser（normal / light Moli） | 搜索引擎、JS 渲染的官网；简单页面试用 light 模式 | 处理需要交互的页面；light 模式的成本和效果待验证 |
| **录制回放 + 会话记录** | 所有云端会话 | 「过程可信」的证据，Demo 录屏也可以引用 |
| Agent 实时调用 | 讨论阶段核实争议点（如「今年还办吗」「去年什么题型」） | 让 Agent 的结论有现场证据 |
| CLI + Skill | 队友的 Apple Silicon / Windows 机器上，用 Claude Code + Skill 先手动探索 MIS 和官网结构 | 提高开发效率；投稿中作为「工具分工」写进去 |

- 不使用：官方代理（不用来规避站点规则）、自动验证码处理（MIS 走人工弹窗登录）。
- WebFetch 和 Moli 的具体接口与额度，第一天确认。

## 架构：Lexmount 全程参与

| 阶段 | 做法 | Lexmount 角色 |
|---|---|---|
| 1. MIS 采集 | 本机连 VPN → `client.tunnels.open()` 打开本地隧道 → 云浏览器经隧道访问 MIS | 云浏览器 + 本地隧道（SDK 0.6 官方能力，`node_modules/lexmount/README.md`「Access a company network」） |
| 2. 公开信息补全 | 云浏览器在必应搜索竞赛名 → 打开官网、往届通知、获奖公示 → DeepSeek 抽取知识要求、难度证据、赛程 | 云浏览器（不走隧道） |
| 3. Agent 对话与评估 | DeepSeek 多轮对话 + 工具调用；可在对话中实时触发云端搜索 | Demo 中现场调用 |

**弹窗登录**：
- 脚本创建会话后，在本机浏览器打开该会话的 `inspectUrl`（SDK `SessionInfo.inspectUrl`）。
- 用户在弹出的窗口里手动输入账号、密码和验证码。
- 脚本检测到跳转进 MIS 后接管。
- 登录态存进 Lexmount 持久化 context（`contexts.create` + `mode: 'readWrite'`），后续会话复用，减少重复登录。
- 凭据不写入任何文件或脚本。

**过程证据**：每个会话开启 `recording: { persistent: true }`；每条数据记录 session ID、URL 和读取时间。`connectUrl` 和 `inspectUrl` 能接管会话，不写进日志。

## 数据

**MIS 原始记录**（`data/mis-raw.jsonl`）：
- 列表字段：年度、项目编号、名称、级别（国际/国家/省部/校级）、类型（A/B/C）、轮次、报名时间。
- 详情页：「查看」后的全文。
- 负责人姓名不保存。

**竞赛去重**：700 条包含往年、多轮次、多赛区。按名称归一化后得到「竞赛」实体，再按报名时间筛出近期的。

**竞赛画像**（`data/competitions.json`）：
- 知识/技能要求标签（含程度）、形式（个人/组队、线上/线下）、赛程。
- 难度证据（往届题型、获奖比例等）和重要性证据（MIS 级别与类型、是否在全国竞赛目录内）。
- 每条附来源 URL；缺失的标「未说明」。
- **补全优先级**：近 6 个月可报名的 → A/B 类 → 其余（受 Browser hours 额度限制）。

## Agent 设计：多轮筛选 + 用户 review + 多 Agent 讨论

原则：
- 权重不是固定公式，而是「Agent 提出草案 → 用户 review → 根据反馈修正」。
- 规则只负责硬性条件和日期；其余维度用「档位 + 证据 + 置信度」表示，不压成一个分数。

**R0 画像访谈**（访谈 Agent）
- 从自由文本开始，逐步追问：年级与专业、技能及其证据（课程/项目/获奖）、每周可投入时间。
- 再问目标偏好：保研、简历、兴趣、奖金，个人还是组队，倾向的领域。
- 输出画像 + **初始权重草案**（附理由，例如「你提到保研，所以 A 类权重高」）。
- 用户 review：在侧栏直接修改，或用一句话纠正。

**R1 粗筛**（700 → 约 40）
- 硬条件：报名窗口、年级/学院限制。只在明确冲突时剔除。
- 领域相关：模型做宽松的语义匹配，宁可多留。
- 按领域分组展示，每条一句入选理由。
- 用户 review：保留、剔除、补充（「我也想看看数模类」）。被剔除的可以恢复。

**R2 精查**（约 40 → 10–15）
- 对候选实时调用 Lexmount（先 WebFetch，不行再用 CloudBrowser）补全公开信息。
- 每个竞赛生成多维评分卡，每维给出档位、证据链接和置信度：
  - 能力差距（按知识标签逐项）
  - 对用户目标的价值（MIS 级别/类型 + 公开认可度）
  - 时间成本 vs 可投入时间
  - 获奖可能
  - 赛程冲突
  - 组队需求
- 权重来自 R0 的草案，用户可用滑块或自然语言调整（「我更在乎能不能拿奖」）。
- **稳健性提示**：标出哪些竞赛在不同权重下都靠前（稳健推荐），哪些只在特定权重下靠前（看偏好）。
- 用户反馈（「这个太难」）会同时更新画像和权重，不只影响单条。

**R3 多 Agent 讨论**（10–15 → 2–3 套组合方案）
- 角色（用户可勾选参与讨论的角色）：
  - **能力教练**：差距能否在比赛前补上，怎么补
  - **收益分析师**：对用户目标的价值，级别与认可度
  - **时间规划师**：与课程、考试、其他比赛的冲突和总工作量
  - **学长学姐**：从公开经验帖和往届获奖情况出发发言，依赖 `web_lookup`
  - **质疑者**：挑战乐观假设、找证据缺口，必要时调 `web_lookup` 现场核实
  - **主持人**：汇总意见，必选
  - 预设「精简模式」：支持方 + 质疑者 + 主持人
- 流程：各自独立发表意见 → 交叉回应 1–2 轮 → 主持人综合成「稳妥型 / 冲刺型 / 探索型」组合，标注仍有分歧的点。
- 用户参与：
  - 讨论通过流式输出实时展示，用户旁听。
  - **用户可以随时插话**：消息进入队列，在下一位 Agent 发言前注入上下文，主持人负责回应或转交给相关角色。
  - 结束后用户 review 摘要（可展开全文），选定一套方案，或加约束（「下学期课多」）后重新讨论。

**R4 最终方案**
- 选定的竞赛及理由（附证据链接）。
- 备赛路线：针对每个差距，列出学什么、练什么、用什么资源、达到什么里程碑。
- 时间线：从报名截止日和比赛日倒推，可导出 `.ics` 日历。

**工具**（DeepSeek function calling）：
- `update_profile`、`update_weights`
- `search_competitions`、`get_competition`
- `web_lookup`：Lexmount WebFetch / CloudBrowser 实时查询
- `hard_filter`：确定性规则
- `scorecard`
- `make_plan`
- 每轮的输入、输出和用户反馈都写入会话日志，作为可复查的过程材料。

## 代码结构（Node，复用现有 `lexmount`、`playwright`、`dotenv`，不新增依赖）

- `lib/lexmount.mjs`：`withTunnel(fn)`、`withCloudSession(opts, fn)`，沿用 `scripts/smoke-test.mjs` 的 try/finally 关闭顺序（先 session，后 tunnel）。
- `lib/deepseek.mjs`：通过 `fetch` 调用 OpenAI 兼容接口（含 tools）。
- `collect/mis.mjs`：弹窗登录后，从持久化 context fork 出多个会话，并发遍历「竞赛项目」列表、详情和附件；限速，只读，不点「报名」。
- `enrich/fetch.mjs`：分层抓取（WebFetch → CloudBrowser），必应搜索 + 官网和章程抽取，带缓存。
- `agent/rounds/`：`r0-interview`、`r1-coarse`、`r2-scorecard`、`r3-debate`、`r4-plan`
- `agent/roles/`：教练、收益、规划、学长学姐、质疑、主持人的提示词
- `web/server.mjs` 用 SSE 推送讨论流；用户插话通过 POST 进入讨论队列
- `agent/tools.mjs`、`agent/filter.mjs`（硬条件和日期）
- `web/server.mjs`（Node 原生 `http`）、`web/index.html`：聊天区 + 画像/权重侧栏 + 每轮 review 面板 + 讨论记录 + 最终方案
- `lexmount-config.yaml` 增加 DeepSeek key（键名待定）；`data/` 不公开。

## 时间线与分工（A 采集/云端，B Agent/评分，C Demo/材料/用户测试）

范围优先级：先打通 R0→R1→R2→R4 主线；R3 多 Agent 讨论和插话第二周接入。如果时间不够，R3 先只做精简模式。

**批准后的第一步（由我来做）**：写 `lib/lexmount.mjs` 和 `collect/mis.mjs --pages 1`。你连上 VPN 后运行，在弹窗里登录，验证隧道、`inspectUrl` 交互和持久化 context 三件事。

- **10-14 决策门槛**：
  - A：隧道可用（需要项目开通 `custom_proxy` 权限）。
  - A：`inspectUrl` 弹窗登录成功，持久化 context 能保住登录态。
  - A：采到 1 页「竞赛项目」。
  - A：云端必应搜索跑通 1 个竞赛。
  - B：DeepSeek 工具调用跑通。
  - C：用活动页报名领取 Pro；登录投稿页查看表单字段。
- **失败兜底**：
  - 隧道权限未开：邮件 support@lexmount.cn 申请；期间先用本地 Playwright 采集 MIS，云端只做补全。
  - `inspectUrl` 不能交互：改为截图验证码，由用户在终端输入答案。
- **10-15～16**：全量采集 + 去重（A）；评分规则和画像结构（B）。
- **10-16～19**：公开信息补全，人工抽检 30 条（A）；Agent 对话流和工具（B）。
- **10-18～21**：网页 Demo（C，B 协助）。
- **10-21～23**：3–5 位同学真实试用，对比他们自己的判断，记录分歧和修正（C）。
- **10-23～24**：脱敏日志、session 回放、抽检表、2–3 分钟录屏；10-24 提交。

## 合规与安全

- 只用本人账号，只读、低频访问；Agent 不执行报名操作。
- 公开材料中给负责人和学生姓名打码，不公开 MIS 原始数据全集。
- 用户描述只发给 DeepSeek，不公开。

## 验证

- `node collect/mis.mjs --pages 1`：弹窗登录后输出 1 页记录，与 MIS 页面人工比对；Lexmount 控制台能看到回放。
- `node enrich/search.mjs --limit 3`：3 个竞赛带来源 URL 和 session ID。
- `agent/score.mjs` 用 3 份虚构画像（编程强/数学强/零基础）检查分档合理，硬性排除只依据明确冲突。
- `node web/server.mjs`：网页完成一次完整对话 → 推荐 + 备赛路线 + 时间线。
- 用户试用反馈和抽检表如实记录错误与失败。
