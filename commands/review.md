---
description: Review what's been learned in this project — lessons, candidates, and recurring errors
allowed-tools: ["Bash"]
disable-model-invocation: false
---

# Review learned-behavior state for this project

Print a workspace-scoped summary: approved lessons, candidates not yet promoted, and recent recurring errors. Read-only.

## What to do

1. Run the review CLI against the current working directory:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" review --workspace "$PWD"
   ```

2. Present the output to the user as-is. The CLI groups its output by section — preserve those groupings:
   - **Stored lessons** — each lesson with status (`approved`/`candidate`/`dormant`), confidence score, and observation count.
   - **Recurring errors** (if any) — error fingerprints with occurrence counts.

3. After showing the output, give a one-line interpretation:
   - If candidates exist, suggest the user run `/learned-behavior:mine` to see if they should be promoted.
   - If recurring errors exist with no matching lesson yet, suggest the user run `/learned-behavior:mine` to cluster them into candidates.
   - If everything is `approved` and no recurring errors are showing, say the workspace is in a steady state.

4. Do not run `promote`, `decay`, or any mutating subcommand from this command. Those are separate CLI calls and should only run when the user explicitly asks.

## Notes

- The review is a snapshot — re-run it after sessions end to see new candidates appear.
- For a global view across all workspaces, the user can run the CLI directly: `python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" review` (omit `--workspace`).
