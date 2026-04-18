# Windsurf integration

**Manual, copy-paste workflow** — Windsurf (Codeium) does not expose a hook API to third-party tools, so `learned-behavior` can't auto-capture what Cascade does. Use it as a project notebook and feed rules back to Windsurf via its rules file.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — generate a Windsurf rules file

Windsurf reads project rules from `.windsurfrules` (workspace-scoped) and `.codeiumrules` (legacy). Pipe advice into one of them:

```bash
learned-behavior advice --agent windsurf --workspace "$PWD" > .windsurfrules
```

Cascade picks it up on next prompt. Regenerate after `promote` runs.

## 3. After a resolved failure — record it

```bash
learned-behavior learn \
  --agent windsurf \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Root cause and detection signal"
```

## 4. Nightly maintenance

```bash
learned-behavior maintain --write
```

## Notes

- Mining subcommands (`mine`, `mine-skill-miss`, `mine-edits`) only have data to work with if something is feeding `observe` events. If you run Claude Code alongside Windsurf, its hooks fill that role and every agent benefits.
- Cascade's own memory is opaque; `learned-behavior` keeps a versionable, inspectable corpus under your control.
