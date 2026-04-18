# Codex integration

Codex doesn't have Claude Code's hook system, so the integration is lighter: you call `learned-behavior advice` at the start of a session and `learn` when a resolved failure is worth remembering.

## 1. Install

```bash
bash install.sh
```

## 2. Session start — pull advice

Add a shell alias or session-start snippet:

```bash
learned-behavior advice --agent codex --workspace "$PWD"
```

Paste the output into your Codex session so it has the approved rules before the first task.

## 3. After a resolved failure — record it

```bash
learned-behavior learn \
  --agent codex \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "Concrete check or action to take next time" \
  --rationale "Root cause and why the rule matters"
```

## 4. Mining (optional)

If you capture Codex command history into a log file, adapt `examples/guard-template.py` to replay those commands through `observe` so mining (`mine`, `mine-skill-miss`, `mine-edits`) can build candidates. Otherwise, stick to manual `learn` calls.

## 5. Nightly maintenance

```bash
learned-behavior promote --write
learned-behavior decay --write
```

Run the same two commands on a timer regardless of which agent produced the signal — the DB is shared.
