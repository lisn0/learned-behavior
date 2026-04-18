# Copilot integration

**This is a manual, copy-paste workflow — not a hook-level integration.**

GitHub Copilot (Chat or inline completions) doesn't expose structured session events, so `learned-behavior` can't observe it. Use the CLI as a project notebook: pull advice at the start of a task and record a lesson when Copilot steers wrong.

If you want automatic mining, run the Claude Code integration alongside Copilot. The DB is shared — lessons that Claude Code mines will surface in `advice` here too.

## 1. Install

```bash
bash install.sh
```

## 2. Before you start a session

```bash
learned-behavior advice --agent copilot --workspace "$PWD"
```

Paste the result into Copilot Chat, a VS Code snippet, or a workspace instruction file (e.g., `.github/copilot-instructions.md`).

## 3. After resolving an issue Copilot got wrong

```bash
learned-behavior learn \
  --agent copilot \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Why Copilot went off the rails and what signal to watch for"
```

## 4. Review

```bash
learned-behavior review --workspace "$PWD"
```

## 5. Nightly maintenance

```bash
learned-behavior maintain --write
```

## Notes

- The `workspace` column isolates records per project; Copilot-produced lessons mix cleanly with ones from Claude Code or Codex on the same project.
- `learned-behavior` is read-only from Copilot's perspective — nothing here can modify Copilot's behavior directly. The value is that **you** paste the rules in before asking Copilot to do the next thing.
