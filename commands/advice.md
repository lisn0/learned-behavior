---
description: Show relevant approved lessons for the current project
allowed-tools: ["Bash"]
disable-model-invocation: false
---

# Show learned-behavior advice

Surface every approved lesson that applies to the current workspace. Read-only — does not mutate the lesson DB.

## What to do

1. Run the advice CLI against the current working directory:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/learning.py" advice --workspace "$PWD"
   ```

2. If the command prints `Relevant lessons from the shared learning DB:` followed by bullets, present them to the user as a numbered list (preserve the rule + rationale verbatim).

3. If the output is empty or says no lessons matched, tell the user:
   - There are no approved lessons for this workspace yet.
   - Suggest they run `/learned-behavior:review` to see lessons in `candidate` state, or `/learned-behavior:mine` to look for new patterns.

4. Do not invent or paraphrase lessons. Only show what the CLI returned.

## Notes

- Lessons are workspace-scoped — running this in a different project will surface a different set.
- The DB lives at `~/.local/share/learned-behavior/learning.db` (or `$LEARNED_BEHAVIOR_HOME` if set).
