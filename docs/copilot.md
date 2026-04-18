# Copilot integration

GitHub Copilot doesn't emit structured events that `learned-behavior` can consume automatically, so the integration is manual: use the CLI as a project notebook the Copilot-driven session reads at the start and updates at the end.

## 1. Install

```bash
bash install.sh
```

## 2. Before you start a session

```bash
learned-behavior advice --agent copilot --workspace "$PWD"
```

Paste the result into your Copilot Chat context (or a VS Code snippet you include in the prompt).

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

Shows the corpus of lessons and the recurring failures still lacking a rule.

## 5. Nightly maintenance

```bash
learned-behavior promote --write
learned-behavior decay --write
```

## Notes

- The `workspace` column isolates records per project; you can freely mix Copilot-produced lessons with ones from other agents on the same project.
- If you use Copilot alongside Claude Code or Codex, let those richer integrations do the observing. The lessons they generate will be surfaced to Copilot via `advice` just the same.
