---
description: Mine recent activity for new lesson candidates (errors, edit self-corrections, skill bypasses, guard blocks)
allowed-tools: ["Bash"]
disable-model-invocation: false
---

# Mine new lesson candidates from observed activity

Run the four miners against this workspace and report what new candidate lessons surface. Each miner clusters a different kind of behavioral signal. This is read-only by default — candidates appear in the DB as `candidate` status; nothing graduates to `approved` until `promote` is run.

## What to do

1. Run the four miners in sequence. Each prints a header and either a list of new candidates or a "nothing found" message.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" mine --workspace "$PWD"
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" mine-edits --workspace "$PWD"
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" mine-skill-miss --workspace "$PWD"
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" mine-blocks --workspace "$PWD"
   ```

2. Aggregate the output into a single summary for the user, grouped by miner:
   - **Recurring errors** (`mine`) — same error pattern across sessions
   - **Edit self-corrections** (`mine-edits`) — agent kept writing X and replacing it with Y
   - **Skill bypasses** (`mine-skill-miss`) — raw commands that should have used a configured skill
   - **Guard blocks** (`mine-blocks`) — PreToolUse denials that recur

3. For each candidate found, show: the proposed rule, the cluster size, and the workspace it was observed in.

4. End with a one-line next step:
   - If candidates were found, mention the user can promote them with `python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" promote --write` (or preview with the same command without `--write`).
   - If nothing new surfaced, say the corpus is up to date for this workspace.

5. Do not run `promote --write` automatically. Mining only produces candidates; promotion is a separate, deliberate step.

## Notes

- Mining looks at observed events accumulated since the last run. If hooks haven't fired recently in this workspace, output may be sparse.
- `mine-skill-miss` only finds clusters when `.claude/learned-behavior.json` (or the default registry) lists matching patterns. Without a registry, only generic rules apply.
- `mine-blocks` requires a PreToolUse guard that records denials via `observe-block`. Projects without a guard will have an empty `mine-blocks` section.
