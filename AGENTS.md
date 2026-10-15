# 项目约定（AI 编码助手通用）

本文件是 Claude Code 与 opencode 共用的项目指令，优先级高于各自的全局默认设置。
- opencode 直接读本文件。
- Claude Code 通过 `CLAUDE.md` 中的 `@AGENTS.md` 引入本文件。

## 项目概述

- 参加 Lexmount「真实任务挑战」的作品：北交大竞赛「能力匹配」Agent。
- 用 Lexmount 云浏览器采集教务系统（MIS）上的竞赛，补全公开信息，再由多轮筛选和多 Agent 讨论给出参赛方案。
- **开工前先读**：
  - `docs/handoff.md`：当前进度、待办、待决事项
  - `docs/plan.md`：已确认的方案
  - `issue.md`：未解决的问题

## 凭据与隐私（必须遵守）

- 凭据放在根目录的 `lexmount-config.yaml`（已 git-ignore；模板是 `lexmount-config.example.yaml`）。
  - 脚本统一通过 `lib/lexmount.mjs` 的 `loadConfig()` / `withClient()` 读取。
  - 不要打印凭据的值，不要写进日志、文档或提交。
- 会话的 `connectUrl` 和 `inspectUrl` 能接管云浏览器，同样不要打印或落盘。
- 以下内容都含个人信息，已 git-ignore，不要提交：
  - `data/`、`.state/`
  - `教务系统/*.png`
  - `.playwright-mcp/` 等浏览器工具留下的快照和日志
- 公开材料中给学生和老师的姓名打码。

## MIS 操作规则

- 只读、低频访问。**不要点「报名」**：`/innovation/cpteam/create/` 会建队。
- 登录走 MIS 统一认证（`mis.bjtu.edu.cn` → CAS），不要用 `aa.bjtu.edu.cn/client/login/`：那是另一套账号体系，反复试错会锁号。
- 登录失败只试一次就停下来排查。
- 详细路径和页面结构见 `教务系统/login-and-competition-guide.md`。

## Lexmount 使用

- 云会话按 Browser hours 计费，并发有限；会话必须在 `finally` 中关闭。复用 `lib/lexmount.mjs` 的 `withCloudBrowser()`。
- 需要用到本地网络时用 `withTunnel()`（SDK 本地隧道）；会话要先于隧道关闭。
- **首选**：在支持的设备上（如 Linux x64）使用 Lexmount 原生 MCP / CLI + Skill（v1.2.4 只支持 macOS arm64、Linux x64、Windows x64）。体验明显好于 SDK 转接。
- **备选**：在不支持原生 MCP / CLI 的设备上（如 Intel Mac），用 Node SDK + Playwright 经 CDP 转接，也就是 `lib/` 和 `collect/` 里的脚本。这条路线较卡。
- 已知问题：10-13 测试时，Lexmount 远程 MCP 的 OAuth 拒绝了 Claude Code 的客户端（`invalid_client`）；opencode 能否接入，待 Linux 侧验证。

## 运行

- Node ≥ 20，执行 `npm ci`。
- 冒烟测试：`node scripts/smoke-test.mjs`
- 采集 MIS（1 页）：`node collect/mis.mjs --pages 1 --perpage 20`
- 命令输出较长时写到文件里，只看末尾。

## 协作规范

- 修改前先说明意图，确认后再动手。
- 遇到不确定的需求，先提问，不要猜。
- 生成的内容要注明来源（引用时），或标注为 AI 辅助生成。
- 不自动执行破坏性操作：删除、覆盖、push、改写历史。
- 文件名用 kebab-case；输出格式优先用 markdown。

## Git 提交规范

- 所有提交的 author 用本机 git 用户配置。
- 提交信息不加 `Co-Authored-By` 或其他 AI 署名。
- Commit message 用自由文本，说明「为什么」改。
