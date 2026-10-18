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

## 本地 Python 后端

> AI 辅助整理，2026-10-18。R0 → R1 → R2 → R4 的 HTTP 模拟闭环已通过离线测试，Task 1–5 已通过分任务独立审查，整体验收审查待完成；**没有验证真实 DeepSeek 调用、Python Lexmount SDK 或 MIS 端到端采集**。

单进程 FastAPI、一个 LiteLLM Agent、本地 JSON，无数据库、队列或模型 Proxy。现有 Node 采集工具保留；Python 后端尚未接入在线补全、MIS 登录、R3、流式输出或日历导出。

从仓库根目录运行（Python ≥ 3.10；当前验证环境为 Python 3.14）：

```bash
python3 -m venv "$HOME/.venvs/bjtu-competition-advisor"
source "$HOME/.venvs/bjtu-competition-advisor/bin/activate"
python -m pip install -e '.[dev]'
python -m pip check
python -m pytest
python -m ruff check backend
python -m ruff format --check backend
```

### 配置与启动

默认 `backend.main:app` **只读环境变量，不自动读取 YAML 或 `.env`**；导入不读取竞赛/会话内容、不创建数据目录。目录在首次查询时加载，会话在首次写入时创建目录。

| 环境变量 | 默认 / 含义 |
|---|---|
| `DEEPSEEK_API_KEY` | 未配置；只在 chat 调用时要求，绝不回退假模型 |
| `LLM_MODEL` | `deepseek/deepseek-chat` |
| `LLM_TIMEOUT_SECONDS` | 每次最多 30 秒，整请求最多 120 秒 |
| `LLM_MAX_OUTPUT_TOKENS` | 4096，上限也是 4096 |
| `BJTU_DATA_DIR` | 仓库 `data/`，会话写到其 `sessions/` 子目录 |
| `BJTU_CATALOG_PATH` | 仓库 `data/competitions.json`，不会自动使用 demo |
| `BJTU_ALLOWED_ORIGINS` | 空；逗号分隔的完整前端 origin，无路径，不允许 `*` |

两个路径分别配置，相对路径相对仓库根目录解析，不随进程 cwd 改变。改变 data 目录不会自动改 catalog 路径。

**显式使用虚构 demo 数据**（三个 AI 辅助生成的虚构竞赛，`example.com` 不是实测竞赛来源，日期会随当前时钟过期）：

```bash
export BJTU_DATA_DIR=data/local-demo
export BJTU_CATALOG_PATH=backend/examples/competitions.json
export BJTU_ALLOWED_ORIGINS=http://localhost:5173
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

无 key 时可创建、读取、编辑会话以及查询竞赛；chat 返回 `503 LLM_NOT_CONFIGURED`。需要真实模型时，先明确费用授权，再通过进程管理器/安全环境注入 `DEEPSEEK_API_KEY`，重启服务；不要把 key 写进命令历史、聊天或文档。模型能力仍需用虚构画像单独联网验收，安装成功不等于 provider 支持工具/JSON 参数。

如确需私有 YAML，使用自己的启动模块显式调用 `Settings.from_sources(os.environ, Path("lexmount-config.yaml"))`，再交给 `create_app(settings)`；环境优先。可读键为 `deepseek-api-key`、`llm-model`、`llm-timeout-seconds`、`llm-max-output-tokens`、`bjtu-data-dir`、`bjtu-catalog-path`、`bjtu-allowed-origins`，其他 Lexmount/MIS 凭据不会保留到 Settings。不要修改或提交真实配置。

### 接口与边界

```bash
curl -X POST http://127.0.0.1:8000/api/sessions -H 'Content-Type: application/json' -d '{}'
curl http://127.0.0.1:8000/api/competitions/fictional_2026_open
```

- OpenAPI：`http://127.0.0.1:8000/openapi.json`；交互文档：`/docs`。画像、候选 PATCH、chat、confirm 的字段见[前后端契约](docs/frontend-contract.md)。确认只确认当前 revision，不调用模型；无预算可筛选，但不能最终确认未知可行性路线。日历返回 `501 FEATURE_NOT_ENABLED`。
- 缺竞赛文件：`503 CATALOG_NOT_CONFIGURED`；损坏目录：`503 CATALOG_INVALID`；损坏会话/写盘失败：`500 INTERNAL_ERROR`，不覆盖损坏文件。配置无效在 factory/显式读取时以 `CONFIG_INVALID` 拒绝启动，不伪装为缺目录。
- 仅运行一个 worker。真实资料和会话放忽略的 `data/`，限制访问并备份。存储拒绝已存在的会话目录/文件符号链接，但**不是针对恶意本地进程并发换链的文件系统沙箱**；受信任的 data 边界及上级目录应由部署者保护。
- 默认仅本机访问；开放网络前必须实现鉴权和会话归属校验。CORS 不等于鉴权；预检协议拒绝可能是纯文本，不保证业务 JSON 错误包。
- 测试使用 tmp_path 虚构目录和注入 Agent，不读取真实配置或私有资料，也不请求模型/云；默认 app 仍连接真实、provider 懒加载的 LiteLLMAgent。详细预算、证据规则和限制见 [LLM 对接](docs/llm-integration.md)。

## 文档地图

| 文件 | 内容 |
|---|---|
| `docs/handoff.md` | **当前进度、待办、待决事项（交接从这里开始）** |
| `docs/plan.md` | 项目方案、最新轻量 Python 后端设计及保留的历史方案 |
| `docs/frontend-contract.md` | 前后端接口、数据结构、确认与错误处理契约 |
| `docs/llm-integration.md` | 已实现的 LiteLLM 配置、工具、草案校验及联网待验事项 |
| `docs/superpowers/plans/2026-10-18-backend-mvp.md` | 已批准的本地后端实现顺序、接口和测试计划 |
| `issue.md` | 未解决的问题 |
| `docs/project-brief.md` / `docs/project-overview.html` | 给评委看的项目简介（HTML 未审核） |
| `教务系统/login-and-competition-guide.md` | MIS 登录路径、竞赛列表与详情页结构 |
| `lexmount-real-task-challenge.md` | 比赛规则、资源、API 调研汇总 |
| `real-task-challenge-product-options.md` | 早期四个选题方案的分析（已被现方案取代） |
| `AGENTS.md` | AI 编码助手（Claude Code / opencode）的项目约定 |

## 代码

- `backend/main.py`：FastAPI app factory 和 HTTP 入口
- `backend/service.py`：版本、重放、用户确认与原子事务；`backend/agent.py`：有界 LiteLLM 工具循环
- `backend/catalog.py`、`backend/tools.py`：本地目录、证据、资格与路线规则
- `pyproject.toml`：Python 包及锁定的运行/测试依赖
- `lib/lexmount.mjs`：读取配置、管理云会话和本地隧道的生命周期
- `scripts/smoke-test.mjs`：云浏览器冒烟测试
- `collect/mis.mjs`：MIS 竞赛列表采集（未端到端跑通）
