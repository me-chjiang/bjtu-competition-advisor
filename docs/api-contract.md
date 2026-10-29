# 前后端 HTTP 接口契约（草案）

> AI 辅助生成（Claude Code），基于 `docs/plan.md` §5、§7 起草，2026-10-15。
> - MIS 部分由 `backend/` 实现。
> - Agent 部分（`/sessions`、`/competitions`）待用户确认后按此实现；前端 mock（`frontend/src/api/mock/`）是它的参考实现。
> - TS 类型见 `frontend/src/api/types.ts`。三份内容必须保持同步。

## 待调整（第二轮，2026-10-16）

以下改动等 `REQUIREMENTS.md`「第二轮」拍板后再写进正文：

- `category` 增加 `S`（MIS 实测有 5 条 S 类）；
- `ranks` 改为后端代码根据档位和画像目标计算，不由模型给出；
- 新增 `/research/*`（调研任务、进度、过程截图）和 `/directions/*`（方向行情报告）；
- 卡片维度改为行情维度（基本信息、时间线、要求、行情、经验、风险），依据类型增加「经验帖」。

## 通用

- JSON 编码，UTF-8；时间用 ISO 8601，日期用 `YYYY-MM-DD`。
- 后端只监听 `127.0.0.1`；前端经 Vite 代理访问，路径不加前缀。
- 失败时统一返回 HTTP 4xx/5xx 加以下结构：

  ```json
  { "code": "SESSION_NOT_FOUND", "message": "会话不存在或已过期" }
  ```

- `message` 给用户看，不能包含凭据、`connectUrl`/`inspectUrl` 或底层堆栈。

| code | HTTP | 含义 |
|---|---|---|
| `VALIDATION_ERROR` | 422 | 请求体不合法（不回显请求内容） |
| `LOGIN_NOT_FOUND` | 404 | login_id 不存在或已超时关闭 |
| `NOT_LOGGED_IN` | 409 | 持久化 context 未登录，无法采集 |
| `CRAWL_RUNNING` | 409 | 采集正在进行 |
| `UPSTREAM_ERROR` | 502 | Lexmount 或 MIS 访问失败 |
| `SESSION_NOT_FOUND` | 404 | 推荐会话不存在 |
| `STAGE_MISMATCH` | 409 | 确认的阶段不是当前阶段（重复点击或已过期） |
| `SESSION_BUSY` | 409 | 同一会话已有请求在处理 |
| `CANDIDATE_NOT_FOUND` | 404 | 候选不存在 |
| `CANDIDATE_LOCKED` | 409 | 候选因明确冲突被硬性排除，不能恢复 |
| `COMPETITION_NOT_FOUND` | 404 | 竞赛不存在 |
| `INTERNAL_ERROR` | 500 | 未预期的服务器错误（不含细节） |
| `MODEL_ERROR` | 502 | 模型调用失败或超时 |
| `OUTPUT_INVALID` | 502 | 模型输出多次修复后仍不合法 |

## MIS 登录与采集

### `GET /mis/status`

只读取本地信息，不创建云会话。

```json
{ "has_context": true, "crawl": CrawlStatus }
```

### `POST /mis/login` → `LoginStep`

- 创建云会话。复用持久化 context，模式为 readWrite，**不录制**。
- context 仍处于登录状态时，直接返回 `already_logged_in` 并关闭会话。
- CAS 登录态仍有效、只是教务系统会话过期时，后端直接完成单点登录，返回 `success`。
- 同一时间只保留一个登录流程：新的 `POST /mis/login` 会关闭之前未完成的流程。会话闲置 180 秒后自动关闭。

### `POST /mis/login/{login_id}/submit` → `LoginStep`

```json
{ "values": { "loginname": "…", "password": "…", "captcha_1": "56" } }
```

- 键名来自 `fields[].name`，前端不写死。
- 登录失败时，返回带 `error` 的新表单和新验证码。后端**不自动重试**。
- 次数用完后返回 `failed`，并关闭会话。

### `POST /mis/login/{login_id}/captcha` → `LoginStep`

用 GET 重新打开 CAS 登录页（不用浏览器刷新，避免重发上一次的 POST），返回新的表单和验证码，不计入尝试次数。

### `DELETE /mis/login/{login_id}` → 204

### `LoginStep`

```jsonc
{ "state": "already_logged_in" }
{ "state": "success" }
{ "state": "failed", "error": "尝试次数已用完，请稍后再试" }
{
  "state": "form",
  "login_id": "b1f…",
  "fields": [ { "name": "loginname", "label": "用户名", "kind": "text" },
              { "name": "password", "label": "密码", "kind": "password" },
              { "name": "captcha_1", "label": "验证码", "kind": "captcha" } ],
  "captcha": "data:image/png;base64,…",   // 可能为 null
  "error": null,                          // CAS 页面上的原文错误
  "attempts_left": 3
}
```

### `POST /mis/crawl` → 202 `CrawlStatus`；`GET /mis/crawl` → `CrawlStatus`

后台依次采集两个列表：`/innovation/cpitem/` 和 `/innovation/cpitem_round/signup/`，写入 `data/mis/`。
- 采集会话**开录制**。
- 每页之间间隔 2 秒；遇到空页、短页或页面内容重复时停止翻页。
- 不保存「负责人」列和「报名」链接。
- 采集中途发现登录失效时，`state` 为 `error`，`error` 字段提示用户重新登录。

```jsonc
{
  "state": "idle" | "running" | "done" | "error",
  "step": "竞赛项目列表 第 1 页",      // 运行中的进度说明，可为 null
  "counts": { "cpitem": 712, "signup_rounds": 43 },  // 可为 null
  "finished_at": "2026-10-15T12:00:00+08:00",       // 可为 null
  "error": null
}
```

## Agent 会话

### 类型

```jsonc
// Stage：R0 画像 → R1 粗筛 → R2 精查 → R4 路线
"profile" | "screen" | "review" | "route" | "done"

// Message
{ "id": "m1", "role": "user" | "assistant", "content": "…", "created_at": "…" }

// Profile
{
  "grade": "大二" | null, "major": "计算机科学与技术" | null,
  "discipline": "工学" | null,           // 学科大类（issue #4）
  "skills": [ { "name": "Python", "level": "basic" | "proficient" | "expert", "evidence": "课程项目…" } ],
  "weekly_hours": 8 | null,
  "goals": ["保研", "简历"],
  "team_preference": "individual" | "team" | "either" | null,
  "domains": ["算法", "数学建模"],
  "notes": null,
  "version": 2,              // 每次修改 +1
  "confirmed": false
}

// Card：按 kind 区分
// R1 候选
{
  "kind": "candidate", "id": "cand-1", "competition_id": "c-icpc-2026",
  "name": "…", "domain": "算法编程", "reason": "一句入选理由",
  "level": "国家级" | null, "category": "A" | "B" | "C" | null,
  "registration": "open" | "not_open" | "closed" | "unknown",
  "status": "kept" | "excluded" | "hidden",   // hidden = 因数量或相关性暂不展示，可恢复
  "exclusion": null | { "type": "hard" | "user", "reason": "…", "evidence_ids": ["e1"] },
  "stale": false
}
// R2 证据卡片
{
  "kind": "scorecard", "id": "sc-1", "competition_id": "…", "name": "…",
  "summary": "…",
  "dimensions": [ {
    "key": "gap" | "value" | "time_cost" | "difficulty" | "schedule" | "team",
    "label": "能力差距", "tier": "high" | "medium" | "low" | "unknown",
    "summary": "…",
    "basis": "official" | "inferred" | "insufficient",
    "confidence": "high" | "medium" | "low",
    "evidence_ids": ["e1"]
  } ],
  "ranks": { "goal": 1, "time": 3, "risk": 2 },   // 1 为最优，前端据此切换排序
  "stale": false
}
// R4 路线：每个会话最多一张
{
  "kind": "route", "id": "route",
  "items": [ { "competition_id": "…", "name": "…", "tasks": [ {
    "title": "刷 50 道图论题", "hours_per_week": 4,
    "acceptance": "Codeforces 1600 以上题目独立 AC 率 ≥ 60%",
    "start": "2026-10-20" | null, "end": "2026-11-30" | null,
    "date_certainty": "confirmed" | "estimated" | "unknown",
    "assumptions": ["报名时间沿用往年，待核实"]
  } ] } ],
  "weekly_hours_total": 10, "weekly_hours_available": 8,
  "conflicts": [ { "description": "…", "competition_ids": ["…"] } ],
  "pending_checks": ["…"],
  "stale": false
}

// Session
{
  "id": "s-…", "stage": "profile", "messages": [Message],
  "profile": Profile, "cards": [Card], "needs_confirmation": false
}

// ChatResponse
{ "message": Message, "stage": Stage, "profile": Profile, "cards": [Card], "needs_confirmation": true }
```

- `cards` 总是返回当前会话的**全量**卡片，前端直接整体替换，不做增量合并。
- `stale: true` 表示画像修改后，这张卡片待更新。

### 接口

| 接口 | 请求 | 响应 |
|---|---|---|
| `POST /sessions` | `{}` | 201 `Session`（首条 assistant 欢迎消息） |
| `GET /sessions/{id}` | — | `Session` |
| `POST /sessions/{id}/chat` | `{ "content": "…" }` | `ChatResponse` |
| `PATCH /sessions/{id}/profile` | `Profile` 的部分字段 | `{ "profile": Profile, "cards": [Card] }`（受影响的卡片标 `stale`） |
| `POST /sessions/{id}/confirm` | `{ "stage": Stage, "selected_competition_ids"?: [id] }` | `ChatResponse`（推进到下一阶段） |
| `PATCH /sessions/{id}/candidates/{candidate_id}` | `{ "status": "kept" \| "excluded" }` | `{ "card": Card }` |
| `GET /competitions/{id}` | — | `Competition` |

- `confirm` 的 `stage` 是前端看到的当前阶段，用于防止重复确认。
- `stage = review` 时，`confirm` 必须带 `selected_competition_ids`（Top-N 中勾选的竞赛），后端只针对这些竞赛生成路线。
- `exclusion.type = hard` 的候选不能恢复。`kept`/`excluded` 之间可以随时切换，`hidden` 可以改为 `kept`。

```jsonc
// Competition
{
  "id": "c-…", "series": "…", "name": "…", "year": "2026",
  "level": "国家级" | null, "category": "A" | null, "organizer": "…" | null,
  "format": "组队 / 线下" | null,
  "registration": { "status": "open", "start": "2026-10-01" | null, "end": "2026-10-31" | null },
  "description": "…" | null,
  "evidence": [ {
    "id": "e1", "excerpt": "…", "url": "https://…", "fetched_at": "…",
    "applies_to_year": "2026" | null, "applies_to_group": "本科组" | null,
    "source_type": "mis" | "official_site" | "notice" | "other",
    "session_id": "…" | null
  } ]
}
```
