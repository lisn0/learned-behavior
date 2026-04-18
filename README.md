# learned-behavior

Self-improving memory for AI coding agents (Claude Code, Codex, Copilot).

Observes what your agent does, distills recurring patterns into lessons, surfaces the relevant ones before each task, and **auto-promotes** rules that keep proving themselves while **decaying** stale ones.

No self-report. No LLM in the loop. Pure behavioral signal mined from agent hook events.

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

## Install

```bash
git clone https://github.com/lisn0/learned-behavior ~/workshop/learned-behavior
bash ~/workshop/learned-behavior/install.sh
```

Installer symlinks the CLI into `~/.local/bin/learned-behavior` and creates the data directory at `~/.local/share/learned-behavior/` (or `$LEARNED_BEHAVIOR_HOME` if set).

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

## License

MIT
