# learned-behavior

[![tests](https://github.com/lisn0/learned-behavior/actions/workflows/test.yml/badge.svg)](https://github.com/lisn0/learned-behavior/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/learned-behavior.svg)](https://pypi.org/project/learned-behavior/)

Self-improving memory for AI coding agents (Claude Code, Codex, Copilot).

Observes what your agent does, distills recurring patterns into lessons, surfaces the relevant ones before each task, and **auto-promotes** rules that keep proving themselves while **decaying** stale ones.

No self-report. No LLM in the loop. Pure behavioral signal mined from agent hook events.

## What it isn't

- Not a coding-style linter — it doesn't read your code, only your agent's tool calls.
- Not a context-window manager or summarizer — lessons are short rules, not session memory.
- Not cloud-hosted — all storage and processing is local SQLite. Nothing leaves your machine.

## What it captures

- **Repeated failures** — same error pattern recurring across sessions
- **Skill bypasses** — raw `aws logs` when a `casino-logs` skill is available, raw `kubectl` when a `k3s` skill is available, etc. (project-configurable)
- **Repeated Edit self-corrections** — the agent keeps writing `X` and replacing it with `Y`; the rule should be "write Y directly next time"
- **PreToolUse blocks** — every time a guard denies a command, we record it. Recurring blocks surface training gaps.

## What it produces

A durable, project-scoped list of **rules** your agents see before their next task:

```
$ learned-behavior advice --workspace "$PWD"
1. laravelphp/vapor image has no bash — use `sh -c`, not `bash -lc`
2. After composer install on a new worktree, run `php artisan package:discover`
3. Never --force-push to production/staging — use --force-with-lease on feature branches only
```

## How it improves itself

Every lesson has a `confidence` score and a `status` (`candidate` → `approved` → `dormant`).

- **Promotion**: candidates with ≥ N observations over ≥ M days with no contradicting signal graduate to `approved`.
- **Decay**: approved lessons whose pattern hasn't been seen in X days lose confidence, eventually going `dormant` and dropping out of `advice`.
- **Reinforcement**: when a lesson is surfaced and the warned-about pattern doesn't recur in that session, confidence ticks up.

Run `learned-behavior promote` and `learned-behavior decay` nightly (or via a cron/Stop hook) and the corpus gets better without human curation.

## Requirements

- Python 3.10+ (uses PEP 604 union syntax and built-in generic type parameters)
- SQLite 3 (ships with Python's `sqlite3` module)
- No third-party runtime dependencies

## Privacy

- **No network calls.** The plugin never reaches out to any server — no telemetry, no analytics, no phone-home, no auto-update check.
- **No data leaves your machine.** Everything is stored in one local SQLite file at `~/.local/share/learned-behavior/learning.db` (or `$LEARNED_BEHAVIOR_HOME`).
- **No third parties.** Zero runtime dependencies; nothing to ship your data to even if it tried.
- **You own the data.** Delete the SQLite file at any time and the plugin starts fresh. See [Disable / uninstall](#disable--uninstall).

There is no separate privacy policy because there is nothing to disclose beyond the above. Full technical detail of every file touched and every hook registered is in the next section.

## Side effects & permissions

Full disclosure of everything the plugin touches on your machine:

- **Hooks registered**: `SessionStart`, `UserPromptSubmit`, `PostToolUse *`, `Stop`, `SessionEnd` — all invoke `python3 ${CLAUDE_PLUGIN_ROOT}/learning.py <subcommand>`. Each call has a short timeout (3–5s) and fails open.
- **Files written**: one SQLite DB at `~/.local/share/learned-behavior/learning.db` (or `$LEARNED_BEHAVIOR_HOME` if set). Nothing else is created or modified outside that directory.
- **Network**: none. No telemetry, no outbound requests, no phone-home. All processing is local.
- **Execution surface**: the CLI reads stdin/argv, queries/writes the SQLite DB, prints JSON or text to stdout. It does not spawn subprocesses, shell out, or touch files outside its own data dir.
- **Destructive subcommands**: `promote`, `decay`, `reinforce`, `maintain` default to dry-run. They only mutate the DB when you pass `--write`.
- **Trust boundary**: `observe` records hook payloads into SQLite verbatim. If you don't want a particular command or path recorded, don't run it while hooks are active.

## Disable / uninstall

- **Plugin (Claude Code)**: `/plugin uninstall learned-behavior@learned-behavior` — removes hooks immediately.
- **Manual hooks**: delete the `hooks` block from your `.claude/settings.local.json`.
- **Data**: the SQLite DB persists after uninstall. Remove it explicitly with `rm -rf ~/.local/share/learned-behavior/` (or `$LEARNED_BEHAVIOR_HOME`).

## Install

```bash
git clone https://github.com/lisn0/learned-behavior ~/workshop/learned-behavior
bash ~/workshop/learned-behavior/install.sh
```

Installer symlinks the CLI into `~/.local/bin/learned-behavior` and creates the data directory at `~/.local/share/learned-behavior/` (or `$LEARNED_BEHAVIOR_HOME` if set).

## Example: from observation to advice

End-to-end lifecycle of a single lesson — observed, mined, surfaced.

**1. Agent makes the same edit twice in a session.** It writes `bash -lc 'php artisan ...'` inside a `laravelphp/vapor` Dockerfile, the build fails with `bash: not found`, and the agent corrects it to `sh -c 'php artisan ...'`. The `PostToolUse` hook records both Edits and the failure.

**2. Mining clusters the self-correction into a candidate lesson.**

```
$ learned-behavior mine-edits --workspace "$PWD"
[candidate] 3 sessions replaced "bash -lc" → "sh -c" in Dockerfile* — proposed rule:
  "On laravelphp/vapor images, use sh -c (not bash -lc) for inline commands"
```

**3. After ≥ N observations across ≥ M days with no contradicting signal, `promote` graduates it to `approved`.**

```
$ learned-behavior promote --write
Promoted 1 lesson to approved: "Use sh, not bash, on vapor images"
```

**4. Next session, the `UserPromptSubmit` hook surfaces it before the agent does anything.**

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Relevant lessons from the shared learning DB:\n- Use sh, not bash, on vapor images: laravelphp/vapor base image has no bash; use 'sh -c' for inline commands"
  }
}
```

**5. If the lesson isn't triggered for X days, `decay` lowers its confidence and eventually marks it `dormant`** — it stops appearing in `advice` until the underlying pattern resurfaces.

## Troubleshooting

**Advice isn't showing up in my next session.**
Approved lessons only surface for the workspace they were learned in. Confirm with `learned-behavior review --workspace "$PWD"`. If you see lessons listed there but they aren't appearing in-session, your hook may be timing out — check Claude Code's hook logs (the plugin fails open by design, so a timeout is silent).

**Lessons aren't being created from my repeated errors.**
Candidates need ≥ N observations over ≥ M days before promotion (`mine` clusters them, `promote` graduates them). Run `learned-behavior mine --workspace "$PWD"` and `learned-behavior review` to see what's still in `candidate` state. Lower the thresholds with `--min-observations` / `--min-age-days` on `promote` if you want faster graduation.

**The SQLite DB is getting large.**
Hook events accumulate. The DB lives at `~/.local/share/learned-behavior/learning.db` (or `$LEARNED_BEHAVIOR_HOME`). It's safe to delete — you'll lose history but lessons currently in `approved` state can be re-mined from any retained event source. There's no built-in pruning yet; if size becomes a problem, file an issue.

**A noisy or wrong lesson keeps appearing.**
Use `learned-behavior review` to find its ID, then mark it dormant manually (or wait for `decay` to do it). A future release will add a `forget` subcommand.

**Hook failing open — how do I tell?**
By design, every hook has a 3–5s timeout and swallows errors so a misbehaving plugin can't block your session. To debug, run the same command from your shell with the same env vars (`CLAUDE_PROJECT_DIR`, `CLAUDE_SESSION_ID`) and inspect stderr.

## Per-agent setup

**Claude Code is the only agent that supports automatic observation** (via its `settings.local.json` hook system). Every other agent integration below is a manual "paste advice into the model's context, record lessons by hand when something goes wrong" flow. The lesson corpus is shared — if you run Claude Code alongside another tool, its mined lessons surface everywhere.

| Agent | Integration | Docs |
|-------|-------------|------|
| Claude Code | Automatic — hooks observe every tool call | [docs/claude-code.md](docs/claude-code.md) |
| Codex (OpenAI CLI / VS Code) | Manual | [docs/codex.md](docs/codex.md) |
| GitHub Copilot | Manual (rules file or Copilot Chat paste) | [docs/copilot.md](docs/copilot.md) |
| Cursor | Manual (writes to `.cursor/rules/`) | [docs/cursor.md](docs/cursor.md) |
| Windsurf / Codeium Cascade | Manual (writes to `.windsurfrules`) | [docs/windsurf.md](docs/windsurf.md) |
| Google Antigravity | Manual | [docs/antigravity.md](docs/antigravity.md) |
| Gemini / Jules / Gemini Code Assist | Manual (writes to `GEMINI.md`) | [docs/gemini.md](docs/gemini.md) |
| Aider | Manual (`aider --read CONVENTIONS.md`) | [docs/aider.md](docs/aider.md) |
| Continue.dev | Manual (writes to `.continue/rules/`) | [docs/continue.md](docs/continue.md) |

Have another agent that should be here? PRs welcome — the CLI is agent-neutral (the `--agent` flag just tags provenance) so adding a new one is mostly a docs task.

## Per-project skill registry (optional)

In any project, create `.claude/learned-behavior.json` to declare skill-bypass rules:

```json
{
  "skill_registry": [
    { "pattern": "\\baws\\s+logs\\b", "skill": "casino-logs",
      "reason": "Use casino-logs skill, not raw `aws logs`" }
  ]
}
```

Patterns are Python regex. Project config is merged over the default registry.

## Slash commands (Claude Code plugin)

When installed as a plugin, three on-demand commands are available — nothing fires automatically beyond the hooks already documented above. The user must invoke them.

| Command | Purpose |
|---------|---------|
| `/learned-behavior:advice` | Show approved lessons relevant to the current workspace |
| `/learned-behavior:review` | Summary of stored lessons (approved + candidates) and recurring errors for this workspace |
| `/learned-behavior:mine` | Run the four miners — error clustering, Edit self-corrections, skill bypasses, guard blocks — and surface new candidate lessons |

`mine` only proposes candidates; promotion to `approved` remains a separate explicit step (`learning.py promote --write`).

## CLI

```
learned-behavior advice --workspace "$PWD"        # lessons relevant to this project
learned-behavior learn ...                        # persist a new lesson manually
learned-behavior review --workspace "$PWD"        # summary of lessons + recurring errors

learned-behavior mine --workspace "$PWD"          # cluster error events into candidates
learned-behavior mine-edits --workspace "$PWD"    # cluster repeated Edit self-corrections
learned-behavior mine-skill-miss --workspace "$PWD"  # commands that bypass skills
learned-behavior mine-blocks --days 30            # PreToolUse guard blocks

learned-behavior promote --dry-run                # preview candidates ready to approve
learned-behavior decay --dry-run                  # preview lessons going dormant
learned-behavior reinforce --session-id <id>      # +/- confidence based on whether surfaced advice held
learned-behavior suggest-hooks --workspace "$PWD" # report missing hook wiring for this project
learned-behavior suggest-skills --workspace "$PWD" # surface repeated raw commands that deserve a skill
learned-behavior maintain --write                 # rate-limited nightly promote+decay
```

Add `--write` (or drop `--dry-run`) to apply.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

Tests are self-contained — they spin up an ephemeral SQLite DB in a tmp dir; nothing touches your real learning DB.

## Design

See [DESIGN.md](DESIGN.md) for the state machine, scoring formula, and why we chose behavioral signal over self-report.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## License

MIT
