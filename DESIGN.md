# Design

## Why behavioral signal over self-report

Agents (and humans) are unreliable narrators of their own mistakes. A "lesson" the agent writes to a memory file at end-of-session is filtered through the agent's summary, not the actual failure.

Behavioral signal — the raw stream of hook events — is ground truth: what commands were actually run, which failed, which the user blocked, which edits were undone. Mining that stream produces rules grounded in evidence, not narration.

## Data model

Two tables: `events` (raw hook payloads) and `lessons` (distilled rules).

```sql
events(
  id, created_at, agent, source, workspace, event_name, status,
  session_id, tool_name, prompt, summary, fingerprint, payload_json
)

lessons(
  id, created_at, updated_at, workspace, status, agent,
  title, rule_text, rationale, source_event_id, fingerprint,
  confidence, observations, approvals, last_seen_at
)
```

`fingerprint` is a normalized string (paths, hex, numbers stripped) so different sessions producing the same failure cluster together.

## Lesson states

```
candidate → approved → dormant → retired
     ↑          ↓
     └─ (demoted, rare)
```

- **candidate**: mined from signal, not yet trusted. Included in `advice` only if `--include-candidates`.
- **approved**: earned promotion via evidence. Included in `advice` by default.
- **dormant**: hasn't fired in a long time. Hidden from default `advice` but not deleted.
- **retired**: dormant + very old. Soft-deleted.

## Confidence scoring

`confidence ∈ [0.0, 1.0]`. Initial candidates start at ~0.3–0.5 based on observation count.

**Reinforcement events** (confidence up):
- New observation of the same fingerprint: +0.05 (diminishing returns past 20 observations)
- Lesson surfaced via `advice`, error fingerprint does **not** recur that session: +0.03
- Manual `approve`: jump to 0.9

**Decay events** (confidence down):
- No observation in > 14 days: -0.02/week
- Lesson surfaced via `advice`, same error still recurs: -0.1 (negative evidence — the rule didn't help)
- Fingerprint hasn't appeared in > 60 days: eligible for dormant

## Promotion rules (candidate → approved)

All of:
- `status = 'candidate'`
- `observations >= 5` (configurable)
- `age >= 7 days` (configurable; prevents hair-trigger promotion on one bad day)
- No negative reinforcement in the last 14 days
- `confidence >= 0.6`

Run daily via `learned-behavior promote`. Default `--dry-run` — operator sees what would flip before it flips.

## Decay rules (approved → dormant)

Any of:
- `last_seen_at > 60 days ago` AND `observations < 20`
- `confidence < 0.3`

Run daily via `learned-behavior decay`.

## Retirement (dormant → retired)

- `status = 'dormant'` AND `last_seen_at > 180 days ago`

Retired rows are hidden from all reads but kept on disk for audit.

## Skill registry (project config)

Per-project `.claude/learned-behavior.json` lets projects declare which commands *should have* used a local skill. The mining subcommand `mine-skill-miss` clusters commands that match a registered pattern but didn't use the skill — evidence of training gaps.

## Non-goals

- **LLM-in-the-loop.** All clustering is deterministic (regex + normalized fingerprint). No model calls, no API costs, no privacy questions.
- **Cross-user sync.** The DB is local to the user. Sharing lessons across a team is a future feature.
- **Replacing the agent's long-term memory.** This tool tracks *operational rules* (don't run X, prefer Y). Conceptual/user-profile memory stays wherever you put it today.

## Open questions

- How to weight multi-workspace patterns? Currently each workspace is scored independently.
- Should lesson text itself get re-written as confidence grows (e.g., "seen 5 times" → "seen 50 times")? Currently static.
- When two lessons have overlapping fingerprints, is merge the right answer or keep both?
