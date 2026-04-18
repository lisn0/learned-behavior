# Codex integration

**This is a manual, copy-paste workflow — not a hook-level integration.**

OpenAI Codex (the CLI and the VS Code extension) doesn't emit structured session events that `learned-behavior` can subscribe to, so there's no way to observe agent behavior automatically. Instead, you use the CLI as a project notebook: pull the current rules at session start, and record lessons by hand when Codex gets something wrong.

If you want the full auto-mining loop (candidates from error clusters, reinforcement scoring, automatic promotion/decay), use the Claude Code integration — its hooks feed the shared DB, and any lessons it mines will surface in `advice` regardless of which agent you use day-to-day.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — pull advice

```bash
learned-behavior advice --agent codex --workspace "$PWD"
```

Paste the output into your Codex chat context or a saved prompt snippet. There is no hook that does this for you.

## 3. After Codex gets something wrong — record it by hand

```bash
learned-behavior learn \
  --agent codex \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "Concrete check or action to take next time" \
  --rationale "Root cause and why the rule matters"
```

## 4. Optional — replay command history into the pipeline

If you capture Codex command history into a log file, adapt `examples/guard-template.py` to replay those commands through `observe` so `mine`, `mine-skill-miss`, and `mine-edits` can cluster candidates. This is a build-it-yourself piece and is not shipped.

## 5. Nightly maintenance

```bash
learned-behavior maintain --write
```

Same DB is shared across agents, so this works even if Claude Code is the thing actually feeding events.
