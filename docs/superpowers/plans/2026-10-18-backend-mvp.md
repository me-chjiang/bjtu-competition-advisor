# 轻量 Python 后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可本机启动、可用虚构数据离线测试的 R0 → R1 → R2 → R4 后端，并提供真实 LiteLLM 对接路径。

**Architecture:** 一个 FastAPI 进程通过 LiteLLM 运行一个 Agent；规则、状态修改和保存由 Python 控制。竞赛与会话使用本地 JSON，无数据库、队列、后台 Worker 或模型网关。默认模型未配置时明确报错，绝不静默生成伪推荐。

**Tech Stack:** Python ≥ 3.10，FastAPI，Pydantic 2，LiteLLM，Uvicorn，PyYAML；测试使用 pytest、pytest-asyncio、HTTPX，静态检查使用 Ruff。

**Spec:** [前后端契约](../../frontend-contract.md)、[LLM 对接](../../llm-integration.md)、[项目方案：最新后端部分](../../plan.md#后端方案2026-10-15-合并)。用户于 2026-10-18 确认计划，并选择子代理实施、独立审查和隔离 worktree；随后明确要求每个任务审查通过后立即提交，包括补提交先前任务，不自动推送。

## Global Constraints

- API base URL：`http://127.0.0.1:8000/api`；字段为 `snake_case`，成功响应不套 `data`。
- 单进程、单 Agent、本地 JSON；不引入 PostgreSQL、Redis、独立 Worker、任务队列或 LiteLLM Proxy。
- Python ≥ 3.10；不能使用只在 Python 3.11+ 存在的运行时接口。
- 首版普通 HTTP 请求响应；不实现 MIS 登录、在线采集/补全、R3、流式输出、日历导出或公网用户系统。
- `weekly_hours` 为正数或 `null`，非必填；新增 `additional_context`，默认 `null`、最多 2000 字符，纯空白归一化为 `null`。
- 总请求预算 120 秒，最多 5 次模型请求、8 次工具执行；每次模型请求建议 30 秒，输出上限 4096 token；`num_retries=0`。
- 模型、格式修复和应用重试共同消耗上述预算；测试不读取私有配置、不请求模型、不创建云会话。
- 所有真实资料和会话位于被忽略的 `data/`；仓库内只有明确标记的虚构 fixtures。
- 不打印 key、账号、Cookie、接管 URL、完整提示词或用户资料；保留已有 Node 脚本和未跟踪的 `.agents/`。
- 各任务结束检查差异，由控制者在独立审查通过后提交；先前已通过任务亦按各自已审查快照补提交。不自动推送。

## Review Focus

1. PATCH 中的“未提供”与 `null` 不同，补充文本不能覆盖用户已确认信息：Task 1/4 测试。
2. 成功请求重放必须先查请求 ID、后查旧 revision，重启后也不再次调用模型：Task 2/5 测试。
3. 模型失败、取消或写盘失败不能提交半份结果，也不能让会话永久处于 processing：Task 2/4 测试。
4. 往年通知、未知报名时间不能被当成本届事实，未知时间预算不能标记可行：Task 3/5 测试。
5. 恶意会话 ID、模型伪造字段/引用和上游异常不能读取私有文件或泄露凭据：Task 1/2/4/5 测试。

---

## 文件与职责

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | Python 包、依赖范围、测试和 Ruff 配置 |
| `backend/__init__.py` | Python 包入口 |
| `backend/config.py` | 显式读取配置和目录；密钥不出现在 repr |
| `backend/schemas.py` | HTTP DTO、内部记录、模型草案及受控异常 |
| `backend/storage.py` | 原子 JSON 写入、每会话锁、请求去重记录 |
| `backend/catalog.py` | 竞赛实例、证据索引和纯规则计算 |
| `backend/tools.py` | 阶段工具白名单与参数校验 |
| `backend/agent.py` | LiteLLM 调用、上下文、工具循环和预算 |
| `backend/service.py` | 状态推进、草案校验和单次事务提交 |
| `backend/main.py` | app factory、路由、异常响应和 CORS |
| `backend/examples/competitions.json` | 三个明确标注的虚构实例，必须显式配置后才使用 |
| `backend/tests/` | schemas/config、storage、catalog、agent、API 测试 |

不新增 `collector.py` 的空实现，不修改现有采集逻辑。为避免路由和工具循环混在一个大文件，增加 `service.py` 与 `catalog.py`，不继续拆多层抽象。

### 配置和内部数据决定

- `Settings.from_sources(environ: Mapping[str, str], config_path: Path | None) -> Settings`：环境优先。模型 key 用 `DEEPSEEK_API_KEY`，可回退到现有私有 YAML 中拟新增的 `deepseek-api-key`；新增模板空键，不编辑真实配置。模型用 `LLM_MODEL`，默认 `deepseek/deepseek-chat`，可回退 YAML 的 `llm-model`。
- `LLM_TIMEOUT_SECONDS`、`LLM_MAX_OUTPUT_TOKENS` 沿用 LLM 文档；新增 `BJTU_DATA_DIR` 默认仓库 `data/`，`BJTU_CATALOG_PATH` 默认 `data/competitions.json`，`BJTU_ALLOWED_ORIGINS` 默认空的逗号分隔列表。相对路径以仓库根解析，与进程工作目录无关。
- 缺模型 key 不阻止创建/读取会话，只有 chat 调用模型时返回 `503 LLM_NOT_CONFIGURED`。缺竞赛文件不自动加载 demo；需要竞赛资料的操作返回 `503 CATALOG_NOT_CONFIGURED`。损坏文件返回受控错误，不能伪装成空目录。
- `SessionRecord` 保存公开快照、已确认画像、粗筛卡片及成功请求缓存；公开 DTO 不暴露这些内部字段。processing 由内存锁派生，不把 true 持久化。
- `AgentRunner` 是可注入的 Python Protocol：`async run(snapshot: SessionSnapshot, request: ChatRequest) -> AgentDraft`。`AgentDraft` 字段固定为 `kind`（question/profile/candidates/analysis/plan）、`message: str`、`profile_changes: ProfileChanges | None`、`candidates: list[CandidateReason]`、`analyses: list[AnalysisDraft]`、`plan: PlanDraft | None`；可选对象默认 null，数组默认空。
- `CandidateReason` 为 `competition_instance_id: str`、`reason: str`；`AnalysisDraft` 为 `competition_instance_id: str`、契约规定的 `dimensions`。`PlanDraft` 仅接收 `selected_competition_ids`、`tasks`、`assumptions`，`Plan` 在此基础上增加后端计算的 `weekly_load`、`conflicts`、`feasibility`。模型不得直接填写这些规则结果。DTO 在 Task 1 统一定义，后续任务不另造同名类型。
- 内部竞赛记录以 `competition_instance_id`、`series_id`、`year`、`group`、`stage` 关联；明确资格约束为 `allowed_grades`、`allowed_majors`（数组或 null）及其 `eligibility_evidence_ids`。所有 HTTP 字段沿用前端契约，原始规则字段不暴露给前端修改。
- `additional_context` 的冲突不靠模型猜测解决：模型只能返回核对问题，结构化修改需明确用户依据；不新增自由 JSON 字段。

## Task 1: 类型、配置与开发环境

**Files:** Create `pyproject.toml`、`backend/__init__.py`、`backend/config.py`、`backend/schemas.py`、`backend/tests/test_schemas_config.py`；Modify `.gitignore`、`lexmount-config.example.yaml`。

**Interfaces:** 产生 `Settings`、`Profile`、`ProfileChanges`、全部请求/响应 DTO、`SessionRecord`、`AgentDraft`、`AgentRunner`，以及 `AppError(code, message, status_code, retryable=False, details=None)`。DTO 字段以契约为准，`extra="forbid"`；内部草案不能携带 revision、权限或确认动作。

- [ ] **Step 0 — 准备测试环境。** 在仓库外建立并激活 Python ≥ 3.10 的 venv，安装 pytest、pytest-asyncio，运行 `python -m pytest --version` 确认测试运行器可用；不读取私有凭据。Step 3 创建 pyproject 后再安装 `python -m pip install -e '.[dev]'`。
- [ ] **Step 1 — 写失败测试。** `test_profile_defaults_and_patch` 断言 `Profile().weekly_hours is None`、`additional_context is None`；PATCH 省略字段不改变原值，显式 null 清空，数组整体替换。参数化检查补充文本 2000 字符接受、2001 拒绝、空白归 null，以及 hours 为 0、负数、NaN、Infinity 和布尔值拒绝。

  ```python
  assert Profile().weekly_hours is None
  assert Profile().additional_context is None
  assert Profile(additional_context="  ").additional_context is None
  assert ProfileChanges().model_dump(exclude_unset=True) == {}
  assert ProfileChanges(weekly_hours=None).model_dump(exclude_unset=True) == {"weekly_hours": None}
  ```

- [ ] **Step 2 — 验证红灯。** `python -m pytest backend/tests/test_schemas_config.py -q`；预期因模块不存在而失败，不接受环境配置错误冒充红灯。
- [ ] **Step 3 — 实现接口与环境。** pyproject 声明 Python ≥ 3.10、运行依赖 FastAPI/Pydantic 2/LiteLLM/Uvicorn/PyYAML，dev extra 为 pytest/pytest-asyncio/httpx/ruff；测试通过后锁定兼容版本，不声称最低版本已在本机全部验证。忽略 `.venv/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`*.egg-info/`；模板仅增加空模型 key 和非敏感默认模型。
- [ ] **Step 4 — 补配置测试并跑绿灯。** `test_env_overrides_yaml`、`test_secret_repr_is_redacted`、`test_invalid_limits_fail_safely` 使用 tmp_path 和虚构 key，绝不读根目录真实 YAML；同上命令预期全部 PASS。
- [ ] **Step 5 — 检查点。** 检查 DTO 覆盖会话、画像、卡片、证据、路线、错误及模型草案，运行 `git diff --check`；确认未引入业务 API 或云服务调用。

## Task 2: 可恢复会话与基础 API

**Files:** Create `backend/storage.py`、`backend/service.py`、`backend/main.py`、`backend/tests/test_storage.py`、`backend/tests/test_api_sessions.py`。

**Interfaces:** 消费 Task 1 的 DTO。产生 `SessionStore(root: Path)` 的 `create() -> SessionRecord`、`load(session_id: str) -> SessionRecord`、`save(record: SessionRecord) -> None`、`guard(session_id: str) -> AsyncContextManager[None]`、`is_processing(session_id: str) -> bool`；初始 `SessionService(store: SessionStore, agent: AgentRunner | None = None)`；`create_app(settings: Settings | None = None, agent: AgentRunner | None = None) -> FastAPI`。Task 3 增加 catalog 依赖，在此之前不得导入尚不存在的模块。

- [ ] **Step 1 — 写失败测试。** `test_create_and_reload_session` 断言 POST `/api/sessions` 为 201、R0/revision 0/profile 默认值正确；重建 app 后 GET 返回同一会话。`test_profile_patch_invalidates_results` 断言修改后 revision 加 1、R0/collecting、cards 空、plan null。

  ```python
  assert created_response.status_code == 201
  assert created_response.json()["stage"] == "R0"
  assert created_response.json()["revision"] == 0
  assert reloaded_response.json() == created_response.json()
  assert patched_response.json()["cards"] == []
  assert patched_response.json()["plan"] is None
  ```

- [ ] **Step 2 — 验证红灯。** `python -m pytest backend/tests/test_storage.py backend/tests/test_api_sessions.py -q`；预期缺少 store/app 实现导致失败。
- [ ] **Step 3 — 实现存储与基础路由。** ID 使用 UUID hex，仅允许服务端生成的安全格式；文件路径不接受任意字符串拼接。目录/会话文件分别使用 0700/0600；在同目录写临时文件后 `os.replace`，失败只清理本次临时文件。实现 create/get/profile PATCH，所有修改在每会话非等待锁内检查 revision，GET 不持锁。
- [ ] **Step 4 — 验证安全和原子性。** `test_session_id_cannot_escape_root`、`test_corrupt_session_is_not_replaced`、`test_replace_failure_preserves_previous_file`、`test_busy_session_is_readable`、`test_cancelled_guard_is_released`、`test_validation_error_does_not_echo_secret`、`test_cors_defaults_closed`；覆盖同会话锁冲突返回 409、异常/取消后锁释放、重启 processing 为 false。运行上述测试与 Task 1，预期全部 PASS。
- [ ] **Step 5 — 检查点。** 请求错误统一成契约 envelope；FastAPI 校验错误不回显原始 input；响应不包含内部缓存、key 或 traceback。基础 API 可在没有 LLM key 时使用。

## Task 3: 虚构竞赛、确定性规则与只读工具

**Files:** Create `backend/catalog.py`、`backend/tools.py`、`backend/examples/competitions.json`、`backend/tests/test_catalog_tools.py`；Modify `backend/service.py`、`backend/main.py` 以接入 catalog，不改变已有会话接口。

**Interfaces:** 产生 `CompetitionCatalog(path: Path)` 的 `search(query: str | None = None) -> list[CompetitionInstance]`、`get(instance_id: str) -> CompetitionInstance`、`evidence(ids: list[str]) -> list[Evidence]`；纯函数 `check_eligibility(profile: Profile, instance: CompetitionInstance, now: datetime) -> EligibilityCheck`、`evaluate_plan(profile: Profile, plan: PlanDraft, catalog: CompetitionCatalog, now: datetime) -> Plan`；`ToolRegistry(catalog)` 的 `definitions(stage: str) -> list[dict]`、`execute(name: str, arguments: dict, snapshot: SessionSnapshot) -> ToolResult`。

扩展 `SessionService(store, agent=None, catalog: CompetitionCatalog | None = None, clock: Callable[[], datetime] | None = None)`，默认时钟为带时区 UTC 当前时间；测试传固定时钟。app factory 同步扩展为 `create_app(settings=None, agent=None, clock: Callable[[], datetime] | None = None) -> FastAPI`，把 clock 传入 service，并从 Settings 创建 catalog；缺失/损坏只影响需要目录的操作，不阻止现有会话 API 启动。

- [ ] **Step 1 — 写失败测试。** `test_only_explicit_conflicts_exclude` 覆盖年级明确冲突、专业未知、无规则来源；`test_historical_dates_do_not_become_current_dates` 覆盖往年通知；`test_missing_budget_keeps_plan_unknown` 断言 null 预算不变成 0 或默认 6 小时。

  ```python
  assert unknown_eligibility.status == "unknown"
  assert conflicting_eligibility.status == "ineligible"
  assert plan_without_budget.feasibility == "unknown"
  assert all(week.budget_hours is None for week in plan_without_budget.weekly_load)
  ```

- [ ] **Step 2 — 验证红灯。** `python -m pytest backend/tests/test_catalog_tools.py -q`；预期缺少目录/规则/工具实现导致失败。
- [ ] **Step 3 — 实现目录和规则。** 三条 fixtures 分别为可报名、已截止、时间/资格未知，使用 example.com 虚构来源，测试时钟固定为 2026-10-18 北京时间。不从 title 归一化删除年度/阶段记录；实际状态以带时区的当前时间和适用来源为准。明确截止的实例不可推荐；未知资格不硬排除。
- [ ] **Step 4 — 实现时间检查和白名单。** 只开放 search/get/evidence/eligibility/plan 五类本地只读工具，不提供 supplement 的伪实现。每任务工时均摊到起止日期内、排除 unavailable_dates 后的日期，再按周一汇总；无可用日或超过已知预算为 infeasible，投入/日期/预算缺失为 unknown。任务结束晚于明确比赛日为冲突，不把所有备赛任务强制截在报名日前。
- [ ] **Step 5 — 跑绿灯及检查点。** 增加 `test_unavailable_days_and_overlapping_weekly_load`、`test_closed_registration_cannot_be_kept`、`test_tool_rejects_unknown_names_and_extra_arguments`、`test_catalog_missing_or_corrupt_is_explicit_error`，运行该文件及前两任务测试，预期全部 PASS。确认 fixtures 不会被生产配置静默加载。

## Task 4: LiteLLM Agent 与受控草案

**Files:** Create `backend/agent.py`、`backend/tests/test_agent.py`。

**Interfaces:** 消费 `AgentRunner`、`AgentDraft`、`ToolRegistry`。产生 `LiteLLMAgent(settings: Settings, tools: ToolRegistry, completion: Callable | None = None)` 的 `async run(snapshot: SessionSnapshot, request: ChatRequest) -> AgentDraft`，默认 completion 为 `litellm.acompletion`；测试注入脚本式 async fake，而非通过 HTTP 开放模型参数。

- [ ] **Step 1 — 写失败测试。** `test_tool_round_trip_preserves_call_ids` 脚本化返回工具调用再返回 JSON，断言完整 assistant 消息与每个 tool_call_id 配对回传；`test_model_cannot_write_server_fields` 拒绝 revision/确认字段；`test_context_conflict_requests_review` 保留用户已确认画像，不从补充文本静默覆盖。

  ```python
  assert second_call_messages[-2]["role"] == "assistant"
  assert second_call_messages[-1]["role"] == "tool"
  assert second_call_messages[-1]["tool_call_id"] == "call_demo_1"
  assert snapshot.profile.weekly_hours == original_snapshot.profile.weekly_hours
  ```

- [ ] **Step 2 — 验证红灯。** `python -m pytest backend/tests/test_agent.py -q`；预期 Agent 尚未实现而失败，测试不得需要 API key。
- [ ] **Step 3 — 实现调用循环。** 为每阶段构建提示词，只取最近 12 条可展示消息、当前画像/决策和相关竞赛证据。工具消息只保留本次请求所需链路；JSON/Pydantic 校验后检查 ID、引用适用范围。模型可以提出画像修改，service 在提交时按失效规则处理，只有用户 `/confirm` 推进阶段。
- [ ] **Step 4 — 实现共享预算与异常映射。** 使用 monotonic 截止时间和剩余时间控制 await；格式修复与临时错误重试各最多一次，均计入最多 5 次模型调用；8 次工具执行为整次请求总量。时间耗尽为 `504 UPSTREAM_TIMEOUT`，调用次数耗尽为 `502 LLM_INVALID_OUTPUT`。超预算批次不部分执行工具后继续模型；拒答、空 content、截断和非法引用不保存。num_retries 固定 0，不输出原始异常。
- [ ] **Step 5 — 跑绿灯及检查点。** `test_timeout_does_not_mutate_input_snapshot`、`test_invalid_output_repair_is_bounded`、`test_budget_is_shared_across_rounds`、`test_fake_evidence_and_cross_instance_ids_are_rejected`、`test_upstream_errors_do_not_leak_key`，分别覆盖 504/429/503/502。运行该文件和已有套件，预期全部 PASS，且无网络请求。

## Task 5: 完整接口、离线闭环与启动说明

**Files:** Modify `backend/service.py`、`backend/main.py`、`README.md`、`docs/handoff.md`、`docs/frontend-contract.md`、`docs/llm-integration.md`；Create `backend/tests/test_api_flow.py`。

**Interfaces:** 完成 SessionService 的 `async chat(session_id: str, request: ChatRequest) -> SessionSnapshot`、`async patch_profile(session_id: str, request: ProfilePatchRequest) -> SessionSnapshot`、`async patch_candidate(session_id: str, candidate_id: str, request: CandidatePatchRequest) -> SessionSnapshot`、`async confirm(session_id: str, request: ConfirmRequest) -> SessionSnapshot`。HTTP 路由严格采用前端契约，竞赛 GET 从 catalog 读取，日历固定返回 501。

- [ ] **Step 1 — 写失败测试。** `test_complete_r0_r1_r2_r4_flow` 使用 tmp_path、虚构目录和 FakeAgent，通过 HTTP 完成画像、确认、筛选、保留、精查、路线及最终确认；断言每个 revision、stage、status、needs_confirmation 和字段一致。所有模型响应均由 fake 提供。

  ```python
  assert confirmed_stages == ["R1", "R2", "R4", "R4"]
  assert final_snapshot["status"] == "completed"
  assert final_snapshot["needs_confirmation"] is False
  assert final_snapshot["plan"]["feasibility"] == "feasible"
  assert replay_response.json() == original_chat_response.json()
  assert fake_agent.calls == calls_before_replay
  ```

- [ ] **Step 2 — 验证红灯。** `python -m pytest backend/tests/test_api_flow.py -q`；预期尚未完成的 chat/confirm/candidate 路由失败。
- [ ] **Step 3 — 实现一致的状态提交。** chat 在加锁后先查 request_id 缓存和内容指纹，再查 expected_revision；成功后一次原子写入新状态、消息和缓存。失败不写半结果。R0→R1→R2→R4 每次确认不调用模型，画像变更回 R0，候选变更按契约回 R1。R4 infeasible/unknown 仍可查看草案但不可最终确认。
- [ ] **Step 4 — 验证重试和未知信息。** `test_successful_chat_replay_after_restart_does_not_call_model`、`test_same_request_id_different_payload_conflicts`、`test_stale_confirmation_does_not_advance`、`test_candidate_edit_invalidates_analysis_and_plan`、`test_unknown_budget_does_not_block_r0_but_blocks_feasible_claim`、`test_model_free_endpoints_work_without_key`、`test_failed_or_cancelled_chat_preserves_file_and_releases_guard`。加入日历 501、缺目录 503 和 FastAPI OpenAPI 字段检查，全部预期 PASS。
- [ ] **Step 5 — 更新启动说明。** README 改为真实存在的入口，说明外部 venv、`python -m pip install -e '.[dev]'`、显式 demo 目录配置和 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1`。区分“模拟闭环测试通过”与“尚未执行真实 LLM/SDK 调用”，不宣称 MIS 已跑通；handoff 更新实际状态，不覆盖采集侧待办。
- [ ] **Step 6 — 全量验证与独立审查。** 执行 `python -m pytest backend/tests -q`、`python -m ruff check backend`、`python -m ruff format --check backend`、`git diff --check`，预期全绿。检查 `/openapi.json` 与前端字段，独立审查实际 diff，核实修复后再向用户交付；不自动提交或推送。

## 执行顺序、风险和审核结论

- 顺序执行 Task 1 → 2 → 3 → 4 → 5。Task 3 与会话代码有接口依赖，不为追求并行同时修改共享 schemas/service。
- 主要风险：模型版本支持差异、JSON 文件损坏、未知资料导致方案无法验证。应对分别为注入测试与真实验证分开、原子提交不覆盖损坏文件、保留 unknown 并要求补充信息；不通过增加数据库或多 Agent 掩盖问题。
- 在线 Lexmount、MIS 登录、日历和公网鉴权单独后续规划，避免本轮越界。
- 自审：HTTP/LLM 文档各要求已映射到任务；画像补充、null 语义、失败原子性、重放、未知时效与敏感信息均有命名测试。尚未执行计划中的任何代码、依赖安装或测试。
- 实现方法与审查模型在执行前确认；若使用按价格选型的子代理流程，届时读取当次模型列表与报价，不在本计划虚构模型可用性或费用。
