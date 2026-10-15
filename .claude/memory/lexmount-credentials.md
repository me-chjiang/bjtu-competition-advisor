---
name: lexmount-credentials
description: Lexmount API key/project ID and BJTU MIS login belong to the user and live in lexmount-config.yaml (git-ignored)
metadata:
  type: project
---

The Lexmount credentials in `lexmount-config.yaml` (keys `api-key`, `project-id`, `base-url`) are the user's own account. The user confirmed this on 2026-10-13. They replace the old `env.sh`.

On 2026-10-13 the BJTU MIS login (`bjtu-entry-url`, `bjtu-username`, `bjtu-password`) moved into the same file; the old `教务系统/site.txt` was deleted. The login flow is documented in `教务系统/login-and-competition-guide.md`.

**Why:** The user wants one YAML file that's easy to edit. Scripts pass these values to `new Lexmount({...})` explicitly, so stale `LEXMOUNT_*` env vars in a shell can't override them.

**How to apply:** New scripts should read `lexmount-config.yaml` the same way `scripts/smoke-test.mjs` does. Never print the values or remove the file from `.gitignore`.
