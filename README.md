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

### Python 环境与 SDK 独立验证（不依赖业务后端）

> AI 辅助整理，2026-10-15 核对官方文档。以下命令供手动执行，本次未安装依赖或调用云服务；仓库目前没有 `backend/`、`requirements.txt` 或 `pyproject.toml`。

SDK 本身要求 Python 3.8+；这里采用官方 quickstart 的固定依赖组合，要求 **Python 3.10+**。虚拟环境放在仓库外（当前忽略规则不包含 `.venv/`）。
来源：[SDK 概览](https://browser.lexmount.cn/docs/python-sdk)、[Python quickstart](https://browser.lexmount.cn/docs/python-sdk/quickstart)。

```bash
python3 --version                         # 确认 >= 3.10
python3 -m venv "$HOME/.venvs/bjtu-competition-advisor"
source "$HOME/.venvs/bjtu-competition-advisor/bin/activate"
python -m pip install lexmount==0.6.1 playwright==1.63.0 python-dotenv
python -m pip check
python -c 'from lexmount import Lexmount; from playwright.sync_api import sync_playwright; print("SDK imports OK")'
```

最后两项只检查依赖和导入，不创建云会话，也不验证认证。这里只用 CDP 连接远程 Chromium，不启动本地浏览器，因此无需为这段验证执行 `playwright install chromium`；连接方式见官方 [quickstart](https://browser.lexmount.cn/docs/python-sdk/quickstart)。

运行联网验证前，将以下 **SDK 官方变量**安全注入当前进程环境，不在命令历史、日志或文档中填入真实值：

| 变量 | 含义 |
|---|---|
| `LEXMOUNT_API_KEY` | 控制台 Settings → API Keys 创建的 API Key |
| `LEXMOUNT_PROJECT_ID` | 同一项目的 Project ID |
| `LEXMOUNT_BASE_URL` | 可省略，默认中国区 `https://api.lexmount.cn`；全球服务为 `https://api.lexmount.com` |

SDK 从构造参数或环境变量读取配置，构造参数优先；区域目录发现是 best effort，不可用时回退到配置的 base URL。不要假设 Python SDK 自动读取本项目的 `lexmount-config.yaml`，也不要假设安装 `python-dotenv` 就会自动加载 `.env`。现有 YAML 读取由 Node 的 `lib/lexmount.mjs` 完成；Python 配置适配尚未实现。
来源：[quickstart：凭证与区域](https://browser.lexmount.cn/docs/python-sdk/quickstart)、[SDK 概览：配置](https://browser.lexmount.cn/docs/python-sdk)。

**可选联网冒烟验证：下面会创建计费云会话，仅在确认凭据和费用后手动执行。** 不访问 MIS、不登录、不保存截图，显式关闭下载存储、持久化回放与自动验证码处理。

```bash
python - <<'PY'
from lexmount import Lexmount
from playwright.sync_api import sync_playwright

try:
    with Lexmount() as client:
        with client.sessions.create(
            browser_mode="normal",
            downloads={"enabled": False},
            recording={"persistent": False},
            enable_captcha=False,
        ) as session:
            print("session:", session.id)
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(session.connect_url)
                try:
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto("https://example.com", wait_until="domcontentloaded")
                    print("title:", page.title())
                finally:
                    browser.close()
except Exception:
    raise SystemExit("验证失败；先检查控制台会话状态，勿直接输出底层异常或盲目重试。") from None
PY
```

期望标题为 `Example Domain`；这只验证 SDK → 云浏览器 → Playwright 链路，不代表业务后端、MIS 采集或模型调用已跑通。嵌套 context manager 负责异常时关闭 session 和 HTTP client；如改为手动管理，必须在 `finally` 中关闭 session。创建超时仍可能已预留 session，重试前先到控制台检查，避免遗留计费实例；不打印或保存 `connect_url` / `inspect_url`。
来源：[quickstart：连接、清理与排查](https://browser.lexmount.cn/docs/python-sdk/quickstart)、[核心能力：会话参数](https://browser.lexmount.cn/docs/python-sdk/capabilities)、[示例：安全清理](https://browser.lexmount.cn/docs/python-sdk/examples)。

官方示例是同步 `Lexmount` + `sync_playwright`；`async_create=True` 表示云端异步创建并轮询到 active，并非 Python `await` 客户端接口。FastAPI 实现时应隔离这些阻塞操作，不直接放进 `async def` 路由的事件循环；本说明不假设未核实的异步 SDK 方法。
来源：[quickstart](https://browser.lexmount.cn/docs/python-sdk/quickstart)、[核心能力：Sessions](https://browser.lexmount.cn/docs/python-sdk/capabilities)。

### 本地开发与单机部署（计划，入口尚不存在）

以下是本项目的实施建议，**不是当前可启动的服务**：

1. 在上述虚拟环境中准备业务依赖：`python -m pip install fastapi uvicorn litellm`。这些是项目选型，不是 Lexmount SDK 的必需依赖；实际兼容版本需测试后锁定到待新增的依赖文件。
2. 按 [`docs/plan.md`](docs/plan.md#后端方案2026-10-15-合并) 实现 `backend/main.py` 等模块、HTTP 契约与 JSON 存储，再验证本地数据闭环。LiteLLM 作为库直接调用，不部署 Proxy；LiteLLM 的 DeepSeek 接入示例使用 `DEEPSEEK_API_KEY` 和模型名 `deepseek/deepseek-chat`，与 Lexmount 认证变量分开。本项目的模型配置适配尚未实现，不能认为现有 YAML 已配置好模型。来源：[LiteLLM DeepSeek 文档](https://docs.litellm.ai/docs/providers/deepseek)。
3. **仅在 `backend/main.py` 已提供 `app` 后**，从仓库根目录运行拟定命令：

   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```

4. 单机用普通用户和进程管理器（如 systemd）托管，固定工作目录与虚拟环境路径，安全注入凭据；只运行一个业务 worker、一个 Agent，同会话串行写 JSON 并采用原子替换。`data/` 保存在持久磁盘，限制访问权限并备份，不随代码发布覆盖，不引入 PostgreSQL、Redis、Docker 或独立 Worker。
5. 默认仅监听回环地址；对外开放前先实现鉴权与会话归属校验，并通过 HTTPS 反向代理接入。前端不持有模型或 Lexmount key，账号、Cookie 和会话接管 URL 不进入模型上下文、JSON 或日志。

开发时可另加 `--reload`，正式演示或部署时关闭热重载；不要与 `--workers` 同时使用。启动入口格式与部署选项参考 [FastAPI 手动部署](https://fastapi.tiangolo.com/deployment/manually/) 和 [Uvicorn 部署文档](https://uvicorn.dev/deployment/)。

### 前端联调与 LLM 对接（拟定契约）

- [前后端契约](docs/frontend-contract.md)：API base URL 为 `http://127.0.0.1:8000/api`，定义请求/响应、画像与卡片字段、R0 → R1 → R2 → R4 确认流程、版本冲突、重复请求和错误码；前端可先用示例 mock，不解析聊天文案作为业务状态。
- [LLM 对接](docs/llm-integration.md)：LiteLLM 异步调用、DeepSeek 配置、JSON 草案校验、受控工具调用和超时/重试预算。`DEEPSEEK_API_KEY` 是 provider 变量，`LLM_MODEL` 等是待实现的本项目配置项，不会因写入文档自动生效。
- 模型只提出草案；阶段推进、资格/时间检查、证据关联和最终响应由后端控制。两个文档均为尚未实现的联调约定，本次没有新增服务入口或调用模型。

## 文档地图

| 文件 | 内容 |
|---|---|
| `docs/handoff.md` | **当前进度、待办、待决事项（交接从这里开始）** |
| `docs/plan.md` | 项目方案、最新轻量 Python 后端设计及保留的历史方案 |
| `docs/frontend-contract.md` | 前后端接口、数据结构、确认与错误处理约定（待实现） |
| `docs/llm-integration.md` | LiteLLM 配置、模型调用、工具与输出校验约定（待实现） |
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
