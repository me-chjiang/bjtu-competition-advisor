@AGENTS.md

# Claude Code 专属

- 本项目的 Claude 配置、memory、skill 都放在项目根目录，不使用全局路径：
  - `./.claude/memory/`：自动记忆目录，索引文件是 `MEMORY.md`。opencode 不读这个目录，所以重要事实要同步写进 `AGENTS.md` 或 `docs/`。
  - `./.claude/`：skill、agent、settings 等。`.claude/skills/` 下的 skill 也会被 opencode 加载。
- 以上目录不得加入 `.gitignore`，随代码一起提交（`settings.local.json` 除外）。
