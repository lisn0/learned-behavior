# Google Antigravity integration

**Manual, copy-paste workflow** — Google Antigravity (the agent-first IDE) does not expose a public third-party hook API as of this writing. `learned-behavior` can't auto-observe what Antigravity's agents do, but you can use it as a project notebook alongside.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — pull advice

```bash
learned-behavior advice --agent antigravity --workspace "$PWD"
```

Paste the output into your Antigravity workspace instructions or project-level agent context. If your workspace supports a rules/instructions file (e.g., an `AGENTS.md` or equivalent), pipe advice there:

```bash
learned-behavior advice --agent antigravity --workspace "$PWD" > AGENTS.md
```

Regenerate after `promote` runs so new approved lessons show up.

## 3. After Antigravity's agent gets something wrong — record it

```bash
learned-behavior learn \
  --agent antigravity \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "Concrete rule to apply next time" \
  --rationale "Root cause and signal to watch for"
```

## 4. Nightly maintenance

```bash
learned-behavior maintain --write
```

## Notes

- If Antigravity ships a hook / webhook / notebook-export mechanism in the future, it can be wired into `observe` the same way Claude Code hooks are — the CLI accepts generic JSON on stdin; see `examples/guard-template.py`.
- The DB is shared across agents, so any lessons mined by Claude Code or added manually from other tools will surface here too.
