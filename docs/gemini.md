# Gemini / Jules / Google coding models

**Manual, copy-paste workflow.** Covers:

- **Gemini CLI** (`gemini` command line) — has a settings file (`~/.gemini/settings.json`) and project-level instructions but no third-party hook API
- **Jules** (Google's async coding agent on `jules.google.com`) — web UI; the only hook surface is what you put in the task prompt
- **Gemini Code Assist** (VS Code / JetBrains extensions) — reads per-repo instruction files
- **Google AI Studio / Vertex AI agents** — see the generic "paste advice into system prompt" pattern

None of these expose structured session hooks today, so `learned-behavior` runs as a project notebook.

## 1. Install

```bash
bash install.sh
```

## 2. Before a session — pull advice into the model's context

### Gemini CLI / Code Assist

Many Google tools read a per-repo instructions file named `GEMINI.md` (similar to `CLAUDE.md` and `AGENTS.md`). Pipe advice there:

```bash
learned-behavior advice --agent gemini --workspace "$PWD" > GEMINI.md
```

Regenerate after `learned-behavior maintain --write` runs.

### Jules (web)

Copy advice into the task's "context" / system-prompt field manually:

```bash
learned-behavior advice --agent jules --workspace "$PWD" | pbcopy   # macOS
```

Paste into the Jules task before dispatching.

### Vertex AI agents / API

Fold the advice text into the system-instruction parameter you pass to the model.

## 3. After a resolved failure — record it

```bash
learned-behavior learn \
  --agent gemini \
  --workspace "$PWD" \
  --title "Short lesson title" \
  --rule "What to do differently next time" \
  --rationale "Root cause and signal to watch for"
```

Use `--agent jules` for Jules-specific lessons if you want the provenance split in `review`.

## 4. Nightly maintenance

```bash
learned-behavior maintain --write
```

## Notes

- The CLI is agent-neutral: the `--agent` flag just tags provenance. All lessons end up in the same per-workspace corpus and are surfaced by `advice` regardless of which agent wrote them.
- If the Gemini CLI gains a pre-/post-tool hook system, the generic `examples/guard-template.py` script shows the JSON shape `observe` expects.
