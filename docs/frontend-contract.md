# 前后端契约约定

> AI 辅助整理（OpenCode），2026-10-15；2026-10-18 同步已实现的轻量 Python 后端。HTTP 离线模拟闭环已验证，Task 5 待独立审查；真实 LLM/SDK/MIS 集成未验收。与 `plan.md` 的历史接口摘要冲突时，以本文和 `/openapi.json` 为准。

## 1. 通用约定

- 本地 API base URL：`http://127.0.0.1:8000/api`，下文路径均相对此地址。前端通过自身构建配置设置 base URL，不写死到页面逻辑。
- 请求和响应使用 UTF-8 JSON、`snake_case` 字段；成功响应直接返回对象，不额外套 `data`。日历下载例外。
- ID 为不透明字符串；前端不从 ID 推导年份、阶段或权限。时间使用带时区的 ISO 8601，纯日期使用 `YYYY-MM-DD`，界面按 `Asia/Shanghai` 展示。
- 未知值返回 `null`，空集合返回 `[]`；不要用空字符串、0 或虚构日期代替未知。新增可选字段应兼容旧前端，字段移除或含义变化须双方同步。
- 首版只做普通请求响应，不承诺 SSE、WebSocket、后台任务或断线续传。加载动画由前端维护，最终状态以服务端快照为准。
- 开发跨域只允许明确配置的前端 origin（协议、域名、端口），不默认放开 `*`。公网部署前须补充鉴权和会话归属检查；CORS 和随机 session ID 都不等于鉴权。
- 统一 JSON 错误包适用于业务路由、业务校验和 HTTP 错误边界；CORS 预检属于协议层，拒绝可能返回纯文本 `400`，前端不要强行解析为业务 JSON。
- 本文不包含 MIS 账号与验证码接口，其流程仍见 `../issue.md` #1；不得把账号或模型 key 塞入推荐聊天接口。

## 2. 接口清单

| 方法与路径 | 请求体 | 成功响应 |
|---|---|---|
| `POST /sessions` | `{}` | `201`，初始会话快照 |
| `GET /sessions/{id}` | 无 | `200`，会话快照 |
| `POST /sessions/{id}/chat` | `request_id`、`expected_revision`、`action`、`content` | `200`，更新后的快照 |
| `PATCH /sessions/{id}/profile` | `expected_revision`、`changes` | `200`，更新后的快照 |
| `PATCH /sessions/{id}/candidates/{candidate_id}` | `expected_revision`、`decision` | `200`，更新后的快照 |
| `POST /sessions/{id}/confirm` | `expected_revision`、`stage` | `200`，推进后的快照 |
| `GET /competitions/{id}` | 无 | `200`，竞赛实例及证据 |
| `GET /sessions/{id}/calendar.ics` | 无 | 可选功能：`200`，`text/calendar; charset=utf-8` |

日历启用后只导出最终确认且日期明确的事件；未完成方案返回 `409 PLAN_NOT_CONFIRMED`，没有可导出日期返回 `409 NO_CONFIRMED_DATES`。未启用功能返回 `501 FEATURE_NOT_ENABLED`，前端首版不展示下载入口。

### 会话快照

下面是初始会话的完整示例，所有数据为虚构示例：

```json
{
  "session_id": "s_demo",
  "revision": 0,
  "stage": "R0",
  "status": "collecting",
  "processing": false,
  "last_request_id": null,
  "message": "请介绍你的专业、年级和想参加竞赛的目标。",
  "messages": [],
  "profile": {
    "grade": null,
    "major": null,
    "skills": [],
    "weekly_hours": null,
    "goals": [],
    "team_preference": null,
    "unavailable_dates": [],
    "additional_context": null
  },
  "cards": [],
  "plan": null,
  "needs_confirmation": false
}
```

- `revision`：每次成功的业务状态修改加 1；GET、仅进入处理中或处理失败不增加。一次请求只提交一次最终状态。
- `stage`：仅 `R0 | R1 | R2 | R4`，首版没有 R3。
- `status`：`collecting | awaiting_review | completed`；`processing` 仅表示当前进程正在处理该会话，不是可跨重启恢复的任务。
- `needs_confirmation`：仅在 `awaiting_review` 为 `true`；前端依此显示确认按钮，但后端仍校验确认条件。
- `message`：本次面向用户的说明；`messages` 为可展示历史，每项含 `id`、`role`（`user | assistant`）、`content`、`created_at`，不包含系统提示词、工具原始记录或模型内部推理。
- `last_request_id`：最近成功提交的 chat 请求 ID，用于判断网络中断后的处理结果；不是鉴权凭据。
- `profile` 为当前画像草案；`cards` 和 `plan` 为当前有效结果，不把已失效结果混入其中。前端不能从聊天文案解析业务字段。

### 画像字段

`grade`、`major` 是字符串或 `null`；`skills` 每项为 `{name, evidence}`；`weekly_hours` 是大于 0 的每周小时数或 `null`；`goals` 为目标描述字符串数组；`team_preference` 为 `solo | team | either | null`；`unavailable_dates` 为不可安排任务的日期数组。

`weekly_hours` 是可选信息，缺失不阻止画像核对和竞赛筛选，也不强制首轮追问。未提供时可以生成投入估算与路线草案，但不能声称已经验证用户的时间预算；方案保持 `feasibility=unknown`，不能按已验证可行方案确认。

`additional_context` 为可选补充文本，类型 `string | null`、默认 `null`、最多 2000 字符，空白文本归一化为 `null`。用于补充经历、偏好和特殊限制，不是任意 JSON 扩展字段。整个文本随 PATCH 替换，`null` 清空。后端可以提出结构化信息修改建议，但不得把补充文本当系统指令或擅自解决与已确认字段的冲突；界面提醒勿填写账号密码等敏感信息。

`changes` 只允许上述字段，未提供的字段保持原值，数组整体替换；`null` 只用于允许为空的字段。模型提取的信息也是草案，不能把猜测当作用户确认。

## 3. 聊天、修改和阶段确认

### 发消息或生成草案

```json
{
  "request_id": "req_demo_001",
  "expected_revision": 0,
  "action": "message",
  "content": "我是大二计算机专业，学过 Python，每周能投入六小时。"
}
```

- `action=message` 时，`content` 必须为非空字符串，最多 4000 字符；用于访谈、提问或反馈。
- `action=generate` 时，`content` 固定为 `null`；基于当前状态生成或重生成本阶段结果。进入下一阶段后由前端显式发起，不在 confirm 内自动触发模型。
- R0 信息不足时继续追问，状态保持 `collecting`；生成可供核对的画像后为 `awaiting_review`。允许用户明确表示某项信息未知，不要求模型猜齐字段。
- R1/R2/R4 的普通问答不自动作废已生成结果；实质改变画像或候选时按下面的失效规则处理。

### 用户直接修改

```json
{
  "expected_revision": 2,
  "changes": {
    "weekly_hours": 4,
    "team_preference": "solo"
  }
}
```

- 画像发生变化：回到 R0，设为 `collecting`，清空有效 `cards` 与 `plan`；用户已明确排除的记录可保留为偏好，但必须重新检查资格并生成候选。自然语言引起的画像更正也遵循该规则，不静默覆盖已确认画像。
- 候选 `decision` 为 `keep | exclude | defer`，R1/R2/R4 可编辑。R1 编辑后仍可 review；R2/R4 编辑后回到 R1 的 `awaiting_review`，保留粗筛摘要、清除精查结论及方案，再确认进入 R2 重生成。前端应在操作前提示后续结果将失效，不自行修改 `stage`。
- 恢复用户排除的候选不改变资格结论；明确资格冲突的实例不能改成可推荐项，尝试将其设为 `keep` 返回 `422 VALIDATION_ERROR`。
- 结果页的节奏调整可在 R4 用 `chat` 反馈并重生成；新方案完成前不能把聊天答复当成已校验方案。

### 确认

```json
{
  "expected_revision": 3,
  "stage": "R0"
}
```

仅当前阶段与请求一致、状态为 `awaiting_review` 且校验通过时接受。R1 至少保留一个没有明确资格冲突的候选，R2 至少保留一个已分析候选；没有可选项时继续解释和调整，不能空确认。R0 → R1 → R2 → R4 的目标状态为 `collecting`，`needs_confirmation=false`，准备生成新阶段结果；R4 确认后为 `completed`。用户确认只确认当前版本，模型不能代用户触发此接口。

## 4. 推荐卡片、证据和路线

推荐卡片的最小形状（虚构示例，非实际推荐）：

```json
{
  "competition_instance_id": "ci_demo_2026_school",
  "name": "示例竞赛：2026 校内选拔",
  "registration_status": "unknown",
  "registration_deadline": null,
  "eligibility": "unknown",
  "decision": "defer",
  "reason": "领域相关，但本届报名资格和时间尚未核实。",
  "dimensions": [
    {
      "name": "ability_gap",
      "assessment": "需要补充团队项目实践",
      "basis": "inferred",
      "evidence_ids": ["ev_demo"],
      "uncertainties": ["今年题型未知"]
    }
  ],
  "evidence": [
    {
      "id": "ev_demo",
      "url": "https://example.com/notice",
      "excerpt": "往届任务要求团队完成项目。",
      "fetched_at": "2026-10-15T12:00:00+08:00",
      "applicable_year": 2025,
      "scope": "往届校内选拔"
    }
  ]
}
```

- 报名状态：`open | upcoming | closed | unknown`；资格：`eligible | ineligible | unknown`；依据：`explicit | inferred | unknown`。
- `scope` 是来源适用范围，不是随意匹配的关键词。本届明确事实要求 `applicable_year` 等于实例年度、`fetched_at` 不晚于当前时钟，且 scope 为严格的 `applies-to/v1:{"stage":"校内选拔","group":"本科组"}` 字符串（两个键都必须提供，无额外键/重复键，值精确匹配实例；`group:null` 仅匹配无组别实例，不是通配符）。上述卡片例子的自由文本 scope/往届材料只可作带 uncertainties 的 inferred 背景，不能当本届日期或资格依据。
- `dimensions` 在 R1 可为空，在 R2 的 `name` 使用 `ability_gap | goal_value | time_cost | preparation_risk | team_requirement | schedule_conflict`，分别表示能力差距、目标价值、投入、准备风险、组队需求与赛程冲突；不强制单一总分，不提供无依据获奖概率。
- `GET /competitions/{id}` 返回 `competition_instance_id`、`name`、`series_id`、`year`、`group`、`stage`、`eligibility_description`、`registration_status`、`registration_start`、`registration_deadline`、`competition_date`、`evidence`；未知字段为 `null`，其中竞赛 `stage` 是比赛阶段文本，不是会话的 R0/R1。证据只返回该用户可访问的内容，不附带云浏览器接管链接。
- `plan` 在 R4 为对象，字段为 `selected_competition_ids`、`tasks`、`weekly_load`、`conflicts`、`assumptions`、`feasibility`。`feasibility` 为 `feasible | infeasible | unknown`；后两种必须明确提示原因，不能当作可执行方案确认。
- 每个任务包含 `id`、`competition_instance_id`、`title`、`estimated_hours`、`acceptance_criteria`、`start_date`、`due_date`；每周负载包含 `week_start`、`estimated_hours`、`budget_hours`。投入以小时计，任务投入已知时须大于 0，`week_start` 固定为周一日期；`conflicts` 与 `assumptions` 均为说明字符串数组。未知投入或日期为 `null`，不以 0 代替。
- 前端把模型文案作为文本或经过清洗的 Markdown 渲染，禁用原始 HTML；来源链接仅允许 HTTP(S)。日期、资格、提示色和按钮状态从结构化字段读取。

## 5. 并发、错误和重试

所有会话修改请求都携带最新 `expected_revision`；同会话只允许一个修改请求执行中。版本不一致返回 `409 REVISION_CONFLICT`，前端 GET 最新快照再决定是否重发，不能静默覆盖。

chat 使用前端生成的唯一 `request_id`：相同 ID、相同请求体在成功提交后重发，返回缓存的原结果，不再次调用模型；相同 ID、不同请求体返回 `409 REQUEST_ID_REUSED`。先检查已提交的请求 ID，再检查 `expected_revision`，避免重放被自己的旧版本号拒绝。执行中的重复请求返回 `409 REQUEST_IN_PROGRESS`。成功结果和请求 ID 一起保存到私有会话文件；不承诺进程崩溃前尚未提交的模型调用恰好执行一次。回放结果的 revision 可能较旧，前端不能用它覆盖更新的状态。

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "会话已更新，请刷新后重试。",
    "retryable": false,
    "details": {
      "current_revision": 4
    }
  },
  "request_id": "req_demo_001"
}
```

| HTTP | 错误码 | 前端行为 |
|---|---|---|
| 404 | `SESSION_NOT_FOUND` / `COMPETITION_NOT_FOUND` | 提示资源不存在或不可访问 |
| 409 | `REVISION_CONFLICT` / `INVALID_STAGE` / `REQUEST_IN_PROGRESS` / `REQUEST_ID_REUSED` | 按原因刷新或等待，不自动重生成 |
| 422 | `VALIDATION_ERROR` | 显示字段错误；后端需统一 FastAPI 默认校验响应 |
| 429 | `RATE_LIMITED` | 显示稍后再试，遵循存在的 `Retry-After` |
| 502 | `LLM_INVALID_OUTPUT` / `UPSTREAM_ERROR` | 保留上次有效结果，提示失败 |
| 503 | `LLM_NOT_CONFIGURED` / `CATALOG_NOT_CONFIGURED` | 提示模型或竞赛资料尚未配置，前端不收集密钥 |
| 503 | `CATALOG_INVALID` | 竞赛文件损坏/内容无效，不当作空列表 |
| 504 | `UPSTREAM_TIMEOUT` | 先 GET 确认状态，不直接重复付费调用 |
| 500 | `INTERNAL_ERROR` | 显示通用错误及 request ID，不展示原始异常 |
| 501 | `FEATURE_NOT_ENABLED` | 日历尚未启用，不显示下载入口 |

`retryable=true` 只表示用户可以在等待并核实状态后重试，不代表前端可以立即自动重发 POST。失败不提交半份画像、卡片或路线；补全缺失但仍可用的结果用结构化未知项表达。

损坏会话或存储失败返回 `500 INTERNAL_ERROR`，不会覆盖损坏文件；`CONFIG_INVALID` 在配置读取/factory 阶段拒绝启动，不是缺目录的 503。注入无时区后端时钟属于部署错误 `500 CLOCK_INVALID`。错误包的 `request_id` 当前允许为 `null`，不要将其视作一定存在的追踪值。

本机 JSON 存储仅支持单进程，拒绝已存在的会话目录/文件符号链接；不保证抵御恶意本地进程并发换链。data 边界及其上级目录须受部署者保护，不是通用文件系统沙箱。

建议总请求预算 120 秒、前端和反向代理等待至少 150 秒，具体通过实测调整。前端断开连接不代表云会话或模型请求已取消；先 GET 查看 `processing`、`last_request_id` 和 revision，再恢复交互。

## 6. 联调验收

先用本文虚构数据做前端 mock：创建会话、问答、生成、确认、修改、恢复候选、刷新恢复和错误提示。重点验证旧版本确认被拒绝、双击不重复调用、未知不显示为符合、画像修改清除旧结果，以及来源文案不执行 HTML。

FastAPI `/openapi.json` 为字段契约；`backend/tests/test_api_flow.py` 使用 tmp_path 虚构目录、ScriptedAgent 和真实 service/store/rules 覆盖完整流程、版本、重放、失败原子性及越权草案，非真实模型验收。模型返回值不能直接成为 HTTP 响应。无需为此新增契约平台或独立服务。
