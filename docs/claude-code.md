# Claude Code integration

Claude Code's [hook system](https://docs.claude.com/en/docs/claude-code/hooks) is the primary signal source.

## 1. Install

```bash
bash install.sh
```

This places `learned-behavior` on your PATH and creates the data directory.

## 2. Wire the hooks

Copy the `hooks` block from [`examples/settings.local.json.example`](../examples/settings.local.json.example) into your project's `.claude/settings.local.json`. All paths use `$HOME`, so the same block drops into any project unchanged.

What each hook does:

| Hook | Purpose |
|------|---------|
| `SessionStart`, `SessionEnd` | Marks session boundaries in the event log |
| `UserPromptSubmit` — `advice` | Emits relevant approved lessons as `additionalContext` |
| `UserPromptSubmit` — `observe` | Records the prompt for later mining |
| `PostToolUse *` | Records every tool call (success and failure) for fingerprinting |
| `Stop` — `session-check` | Surfaces recurring failures from this session as extra context |

## 3. Optional: PreToolUse guard

If you want to capture guardrail blocks, copy [`examples/guard-template.py`](../examples/guard-template.py) into your project and register it as a `PreToolUse` hook with matcher `Bash`. Every refusal is mined into `mine-blocks`.

## 4. Nightly maintenance

Add a cron or a `Stop` hook that runs:

```bash
learned-behavior promote --write
learned-behavior decay --write
```

Promotion graduates candidates with enough evidence; decay quietens stale rules.

## Agent value

Pass `--agent claude` to every command so cross-agent statistics stay clean.
