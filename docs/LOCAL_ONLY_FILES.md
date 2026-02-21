# Local-only files (not committed)

This doc explains which files or directories are intentionally **not** committed to the wawa repo and why. It is for maintainers and AI assistants (e.g. Claude) working on the repo.

---

## Cursor / Claude config (in `.gitignore`)

| Entry      | Reason |
|-----------|--------|
| **`.cursorrules`** | Cursor project rules. May contain machine-specific paths (e.g. `E:\AIDAO`) and internal project names. Rule *content* that matters for contributors (repo boundaries, English-only, constitution) should live in human-readable form in `CONTRIBUTING.md` or this docs folder, not in tool-specific files. Keeping `.cursorrules` local avoids leaking internal setup. |
| **`.cursor/`**     | Cursor editor workspace data. Not needed for building or contributing. |
| **`.claude/`**    | Claude-related prompts, sessions, or config. Local workflow only; no need to expose in the public repo. |

**Decision (2025-02):** Do not commit these. Public repo stays clean and tool-agnostic; contributors get guidance from `CONTRIBUTING.md` (or similar) instead of Cursor/Claude-specific files.

---

## Strategy / process docs (already in `.gitignore`)

Files such as `ANTI_COPY_PROMOTION_STRATEGY.md`, `TWITTER_LAUNCH_THREADS.md`, `SYSTEM_SELFCHECK_REPORT.md`, etc. are listed in `.gitignore` under “Strategy & process docs”. Code = open source; strategy and internal process docs = private. They remain local only.

---

## If you (or Claude) need to restore local rules

- Copy or adapt rule *content* from any public doc (e.g. `CONTRIBUTING.md`, `docs/REPO_BOUNDARIES.md`) into your local `.cursorrules` if you use Cursor.
- Do not commit `.cursorrules` or `.claude/`; the reasons above still apply.
