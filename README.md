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

## Install

```bash
git clone https://github.com/<you>/learned-behavior ~/workshop/learned-behavior
bash ~/workshop/learned-behavior/install.sh
```

Installer symlinks the CLI into `~/.local/bin/learned-behavior` and creates the data directory at `~/.local/share/learned-behavior/` (or `$LEARNED_BEHAVIOR_HOME` if set).

## Per-agent setup

See `docs/`:

- [docs/claude-code.md](docs/claude-code.md) — drop-in `settings.local.json` hooks
- [docs/codex.md](docs/codex.md) — Codex session integration
- [docs/copilot.md](docs/copilot.md) — Copilot workflow

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
```

Add `--write` (or drop `--dry-run`) to apply.

## Design

See [DESIGN.md](DESIGN.md) for the state machine, scoring formula, and why we chose behavioral signal over self-report.

## License

MIT
