# Continue.dev integration

**Manual, copy-paste workflow** — Continue.dev (VS Code / JetBrains open-source agent) reads per-workspace rules from `.continue/rules/` and from `config.yaml` system prompts. Pipe advice there.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — generate a Continue rules file

```bash
mkdir -p .continue/rules
learned-behavior advice --agent continue --workspace "$PWD" \
  > .continue/rules/learned-behavior.md
```

Continue loads every file in `.continue/rules/` into the system prompt for that workspace. Regenerate after `learned-behavior maintain --write`.

## 3. After a resolved failure — record it

```bash
learned-behavior learn \
  --agent continue \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Root cause and signal to watch for"
```

## 4. Optional — custom slash command

Add a Continue slash command that shells out to `learned-behavior learn` via Continue's `run` step, so you can record lessons without leaving the editor. See Continue's custom-commands docs.

## 5. Nightly maintenance

```bash
learned-behavior maintain --write
```
