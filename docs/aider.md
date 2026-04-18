# Aider integration

**Manual, copy-paste workflow** — and for once the manual path is lightweight because Aider reads a conventions file natively.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — pipe advice into CONVENTIONS.md

Aider reads extra system prompts from any file you pass with `--read`:

```bash
learned-behavior advice --agent aider --workspace "$PWD" > CONVENTIONS.md
aider --read CONVENTIONS.md
```

Or commit `CONVENTIONS.md` and set it in `.aider.conf.yml`:

```yaml
read: CONVENTIONS.md
```

Regenerate `CONVENTIONS.md` after `learned-behavior maintain --write`.

## 3. After Aider gets something wrong — record it

```bash
learned-behavior learn \
  --agent aider \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Root cause and signal to watch for"
```

## 4. Optional — mine Aider's history file

Aider keeps a per-project chat history at `.aider.chat.history.md`. You can grep it for recurring errors and feed them to `observe` via a small adapter; see `examples/guard-template.py` for the event shape.

## 5. Nightly maintenance

```bash
learned-behavior maintain --write
```
