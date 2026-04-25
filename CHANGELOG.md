# Changelog

All notable changes to `learned-behavior` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-04-25

### Added
- Three on-demand slash commands for the Claude Code plugin — invoked manually, nothing fires automatically:
  - `/learned-behavior:advice` — show approved lessons for the current workspace
  - `/learned-behavior:review` — summary of stored lessons and recurring errors for this workspace
  - `/learned-behavior:mine` — run the four miners (errors, edits, skill bypasses, guard blocks) and surface new candidate lessons
- README "Slash commands" section documenting the new commands.

### Notes
- Promotion of mined candidates remains a deliberate, separate step (`learning.py promote --write`); `/learned-behavior:mine` only proposes.

## [0.1.0] — 2026-04-25

Initial public release.

### Added
- Self-improving rule corpus mined from Claude Code hook events — no LLM in the loop, no self-report.
- Five hook integrations: `SessionStart`, `UserPromptSubmit`, `PostToolUse *`, `Stop`, `SessionEnd`.
- Lesson lifecycle: `candidate` → `approved` → `dormant` with confidence-based promotion, decay, and reinforcement.
- Mining subcommands: `mine` (recurring errors), `mine-edits` (Edit self-corrections), `mine-skill-miss` (skill-bypass commands), `mine-blocks` (PreToolUse guard denials).
- Per-project skill registry via `.claude/learned-behavior.json`.
- Manual integration paths for Codex, Copilot, Cursor, Windsurf, Antigravity, Gemini, Aider, and Continue.dev.
- SQLite-backed local store at `~/.local/share/learned-behavior/learning.db` (overridable with `$LEARNED_BEHAVIOR_HOME`).
- Self-contained Claude Code plugin — installs via `/plugin install`, no `pip install` required.
- Test suite (`pytest tests/`) running against an ephemeral DB.

### Notes
- Zero third-party runtime dependencies; Python 3.10+ stdlib only.
- No network calls, no telemetry. All processing local.
