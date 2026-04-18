# Cursor integration

**Manual, copy-paste workflow** — Cursor has no public hook system for third-party observers, so `learned-behavior` can't auto-record what Cursor's agent does. Use it as a project notebook.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — pull advice into Cursor Rules

Cursor reads project rules from `.cursorrules` (legacy) and `.cursor/rules/*.md` (modern). Pipe advice straight into a rules file so every Cursor chat in this project sees it:

```bash
mkdir -p .cursor/rules
learned-behavior advice --agent cursor --workspace "$PWD" \
  > .cursor/rules/learned-behavior.md
```

Regenerate whenever you promote new lessons (or wire it into a git pre-commit / CI step). Cursor does not read arbitrary shell output live — it reads the file.

## 3. After a resolved failure — record it

```bash
learned-behavior learn \
  --agent cursor \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Root cause and detection signal"
```

## 4. Optional — feed Cursor's terminal history into the pipeline

If you run Cursor's terminal and have a shell history-hook of your own, you can replay Bash commands through `learned-behavior observe` so the skill-miss and repeated-error miners work. See `examples/guard-template.py` for the payload shape.

## 5. Nightly maintenance

```bash
learned-behavior maintain --write
```

## Notes

- The lesson corpus is shared across agents. If you also use Claude Code (which does have hook-level observation), its mined lessons will show up here too.
- Cursor's own "memories" feature is model-managed and opaque — `learned-behavior` is complementary: auditable, versionable, portable.
