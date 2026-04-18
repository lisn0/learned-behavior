#!/usr/bin/env python3
import sys as _sys
if _sys.version_info < (3, 10):
    _sys.stderr.write("learned-behavior requires Python 3.10+ (detected {}).\n".format(
        ".".join(map(str, _sys.version_info[:3]))))
    _sys.exit(2)

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT_PATH = SCRIPT_PATH.parent
USER_HOME = Path.home()


def _env(*names: str) -> str | None:
    """Return the first environment variable value that is set (supports deprecated aliases)."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


_xdg_data = _env("XDG_DATA_HOME") or str(USER_HOME / ".local" / "share")

LB_HOME = Path(
    _env("LEARNED_BEHAVIOR_HOME", "CONTINUOUS_LEARNING_HOME")
    or str(Path(_xdg_data) / "learned-behavior")
)

DEFAULT_DB_PATH = Path(
    _env("LEARNED_BEHAVIOR_DB", "CONTINUOUS_LEARNING_DB")
    or str(LB_HOME / "learning.db")
)

# Registry: prefer user config, fall back to default that ships with the repo.
_repo_default_registry = REPO_ROOT_PATH / "config" / "default-skill-registry.json"
_user_default_registry = LB_HOME / "config" / "default-skill-registry.json"
DEFAULT_REGISTRY_PATH = _user_default_registry if _user_default_registry.exists() else _repo_default_registry

# Optional legacy DB path (for users upgrading from earlier installs).
# Set LEARNED_BEHAVIOR_LEGACY_DB=/path/to/old.db to auto-migrate on first run.
LEGACY_DB_PATH_STR = _env("LEARNED_BEHAVIOR_LEGACY_DB", "CONTINUOUS_LEARNING_LEGACY_DB")
LEGACY_DB_PATH = Path(LEGACY_DB_PATH_STR) if LEGACY_DB_PATH_STR else None


def _maybe_migrate_db(target: Path) -> None:
    """One-time copy of a legacy DB into the active location, if configured and present."""
    if target.exists() or LEGACY_DB_PATH is None or not LEGACY_DB_PATH.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        import shutil
        shutil.copy2(LEGACY_DB_PATH, target)
    except Exception:
        pass
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "please",
    "run",
    "show",
    "that",
    "the",
    "this",
    "to",
    "use",
    "with",
}
AGENT_ALIASES = {
    "claude": "claude",
    "codex": "claude",
    "copilot": "copilot",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "antigravity": "antigravity",
    "gemini": "gemini",
    "jules": "gemini",
    "aider": "aider",
    "continue": "continue",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Shared continuous learning backend")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    observe = subparsers.add_parser("observe", help="Record a hook or manual event")
    observe.add_argument("--agent", default="claude",
                         help="Agent label for provenance (default: claude). Any string accepted.")
    observe.add_argument("--stdin-json", action="store_true")
    observe.add_argument("--event-name")
    observe.add_argument("--workspace")
    observe.add_argument("--status", choices=("info", "success", "error"))
    observe.add_argument("--summary")
    observe.add_argument("--tool-name")
    observe.add_argument("--prompt")
    observe.add_argument("--session-id")
    observe.add_argument("--source", default="hook")
    observe.add_argument(
        "--output",
        choices=("none", "claude-error-context"),
        default="none",
        help="Optional structured output for hook integrations",
    )

    advice = subparsers.add_parser("advice", help="Print relevant approved lessons")
    advice.add_argument("--agent", default="claude",
                        help="Agent label for provenance (default: claude). Any string accepted.")
    advice.add_argument("--workspace")
    advice.add_argument("--task")
    advice.add_argument("--stdin-json", action="store_true")
    advice.add_argument("--limit", type=int, default=5)
    advice.add_argument(
        "--output",
        choices=("text", "claude-json"),
        default="text",
        help="Output format",
    )
    advice.add_argument(
        "--session-id",
        help="Session id to record advice_shown against (for reinforcement). "
             "If omitted, falls back to stdin payload `session_id`.",
    )

    learn = subparsers.add_parser("learn", help="Persist an approved lesson")
    learn.add_argument("--agent", default="claude",
                       help="Agent label for provenance (default: claude). Any string accepted.")
    learn.add_argument("--workspace", required=True)
    learn.add_argument("--title", required=True)
    learn.add_argument("--rule", required=True)
    learn.add_argument("--rationale", default="")
    learn.add_argument("--event-id", type=int)
    learn.add_argument("--confidence", type=float, default=0.8)

    review = subparsers.add_parser("review", help="Summarize repeated failures and lessons")
    review.add_argument("--workspace", required=True)
    review.add_argument("--days", type=int, default=14)
    review.add_argument("--limit", type=int, default=10)
    review.add_argument("--all", action="store_true",
                        help="Include candidate lessons (default: approved only)")

    init_db = subparsers.add_parser("init-db", help="Create the database schema")
    init_db.add_argument("--workspace", default=str(Path.cwd()))

    mine = subparsers.add_parser(
        "mine",
        help="Cluster historical error events into candidate lessons",
    )
    mine.add_argument("--workspace")
    mine.add_argument("--min-count", type=int, default=3)
    mine.add_argument("--days", type=int, default=90)
    mine.add_argument("--limit", type=int, default=20)
    mine.add_argument("--write", action="store_true", help="Insert candidate lessons")
    mine.add_argument("--global", dest="global_scope", action="store_true",
                      help="Mine across all workspaces (default: current workspace)")

    mine_edits = subparsers.add_parser(
        "mine-edits",
        help="Cluster Edit tool diffs by normalized old_string to surface self-correction",
    )
    mine_edits.add_argument("--workspace")
    mine_edits.add_argument("--min-count", type=int, default=3)
    mine_edits.add_argument("--days", type=int, default=90)
    mine_edits.add_argument("--limit", type=int, default=20)
    mine_edits.add_argument("--global", dest="global_scope", action="store_true")
    mine_edits.add_argument("--write", action="store_true")

    mine_skill = subparsers.add_parser(
        "mine-skill-miss",
        help="Flag Bash commands that should have used a skill",
    )
    mine_skill.add_argument("--workspace")
    mine_skill.add_argument("--days", type=int, default=60)
    mine_skill.add_argument("--min-count", type=int, default=3)
    mine_skill.add_argument("--limit", type=int, default=20)
    mine_skill.add_argument("--global", dest="global_scope", action="store_true")
    mine_skill.add_argument("--write", action="store_true")

    observe_block = subparsers.add_parser(
        "observe-block",
        help="Record a PreToolUse hook block event (called by blocking hooks)",
    )
    observe_block.add_argument("--agent", default="claude", choices=tuple(AGENT_ALIASES))
    observe_block.add_argument("--stdin-json", action="store_true")
    observe_block.add_argument("--rule", required=True,
                               help="Name of the rule that fired (e.g. 'aws-logs-ban')")
    observe_block.add_argument("--reason", default="",
                               help="Human-readable reason for the block")

    mine_blocks = subparsers.add_parser(
        "mine-blocks",
        help="Cluster PreToolUse hook blocks by rule to find noisy guardrails",
    )
    mine_blocks.add_argument("--workspace")
    mine_blocks.add_argument("--days", type=int, default=60)
    mine_blocks.add_argument("--limit", type=int, default=20)
    mine_blocks.add_argument("--global", dest="global_scope", action="store_true")

    session_check = subparsers.add_parser(
        "session-check",
        help="Surface unresolved session errors and prompt the agent to learn",
    )
    session_check.add_argument("--agent", default="claude", choices=tuple(AGENT_ALIASES))
    session_check.add_argument("--stdin-json", action="store_true")
    session_check.add_argument("--session-id")
    session_check.add_argument("--workspace")
    session_check.add_argument(
        "--output",
        choices=("text", "claude-json", "stop-json"),
        default="claude-json",
        help="claude-json: UserPromptSubmit/PostToolUse shape. stop-json: Stop hook shape.",
    )

    promote = subparsers.add_parser(
        "promote",
        help="Promote candidate lessons with enough evidence to approved",
    )
    promote.add_argument("--min-observations", type=int, default=5)
    promote.add_argument("--min-age-days", type=int, default=7)
    promote.add_argument("--min-confidence", type=float, default=0.6)
    promote.add_argument("--workspace", help="Restrict to one workspace (default: all)")
    promote.add_argument("--write", action="store_true",
                         help="Apply promotions (default is dry-run)")

    decay = subparsers.add_parser(
        "decay",
        help="Decay confidence of lessons that have not fired recently; move stale ones to dormant",
    )
    decay.add_argument("--stale-days", type=int, default=60,
                       help="Lessons not seen in this many days are eligible for decay")
    decay.add_argument("--dormant-days", type=int, default=60,
                       help="Lessons not seen in this many days move to dormant status")
    decay.add_argument("--retire-days", type=int, default=180,
                       help="Dormant lessons older than this move to retired (hidden)")
    decay.add_argument("--decay-rate", type=float, default=0.02,
                       help="Per-week confidence drop for stale lessons")
    decay.add_argument("--workspace")
    decay.add_argument("--write", action="store_true",
                       help="Apply changes (default is dry-run)")

    reinforce = subparsers.add_parser(
        "reinforce",
        help="Apply +/- reinforcement to lessons based on whether surfaced advice prevented recurrence",
    )
    reinforce.add_argument("--session-id", required=True)
    reinforce.add_argument("--reinforce-bonus", type=float, default=0.03)
    reinforce.add_argument("--contradict-penalty", type=float, default=0.1)
    reinforce.add_argument("--write", action="store_true",
                           help="Apply changes (default is dry-run)")

    suggest = subparsers.add_parser(
        "suggest-hooks",
        help="Inspect event coverage and suggest missing hook wiring for this workspace",
    )
    suggest.add_argument("--workspace", required=True)
    suggest.add_argument("--days", type=int, default=14)

    suggest_skills = subparsers.add_parser(
        "suggest-skills",
        help="Cluster frequently-run Bash commands not covered by any registered skill pattern",
    )
    suggest_skills.add_argument("--workspace", required=True)
    suggest_skills.add_argument("--days", type=int, default=30)
    suggest_skills.add_argument("--min-count", type=int, default=5)
    suggest_skills.add_argument("--top", type=int, default=10)

    maintain = subparsers.add_parser(
        "maintain",
        help="Rate-limited nightly maintenance: runs promote + decay at most once per interval",
    )
    maintain.add_argument("--min-interval-hours", type=float, default=20.0,
                          help="Skip if the last maintain run was within this many hours")
    maintain.add_argument("--write", action="store_true",
                          help="Apply changes (default is dry-run)")

    return parser.parse_args()


def load_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def canonical_agent(agent: str) -> str:
    """Map an agent label to its canonical form. Unknown labels pass through unchanged."""
    return AGENT_ALIASES.get(agent, agent)


def parse_possible_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def repo_root_for(path_value: str | None) -> str:
    candidate = Path(path_value or Path.cwd()).expanduser().resolve()
    current = candidate if candidate.is_dir() else candidate.parent
    for root in (current, *current.parents):
        if (root / ".git").exists():
            return str(root)
    return str(candidate if candidate.is_dir() else candidate.parent)


def ensure_db(conn: sqlite3.Connection) -> None:
    schema = """
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        agent TEXT NOT NULL,
        source TEXT NOT NULL,
        workspace TEXT NOT NULL,
        event_name TEXT NOT NULL,
        status TEXT NOT NULL,
        session_id TEXT,
        tool_name TEXT,
        prompt TEXT,
        summary TEXT,
        fingerprint TEXT,
        payload_json TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_workspace_created
        ON events(workspace, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_events_workspace_fingerprint
        ON events(workspace, fingerprint);

    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        workspace TEXT NOT NULL,
        status TEXT NOT NULL,
        agent TEXT NOT NULL,
        title TEXT NOT NULL,
        rule_text TEXT NOT NULL,
        rationale TEXT,
        source_event_id INTEGER,
        fingerprint TEXT,
        confidence REAL NOT NULL,
        observations INTEGER NOT NULL DEFAULT 1,
        approvals INTEGER NOT NULL DEFAULT 0,
        last_seen_at TEXT NOT NULL,
        UNIQUE(workspace, title, rule_text)
    );

    CREATE INDEX IF NOT EXISTS idx_lessons_workspace_status
        ON lessons(workspace, status, updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_lessons_workspace_fingerprint
        ON lessons(workspace, fingerprint);

    CREATE TABLE IF NOT EXISTS advice_shown (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shown_at TEXT NOT NULL,
        session_id TEXT,
        workspace TEXT NOT NULL,
        lesson_id INTEGER NOT NULL,
        fingerprint TEXT,
        processed INTEGER NOT NULL DEFAULT 0,
        outcome TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_advice_session ON advice_shown(session_id, processed);
    """
    migrations = (
        "ALTER TABLE lessons ADD COLUMN reinforcements INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE lessons ADD COLUMN contradictions INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE lessons ADD COLUMN last_contradicted_at TEXT",
    )
    for attempt in range(5):
        try:
            conn.executescript(schema)
            for stmt in migrations:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            conn.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def connect_db(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path).expanduser().resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    _maybe_migrate_db(db_file)
    conn = sqlite3.connect(db_file, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    ensure_db(conn)
    return conn


def truncate(value: str | None, limit: int = 220) -> str:
    if not value:
        return ""
    compact = " ".join(str(value).split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1]}…"


def tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return {token for token in cleaned.split() if len(token) > 2 and token not in STOPWORDS}


def normalize_text(text: str) -> str:
    return " ".join(sorted(tokenize(text)))


_RE_RERUN = re.compile(r"\[rerun:\s*[0-9a-f]+\]", re.IGNORECASE)
_RE_ABSPATH = re.compile(r"(?:/[\w.\-]+){2,}")
_RE_HOMEPATH = re.compile(r"~/[\w./\-]+")
_RE_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_RE_NUM = re.compile(r"\b\d+\b")
_RE_LINENO = re.compile(r":\d+(?::\d+)?\b")
_RE_WS = re.compile(r"\s+")


def normalize_error_text(text: str | None, limit: int = 240) -> str:
    """Strip variable parts from error text so structurally similar errors cluster."""
    if not text:
        return ""
    t = str(text)
    t = _RE_RERUN.sub("", t)
    t = _RE_ABSPATH.sub("<path>", t)
    t = _RE_HOMEPATH.sub("<path>", t)
    t = _RE_LINENO.sub(":<n>", t)
    t = _RE_HEX.sub("<hex>", t)
    t = _RE_NUM.sub("<n>", t)
    t = _RE_WS.sub(" ", t).strip().lower()
    return t[:limit]


def fingerprint_for(tool_name: str | None, summary: str, details: Any) -> str | None:
    error_raw = ""
    if isinstance(details, dict):
        error_raw = details.get("error") or ""
        if not error_raw and isinstance(details.get("tool_result"), dict):
            tr = details["tool_result"]
            error_raw = tr.get("stderr") or tr.get("error") or tr.get("message") or ""
    normalized_error = normalize_error_text(error_raw)
    material = " | ".join(
        part
        for part in [
            tool_name or "",
            normalized_error,
            normalize_text(summary) if not normalized_error else "",
        ]
        if part
    )
    if not material:
        return None
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def first_line(value: Any) -> str:
    if isinstance(value, str):
        return truncate(value.splitlines()[0])
    return ""


def summarize_tool_event(tool_name: str | None, tool_args: Any, tool_result: Any, event_name: str) -> str:
    if tool_name in {"Bash", "bash"}:
        command = ""
        if isinstance(tool_args, dict):
            command = tool_args.get("command") or tool_args.get("description") or ""
        exit_code = None
        if isinstance(tool_result, dict):
            exit_code = tool_result.get("exit_code")
            if exit_code is None:
                exit_code = tool_result.get("exitCode")
        suffix = f" -> exit {exit_code}" if exit_code not in (None, "") else ""
        return truncate(f"{command}{suffix}")
    if isinstance(tool_args, dict):
        for key in ("file_path", "path", "description"):
            if tool_args.get(key):
                return truncate(f"{tool_name} {tool_args[key]}")
    if isinstance(tool_result, dict):
        for key in ("error", "stderr", "message"):
            if tool_result.get(key):
                return truncate(f"{tool_name} {first_line(tool_result.get(key))}")
    return truncate(f"{tool_name or event_name} event")


def derive_status(event_name: str, tool_result: Any, payload: dict[str, Any]) -> str:
    lowered = event_name.lower()
    if lowered in {"erroroccurred", "posttoolusefailure"}:
        return "error"
    if lowered in {"sessionstart", "sessionend", "userpromptsubmitted", "userpromptsubmit"}:
        return "info"
    if isinstance(tool_result, dict):
        exit_code = tool_result.get("exit_code")
        if exit_code is None:
            exit_code = tool_result.get("exitCode")
        if isinstance(exit_code, int) and exit_code != 0:
            return "error"
        if tool_result.get("success") is False or tool_result.get("ok") is False:
            return "error"
        if tool_result.get("error"):
            return "error"
    if payload.get("error"):
        return "error"
    return "success"


def infer_event_name(agent: str, payload: dict[str, Any], fallback: str | None) -> str:
    if fallback:
        return fallback
    if agent == "claude":
        return payload.get("hook_event_name", "Unknown")
    if "toolResult" in payload:
        return "postToolUse"
    if "toolArgs" in payload:
        return "preToolUse"
    if "error" in payload:
        return "errorOccurred"
    if "initialPrompt" in payload:
        return "sessionStart"
    if "reason" in payload:
        return "sessionEnd"
    if "prompt" in payload:
        return "userPromptSubmitted"
    return "unknown"


def normalize_event(agent: str, payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    tool_args = payload.get("tool_input")
    if tool_args is None:
        tool_args = payload.get("toolArgs")
    tool_args = parse_possible_json(tool_args)

    tool_result = payload.get("tool_response")
    if tool_result is None:
        tool_result = payload.get("toolResult")
    tool_result = parse_possible_json(tool_result)

    tool_name = args.tool_name or payload.get("tool_name") or payload.get("toolName")
    event_name = infer_event_name(agent, payload, args.event_name)
    workspace = repo_root_for(args.workspace or payload.get("cwd"))
    prompt = args.prompt or payload.get("prompt") or payload.get("initialPrompt") or None
    status = args.status or derive_status(event_name, tool_result, payload)

    if args.summary:
        summary = args.summary
    elif prompt and event_name.lower() in {"sessionstart", "userpromptsubmitted", "userpromptsubmit"}:
        summary = truncate(prompt)
    elif status == "error":
        summary = truncate(
            first_line(payload.get("error"))
            or first_line((tool_result or {}).get("stderr") if isinstance(tool_result, dict) else "")
            or first_line((tool_result or {}).get("error") if isinstance(tool_result, dict) else "")
            or summarize_tool_event(tool_name, tool_args, tool_result, event_name)
        )
    else:
        summary = summarize_tool_event(tool_name, tool_args, tool_result, event_name)

    details = {
        "tool_args": tool_args,
        "tool_result": tool_result,
        "error": payload.get("error"),
        "reason": payload.get("reason"),
        "source": payload.get("source"),
    }
    fingerprint = None
    if status == "error":
        fingerprint = fingerprint_for(tool_name, summary, details)

    return {
        "created_at": utc_now(),
        "agent": agent,
        "source": args.source,
        "workspace": workspace,
        "event_name": event_name,
        "status": status,
        "session_id": args.session_id or payload.get("session_id"),
        "tool_name": tool_name,
        "prompt": prompt,
        "summary": summary,
        "fingerprint": fingerprint,
        "payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=True),
    }


def insert_event(conn: sqlite3.Connection, event: dict[str, Any]) -> int:
    cursor = conn.execute(
        """
        INSERT INTO events (
            created_at, agent, source, workspace, event_name, status,
            session_id, tool_name, prompt, summary, fingerprint, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["created_at"],
            event["agent"],
            event["source"],
            event["workspace"],
            event["event_name"],
            event["status"],
            event["session_id"],
            event["tool_name"],
            event["prompt"],
            event["summary"],
            event["fingerprint"],
            event["payload_json"],
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def build_candidate_title(tool_name: str | None, summary: str) -> str:
    label = truncate(summary, 90) or "repeated failure"
    prefix = tool_name or "Tool"
    return truncate(f"{prefix}: {label}", 110)


def build_candidate_rule(tool_name: str | None, summary: str) -> str:
    if tool_name in {"Bash", "bash"}:
        return truncate(
            f"When this shell failure reappears ({summary}), inspect the previous stderr and environment state before retrying blindly.",
            220,
        )
    return truncate(
        f"When this {tool_name or 'tool'} failure reappears ({summary}), inspect the previous failing payload and document the root cause once fixed.",
        220,
    )


def maybe_upsert_candidate_lesson(conn: sqlite3.Connection, event_id: int, event: dict[str, Any]) -> None:
    fingerprint = event.get("fingerprint")
    if event.get("status") != "error" or not fingerprint:
        return

    count_row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM events
        WHERE workspace = ? AND fingerprint = ? AND status = 'error'
        """,
        (event["workspace"], fingerprint),
    ).fetchone()
    repeats = int(count_row["count"])
    if repeats < 2:
        return

    title = build_candidate_title(event.get("tool_name"), event.get("summary") or "")
    rule_text = build_candidate_rule(event.get("tool_name"), event.get("summary") or "")
    confidence = min(0.35 + (repeats - 2) * 0.1, 0.75)
    now = utc_now()

    existing = conn.execute(
        """
        SELECT id FROM lessons
        WHERE workspace = ? AND fingerprint = ? AND status = 'candidate'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (event["workspace"], fingerprint),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE lessons
            SET updated_at = ?, observations = ?, confidence = ?, last_seen_at = ?, source_event_id = ?
            WHERE id = ?
            """,
            (now, repeats, confidence, now, event_id, int(existing["id"])),
        )
    else:
        conn.execute(
            """
            INSERT INTO lessons (
                created_at, updated_at, workspace, status, agent, title, rule_text, rationale,
                source_event_id, fingerprint, confidence, observations, approvals, last_seen_at
            ) VALUES (?, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                now,
                now,
                event["workspace"],
                event["agent"],
                title,
                rule_text,
                f"Auto-created after {repeats} matching failures.",
                event_id,
                fingerprint,
                confidence,
                repeats,
                now,
            ),
        )
    conn.commit()


def fetch_approved_lessons(conn: sqlite3.Connection, workspace: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE workspace = ? AND status = 'approved'
        ORDER BY confidence DESC, observations DESC, updated_at DESC
        """,
        (workspace,),
    ).fetchall()


def fetch_matching_lessons(
    conn: sqlite3.Connection, workspace: str, fingerprint: str | None, tool_name: str | None
) -> list[sqlite3.Row]:
    if fingerprint:
        direct = conn.execute(
            """
            SELECT *
            FROM lessons
            WHERE workspace = ? AND status = 'approved' AND fingerprint = ?
            ORDER BY confidence DESC, observations DESC, updated_at DESC
            """,
            (workspace, fingerprint),
        ).fetchall()
        if direct:
            return direct

    if not tool_name:
        return []

    wildcard = f"%{tool_name.lower()}%"
    return conn.execute(
        """
        SELECT *
        FROM lessons
        WHERE workspace = ?
          AND status = 'approved'
          AND (lower(title) LIKE ? OR lower(rule_text) LIKE ? OR lower(COALESCE(rationale, '')) LIKE ?)
        ORDER BY confidence DESC, observations DESC, updated_at DESC
        LIMIT 3
        """,
        (workspace, wildcard, wildcard, wildcard),
    ).fetchall()


def score_lesson(lesson: sqlite3.Row, prompt: str | None) -> tuple[float, str]:
    haystack = " ".join(
        part for part in [lesson["title"], lesson["rule_text"], lesson["rationale"] or ""] if part
    )
    if not prompt:
        return (float(lesson["confidence"]) + lesson["observations"] * 0.05, haystack)

    prompt_tokens = tokenize(prompt)
    lesson_tokens = tokenize(haystack)
    overlap = len(prompt_tokens & lesson_tokens)
    score = overlap * 10 + float(lesson["confidence"]) + lesson["observations"] * 0.05
    return (score, haystack)


def select_relevant_lessons(
    conn: sqlite3.Connection, workspace: str, prompt: str | None, limit: int
) -> list[sqlite3.Row]:
    approved = fetch_approved_lessons(conn, workspace)
    ranked = sorted(approved, key=lambda lesson: score_lesson(lesson, prompt), reverse=True)
    if prompt:
        prompt_tokens = tokenize(prompt)
        ranked = [
            lesson
            for lesson in ranked
            if prompt_tokens & tokenize(" ".join([lesson["title"], lesson["rule_text"], lesson["rationale"] or ""]))
        ] or ranked
    return ranked[:limit]


def format_lessons(lessons: list[sqlite3.Row], heading: str) -> str:
    lines = [heading]
    for lesson in lessons:
        rationale = truncate(lesson["rationale"], 120)
        rule_line = truncate(lesson["rule_text"], 180)
        lines.append(
            f"- {lesson['title']}: {rule_line}"
            + (f" Rationale: {rationale}" if rationale else "")
        )
    return "\n".join(lines)


def build_claude_error_context(
    conn: sqlite3.Connection, workspace: str, event_id: int, event: dict[str, Any]
) -> str | None:
    matches = fetch_matching_lessons(conn, workspace, event.get("fingerprint"), event.get("tool_name"))
    if matches:
        return format_lessons(matches[:3], "Relevant learned lessons:")

    if not event.get("fingerprint"):
        return None

    repeats = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM events
        WHERE workspace = ? AND fingerprint = ? AND status = 'error'
        """,
        (workspace, event["fingerprint"]),
    ).fetchone()
    count = int(repeats["count"])
    if count < 2:
        return None

    return (
        f"This failure pattern has appeared {count} times in the shared learning DB. "
        f"If you resolve it, persist a durable lesson with:\n"
        f"python3 {SCRIPT_PATH} learn --agent {event['agent']} --workspace {workspace} "
        f"--event-id {event_id} --title \"<short lesson title>\" --rule \"<actionable rule>\" "
        f"--rationale \"<root cause and signal>\""
    )


def command_observe(args: argparse.Namespace) -> int:
    payload = load_stdin_json() if args.stdin_json else {}
    event = normalize_event(args.agent, payload, args)
    conn = connect_db(args.db)
    event_id = insert_event(conn, event)
    maybe_upsert_candidate_lesson(conn, event_id, event)

    if args.output == "claude-error-context" and args.agent == "claude" and event["status"] == "error":
        context = build_claude_error_context(conn, event["workspace"], event_id, event)
        if context:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUseFailure",
                            "additionalContext": context,
                        }
                    }
                )
            )
    return 0


def command_advice(args: argparse.Namespace) -> int:
    payload = load_stdin_json() if args.stdin_json else {}
    workspace = repo_root_for(args.workspace or payload.get("cwd"))
    prompt = args.task or payload.get("prompt") or payload.get("initialPrompt")
    conn = connect_db(args.db)
    lessons = select_relevant_lessons(conn, workspace, prompt, args.limit)
    if not lessons:
        return 0

    session_id = getattr(args, "session_id", None) or payload.get("session_id")
    if session_id:
        now = utc_now()
        conn.executemany(
            "INSERT INTO advice_shown (shown_at, session_id, workspace, lesson_id, fingerprint) "
            "VALUES (?, ?, ?, ?, ?)",
            [(now, session_id, workspace, lesson["id"], lesson["fingerprint"]) for lesson in lessons],
        )
        conn.commit()

    text = format_lessons(lessons, "Relevant lessons from the shared learning DB:")
    if args.output == "claude-json":
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": text,
                    }
                }
            )
        )
        return 0

    print(text)
    return 0


def command_learn(args: argparse.Namespace) -> int:
    workspace = repo_root_for(args.workspace)
    conn = connect_db(args.db)
    now = utc_now()
    fingerprint = None
    source_event_id = args.event_id

    if args.event_id:
        event = conn.execute(
            "SELECT fingerprint FROM events WHERE id = ? AND workspace = ?",
            (args.event_id, workspace),
        ).fetchone()
        if event:
            fingerprint = event["fingerprint"]

    existing = conn.execute(
        """
        SELECT id
        FROM lessons
        WHERE workspace = ? AND title = ? AND rule_text = ?
        LIMIT 1
        """,
        (workspace, args.title, args.rule),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE lessons
            SET updated_at = ?, status = 'approved', rationale = ?, confidence = ?,
                source_event_id = COALESCE(source_event_id, ?), fingerprint = COALESCE(fingerprint, ?),
                agent = ?, approvals = approvals + 1, last_seen_at = ?, observations = observations + 1
            WHERE id = ?
            """,
            (
                now,
                args.rationale,
                args.confidence,
                source_event_id,
                fingerprint,
                args.agent,
                now,
                int(existing["id"]),
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO lessons (
                created_at, updated_at, workspace, status, agent, title, rule_text, rationale,
                source_event_id, fingerprint, confidence, observations, approvals, last_seen_at
            ) VALUES (?, ?, ?, 'approved', ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
            """,
            (
                now,
                now,
                workspace,
                args.agent,
                args.title,
                args.rule,
                args.rationale,
                source_event_id,
                fingerprint,
                args.confidence,
                now,
            ),
        )

    conn.commit()
    print(f"Saved approved lesson for {workspace}")
    return 0


def command_review(args: argparse.Namespace) -> int:
    workspace = repo_root_for(args.workspace)
    conn = connect_db(args.db)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).replace(microsecond=0).isoformat()

    repeated = conn.execute(
        """
        SELECT fingerprint, tool_name, summary, COUNT(*) AS count, MAX(created_at) AS last_seen
        FROM events
        WHERE workspace = ? AND status = 'error' AND created_at >= ? AND fingerprint IS NOT NULL
        GROUP BY fingerprint, tool_name, summary
        HAVING COUNT(*) >= 2
        ORDER BY count DESC, last_seen DESC
        LIMIT ?
        """,
        (workspace, since, args.limit),
    ).fetchall()

    status_clause = "" if args.all else "AND status = 'approved'"
    lessons = conn.execute(
        f"""
        SELECT status, title, rule_text, confidence, observations, updated_at
        FROM lessons
        WHERE workspace = ? {status_clause}
        ORDER BY
            CASE status WHEN 'approved' THEN 0 ELSE 1 END,
            updated_at DESC
        LIMIT ?
        """,
        (workspace, args.limit),
    ).fetchall()

    lines = [f"Continuous learning review for {workspace}"]
    filtered = [r for r in repeated if not _is_noise(normalize_error_text(r["summary"] or ""))]
    if filtered:
        lines.append("")
        lines.append("Repeated failures:")
        for row in filtered:
            lines.append(
                f"- {row['count']}x {row['tool_name'] or 'tool'}: {truncate(row['summary'], 140)} "
                f"(last seen {row['last_seen']})"
            )
    if lessons:
        lines.append("")
        lines.append("Stored lessons:")
        for row in lessons:
            lines.append(
                f"- [{row['status']}] {row['title']}: {truncate(row['rule_text'], 150)} "
                f"(confidence {row['confidence']:.2f}, observations {row['observations']})"
            )

    print("\n".join(lines))
    return 0


def command_init_db(args: argparse.Namespace) -> int:
    connect_db(args.db).close()
    print(f"Initialized shared learning DB at {Path(args.db).expanduser().resolve()}")
    return 0


_NOISE_PATTERNS = (
    "exit code <n>",
    "file content (<n> tokens) exceeds maximum",
    "file does not exist. note: your current working directory",
    "request failed with status code <n>",
    "ripgrep search timed out",
    "command terminated with exit code <n>",
)


def _is_noise(normalized: str) -> bool:
    if not normalized:
        return True
    stripped = normalized.strip()
    if stripped in {"exit code <n>", "<path>", "<n>", ""}:
        return True
    for pattern in _NOISE_PATTERNS:
        if stripped == pattern:
            return True
    if len(stripped) < 25:
        return True
    # Read tool token-limit errors: no useful signal, just resource limit
    if "exceeds maximum allowed tokens" in stripped:
        return True
    # Read tool "file does not exist" errors: usually path typos, not durable
    if stripped.startswith("file does not exist."):
        return True
    # Pure HTTP errors with no other content
    if stripped.startswith("request failed with status code") and len(stripped) < 45:
        return True
    return False


def _cluster_error_events(
    conn: sqlite3.Connection, workspace: str | None, since_iso: str
) -> list[dict[str, Any]]:
    """Group error events by the new normalized-error key. Returns clusters sorted by count."""
    where = ["status = 'error'", "created_at >= ?"]
    params: list[Any] = [since_iso]
    if workspace:
        where.append("workspace = ?")
        params.append(workspace)
    query = f"""
        SELECT id, workspace, tool_name, summary, payload_json, created_at
        FROM events
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
    """
    rows = conn.execute(query, params).fetchall()

    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        error_text = payload.get("error") or ""
        if not error_text and isinstance(payload.get("tool_response"), dict):
            tr = payload["tool_response"]
            error_text = tr.get("stderr") or tr.get("error") or tr.get("message") or ""
        key_tool = row["tool_name"] or "?"
        key_err = normalize_error_text(error_text, limit=240)
        if not key_err:
            key_err = normalize_text(row["summary"] or "")
        if _is_noise(key_err):
            continue
        key = f"{key_tool}|{key_err}"
        bucket = clusters.setdefault(
            key,
            {
                "tool": key_tool,
                "normalized": key_err,
                "count": 0,
                "example_id": row["id"],
                "example_cmd": (payload.get("tool_input") or {}).get("command")
                if isinstance(payload.get("tool_input"), dict)
                else None,
                "example_error": error_text[:400],
                "last_seen": row["created_at"],
                "workspaces": set(),
            },
        )
        bucket["count"] += 1
        bucket["workspaces"].add(row["workspace"])

    ordered = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)
    for c in ordered:
        c["workspaces"] = sorted(c["workspaces"])
    return ordered


def _suggest_lesson(cluster: dict[str, Any]) -> dict[str, str]:
    tool = cluster["tool"]
    err = cluster["normalized"]
    snippet = err[:110]
    title = truncate(f"{tool}: {snippet}", 110)
    rule = truncate(
        f"When this {tool} failure pattern reappears ({snippet}), "
        "identify the root cause and document a real fix (do not retry blindly).",
        240,
    )
    return {"title": title, "rule": rule}


def command_mine(args: argparse.Namespace) -> int:
    workspace = None if args.global_scope else repo_root_for(args.workspace)
    conn = connect_db(args.db)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).replace(microsecond=0).isoformat()
    clusters = _cluster_error_events(conn, workspace, since)
    clusters = [c for c in clusters if c["count"] >= args.min_count]
    clusters = clusters[: args.limit]

    if not clusters:
        scope = "all workspaces" if args.global_scope else (workspace or "")
        print(f"No error clusters with count >= {args.min_count} in last {args.days} days for {scope}.")
        return 0

    now = utc_now()
    wrote = 0
    scope_label = "all workspaces" if args.global_scope else workspace
    print(f"Error clusters (>= {args.min_count} occurrences, last {args.days}d) for {scope_label}:\n")
    for cluster in clusters:
        suggestion = _suggest_lesson(cluster)
        ws = cluster["workspaces"]
        ws_repr = ws[0] if len(ws) == 1 else f"{len(ws)} worktrees"
        print(f"[{cluster['count']}x] {cluster['tool']} — {truncate(cluster['normalized'], 140)}")
        print(f"   example cmd: {truncate(cluster['example_cmd'] or '', 160)}")
        print(f"   example err: {truncate(cluster['example_error'], 200)}")
        print(f"   workspaces : {ws_repr}")
        print(f"   last seen  : {cluster['last_seen']}")
        print(f"   suggested  : {suggestion['title']}")
        print()

        if args.write:
            target_ws = ws[0] if len(ws) == 1 else (workspace or ws[0])
            fingerprint = hashlib.sha256(
                f"{cluster['tool']}|{cluster['normalized']}".encode("utf-8")
            ).hexdigest()
            existing = conn.execute(
                """
                SELECT id FROM lessons
                WHERE workspace = ? AND fingerprint = ?
                LIMIT 1
                """,
                (target_ws, fingerprint),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO lessons (
                    created_at, updated_at, workspace, status, agent, title, rule_text,
                    rationale, source_event_id, fingerprint, confidence, observations,
                    approvals, last_seen_at
                ) VALUES (?, ?, ?, 'candidate', 'claude', ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    now,
                    now,
                    target_ws,
                    suggestion["title"],
                    suggestion["rule"],
                    f"Mined from {cluster['count']} matching errors across {ws_repr}.",
                    cluster["example_id"],
                    fingerprint,
                    min(0.35 + (cluster["count"] - 2) * 0.05, 0.75),
                    cluster["count"],
                    now,
                ),
            )
            wrote += 1
    if args.write:
        conn.commit()
        print(f"Inserted {wrote} candidate lesson(s).")
    else:
        print("Re-run with --write to persist these as candidate lessons.")
    return 0


# ----------------------------------------------------------------------------
# mine-edits: cluster Edit tool diffs to surface recurring self-corrections
# ----------------------------------------------------------------------------

_RE_EDIT_NORM = re.compile(r"\s+")


def _normalize_edit_snippet(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    t = _RE_EDIT_NORM.sub(" ", str(text)).strip()
    return t[:limit]


def command_mine_edits(args: argparse.Namespace) -> int:
    workspace = None if args.global_scope else repo_root_for(args.workspace)
    conn = connect_db(args.db)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).replace(microsecond=0).isoformat()
    where = ["tool_name = 'Edit'", "created_at >= ?"]
    params: list[Any] = [since]
    if workspace:
        where.append("workspace = ?")
        params.append(workspace)
    rows = conn.execute(
        f"""
        SELECT id, workspace, payload_json, created_at
        FROM events
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        """,
        params,
    ).fetchall()

    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        ti = payload.get("tool_input") or {}
        old_s = ti.get("old_string") or ""
        new_s = ti.get("new_string") or ""
        if not old_s or old_s == new_s:
            continue
        key_old = _normalize_edit_snippet(old_s, 100)
        if len(key_old) < 12:
            continue
        key = key_old
        bucket = clusters.setdefault(
            key,
            {
                "old": key_old,
                "example_new": _normalize_edit_snippet(new_s, 160),
                "example_id": row["id"],
                "count": 0,
                "files": set(),
                "workspaces": set(),
                "last_seen": row["created_at"],
            },
        )
        bucket["count"] += 1
        file_path = ti.get("file_path") or ""
        if file_path:
            bucket["files"].add(file_path)
        bucket["workspaces"].add(row["workspace"])

    ordered = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)
    ordered = [c for c in ordered if c["count"] >= args.min_count]
    ordered = ordered[: args.limit]

    if not ordered:
        scope = "all workspaces" if args.global_scope else (workspace or "")
        print(f"No Edit clusters >= {args.min_count} in last {args.days}d for {scope}.")
        return 0

    now = utc_now()
    wrote = 0
    scope_label = "all workspaces" if args.global_scope else workspace
    print(f"Edit self-correction clusters (>= {args.min_count}x, last {args.days}d) for {scope_label}:\n")
    for c in ordered:
        files_repr = f"{len(c['files'])} file(s)" if len(c["files"]) != 1 else next(iter(c["files"]))
        print(f"[{c['count']}x] replaced: {truncate(c['old'], 110)}")
        print(f"   with       : {truncate(c['example_new'], 140)}")
        print(f"   files      : {files_repr}")
        print(f"   last seen  : {c['last_seen']}")
        print()

        if args.write:
            target_ws = next(iter(c["workspaces"])) if len(c["workspaces"]) == 1 else (workspace or next(iter(c["workspaces"])))
            fingerprint = hashlib.sha256(f"edit|{c['old']}".encode("utf-8")).hexdigest()
            existing = conn.execute(
                "SELECT id FROM lessons WHERE workspace = ? AND fingerprint = ? LIMIT 1",
                (target_ws, fingerprint),
            ).fetchone()
            if existing:
                continue
            title = truncate(f"Edit: recurring replacement of '{c['old'][:60]}'", 110)
            rule = truncate(
                f"Before writing code, avoid the pattern '{c['old'][:80]}'. "
                f"Prefer the corrected form (see example). Self-corrected {c['count']} times.",
                240,
            )
            conn.execute(
                """
                INSERT INTO lessons (
                    created_at, updated_at, workspace, status, agent, title, rule_text,
                    rationale, source_event_id, fingerprint, confidence, observations,
                    approvals, last_seen_at
                ) VALUES (?, ?, ?, 'candidate', 'claude', ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    now, now, target_ws, title, rule,
                    f"Mined from {c['count']} Edit self-corrections across {len(c['files'])} file(s).",
                    c["example_id"], fingerprint,
                    min(0.3 + (c["count"] - 2) * 0.05, 0.7),
                    c["count"], now,
                ),
            )
            wrote += 1
    if args.write:
        conn.commit()
        print(f"Inserted {wrote} candidate lesson(s).")
    else:
        print("Re-run with --write to persist.")
    return 0


# ----------------------------------------------------------------------------
# mine-skill-miss: flag Bash commands that bypass a dedicated skill
# ----------------------------------------------------------------------------

# Skill registry is now loaded from config files (per-project + user default),
# not hardcoded. See load_skill_registry().

def _compile_registry_entries(raw: Any) -> list[tuple[re.Pattern[str], str, str]]:
    """Compile a list of {pattern, skill, reason} dicts into regex tuples."""
    out: list[tuple[re.Pattern[str], str, str]] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        pat = entry.get("pattern")
        skill = entry.get("skill")
        reason = entry.get("reason", "")
        if not pat or not skill:
            continue
        try:
            out.append((re.compile(pat), str(skill), str(reason)))
        except re.error:
            continue
    return out


def load_skill_registry(workspace: str | None) -> list[tuple[re.Pattern[str], str, str]]:
    """Load per-project + user default skill registry.

    Precedence: per-project config first, then user default appended (deduped by skill).
    """
    entries: list[tuple[re.Pattern[str], str, str]] = []
    seen_skills: set[str] = set()

    def _load_from(path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for item in _compile_registry_entries(data.get("skill_registry")):
            if item[1] in seen_skills:
                continue
            seen_skills.add(item[1])
            entries.append(item)

    if workspace:
        _load_from(Path(workspace) / ".claude" / "continuous-learning.json")
    _load_from(DEFAULT_REGISTRY_PATH)
    return entries


def command_mine_skill_miss(args: argparse.Namespace) -> int:
    workspace = None if args.global_scope else repo_root_for(args.workspace)
    conn = connect_db(args.db)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).replace(microsecond=0).isoformat()
    where = ["tool_name = 'Bash'", "created_at >= ?"]
    params: list[Any] = [since]
    if workspace:
        where.append("workspace = ?")
        params.append(workspace)
    rows = conn.execute(
        f"""
        SELECT id, workspace, payload_json, created_at
        FROM events
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        """,
        params,
    ).fetchall()

    # Cache compiled registries per workspace so --global picks up each repo's rules.
    registry_cache: dict[str, list[tuple[re.Pattern[str], str, str]]] = {}

    def _registry_for(ws: str | None) -> list[tuple[re.Pattern[str], str, str]]:
        key = ws or ""
        if key not in registry_cache:
            registry_cache[key] = load_skill_registry(ws)
        return registry_cache[key]

    hits: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        cmd = ((payload.get("tool_input") or {}).get("command") or "").strip()
        if not cmd:
            continue
        for regex, skill, reason in _registry_for(row["workspace"]):
            if regex.search(cmd):
                bucket = hits.setdefault(
                    skill,
                    {
                        "skill": skill,
                        "reason": reason,
                        "count": 0,
                        "example_cmd": cmd,
                        "example_id": row["id"],
                        "workspaces": set(),
                        "last_seen": row["created_at"],
                    },
                )
                bucket["count"] += 1
                bucket["workspaces"].add(row["workspace"])
                break

    ordered = sorted(hits.values(), key=lambda b: b["count"], reverse=True)
    ordered = [b for b in ordered if b["count"] >= args.min_count][: args.limit]

    if not ordered:
        scope = "all workspaces" if args.global_scope else (workspace or "")
        print(f"No skill-miss clusters >= {args.min_count} in last {args.days}d for {scope}.")
        return 0

    now = utc_now()
    wrote = 0
    print(f"Skill non-usage clusters (>= {args.min_count}x, last {args.days}d):\n")
    for b in ordered:
        print(f"[{b['count']}x] {b['skill']}: {b['reason']}")
        print(f"   example cmd: {truncate(b['example_cmd'], 180)}")
        print(f"   workspaces : {len(b['workspaces'])}")
        print(f"   last seen  : {b['last_seen']}")
        print()
        if args.write:
            target_ws = (workspace or next(iter(b["workspaces"])))
            fingerprint = hashlib.sha256(f"skill-miss|{b['skill']}".encode("utf-8")).hexdigest()
            existing = conn.execute(
                "SELECT id FROM lessons WHERE workspace = ? AND fingerprint = ? LIMIT 1",
                (target_ws, fingerprint),
            ).fetchone()
            if existing:
                continue
            title = truncate(f"Use {b['skill']} skill instead of raw Bash", 110)
            rule = truncate(f"{b['reason']}. Detected {b['count']} bypasses.", 240)
            conn.execute(
                """
                INSERT INTO lessons (
                    created_at, updated_at, workspace, status, agent, title, rule_text,
                    rationale, source_event_id, fingerprint, confidence, observations,
                    approvals, last_seen_at
                ) VALUES (?, ?, ?, 'candidate', 'claude', ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    now, now, target_ws, title, rule,
                    f"Mined from {b['count']} Bash commands matching skill pattern '{b['skill']}'.",
                    b["example_id"], fingerprint,
                    min(0.4 + (b["count"] - 2) * 0.05, 0.8),
                    b["count"], now,
                ),
            )
            wrote += 1
    if args.write:
        conn.commit()
        print(f"Inserted {wrote} candidate lesson(s).")
    else:
        print("Re-run with --write to persist.")
    return 0


# ----------------------------------------------------------------------------
# observe-block / mine-blocks: record PreToolUse blocks from guardrail hooks
# ----------------------------------------------------------------------------

def command_observe_block(args: argparse.Namespace) -> int:
    payload = load_stdin_json() if args.stdin_json else {}
    cmd = ""
    if isinstance(payload.get("tool_input"), dict):
        cmd = payload["tool_input"].get("command") or ""
    workspace = repo_root_for(payload.get("cwd"))
    session_id = payload.get("session_id") or payload.get("sessionId")
    event = {
        "created_at": utc_now(),
        "agent": canonical_agent(args.agent),
        "source": "hook",
        "workspace": workspace,
        "event_name": "PreToolUseBlock",
        "status": "blocked",
        "session_id": session_id,
        "tool_name": payload.get("tool_name") or "Bash",
        "prompt": None,
        "summary": truncate(f"blocked[{args.rule}]: {cmd}", 220),
        "fingerprint": hashlib.sha256(f"block|{args.rule}".encode("utf-8")).hexdigest(),
        "payload_json": json.dumps(
            {
                "rule": args.rule,
                "reason": args.reason,
                "command": cmd,
                "session_id": session_id,
                "cwd": workspace,
            },
            sort_keys=True,
            ensure_ascii=True,
        ),
    }
    conn = connect_db(args.db)
    insert_event(conn, event)
    return 0


def command_mine_blocks(args: argparse.Namespace) -> int:
    workspace = None if args.global_scope else repo_root_for(args.workspace)
    conn = connect_db(args.db)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).replace(microsecond=0).isoformat()
    where = ["event_name = 'PreToolUseBlock'", "created_at >= ?"]
    params: list[Any] = [since]
    if workspace:
        where.append("workspace = ?")
        params.append(workspace)
    rows = conn.execute(
        f"""
        SELECT payload_json, workspace, created_at
        FROM events
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        """,
        params,
    ).fetchall()

    by_rule: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            p = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        rule = p.get("rule") or "unknown"
        b = by_rule.setdefault(
            rule,
            {
                "rule": rule,
                "count": 0,
                "example_cmd": p.get("command") or "",
                "reason": p.get("reason") or "",
                "workspaces": set(),
                "last_seen": row["created_at"],
            },
        )
        b["count"] += 1
        b["workspaces"].add(row["workspace"])

    ordered = sorted(by_rule.values(), key=lambda b: b["count"], reverse=True)[: args.limit]
    if not ordered:
        scope = "all workspaces" if args.global_scope else (workspace or "")
        print(f"No PreToolUse blocks recorded in last {args.days}d for {scope}.")
        print("Tip: wire guardrail hooks to call `observe-block --rule <name>` via stdin JSON.")
        return 0

    print(f"PreToolUse hook blocks (last {args.days}d):\n")
    for b in ordered:
        print(f"[{b['count']}x] rule={b['rule']}")
        if b["reason"]:
            print(f"   reason     : {truncate(b['reason'], 160)}")
        print(f"   example cmd: {truncate(b['example_cmd'], 160)}")
        print(f"   workspaces : {len(b['workspaces'])}")
        print(f"   last seen  : {b['last_seen']}")
        print()
    return 0


def command_session_check(args: argparse.Namespace) -> int:
    payload = load_stdin_json() if args.stdin_json else {}
    session_id = args.session_id or payload.get("session_id") or payload.get("sessionId")
    workspace = repo_root_for(args.workspace or payload.get("cwd"))
    if not session_id:
        return 0
    conn = connect_db(args.db)
    errors = conn.execute(
        """
        SELECT id, tool_name, summary, payload_json
        FROM events
        WHERE session_id = ? AND status = 'error'
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (session_id,),
    ).fetchall()
    if not errors:
        return 0

    seen: set[str] = set()
    lines: list[str] = []
    for row in errors:
        try:
            p = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            p = {}
        err_text = p.get("error") or ""
        key = normalize_error_text(err_text) or row["summary"] or ""
        key = f"{row['tool_name']}|{key}"
        if key in seen or not key.strip("|"):
            continue
        seen.add(key)
        snippet = truncate(err_text.splitlines()[0] if err_text else row["summary"] or "", 140)
        lines.append(f"- [event {row['id']}] {row['tool_name']}: {snippet}")
        if len(lines) >= 5:
            break

    if not lines:
        return 0

    context = (
        "Session errors recorded this turn. If any have a clear root cause, "
        "persist a durable lesson before stopping:\n"
        + "\n".join(lines)
        + f"\n\nUse: python3 {SCRIPT_PATH} learn --agent {args.agent} "
        f"--workspace \"{workspace}\" --event-id <id> "
        "--title \"<rule>\" --rule \"<actionable rule>\" --rationale \"<root cause>\""
    )

    if args.output in ("claude-json", "stop-json"):
        # Stop hook schema: top-level systemMessage, NOT hookSpecificOutput
        # (hookSpecificOutput is only valid for PreToolUse / UserPromptSubmit / PostToolUse).
        print(json.dumps({"systemMessage": context}))
    else:
        print(context)
    return 0


def command_promote(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    ensure_db(conn)
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=args.min_age_days)).isoformat()
    params: list[Any] = ["candidate", args.min_observations, args.min_confidence, cutoff_iso]
    sql = (
        "SELECT id, workspace, title, rule_text, confidence, observations, "
        "created_at, last_seen_at FROM lessons "
        "WHERE status = ? AND observations >= ? AND confidence >= ? AND created_at <= ?"
    )
    if args.workspace:
        sql += " AND workspace = ?"
        params.append(args.workspace)
    sql += " ORDER BY observations DESC, confidence DESC"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("No candidates eligible for promotion.")
        conn.close()
        return 0
    action = "Promoting" if args.write else "Would promote (dry-run)"
    print(f"{action} {len(rows)} candidate(s) → approved:\n")
    for row in rows:
        print(f"- [#{row['id']}] {row['title'][:80]}")
        print(f"    workspace   : {row['workspace']}")
        print(f"    observations: {row['observations']}    confidence: {row['confidence']:.2f}")
        print(f"    first seen  : {row['created_at']}")
        print(f"    last seen   : {row['last_seen_at']}")
    if args.write:
        now = datetime.now(timezone.utc).isoformat()
        promoted, merged = [], []
        for row in rows:
            fp = row["fingerprint"]
            dup = None
            if fp:
                dup = conn.execute(
                    "SELECT id, observations FROM lessons WHERE workspace = ? AND fingerprint = ? "
                    "AND status = 'approved' AND id != ? LIMIT 1",
                    (row["workspace"], fp, row["id"]),
                ).fetchone()
            if dup:
                # Merge candidate into the existing approved lesson; retire the candidate.
                conn.execute(
                    "UPDATE lessons SET observations = observations + ?, "
                    "last_seen_at = ?, updated_at = ? WHERE id = ?",
                    (row["observations"], now, now, dup["id"]),
                )
                conn.execute(
                    "UPDATE lessons SET status = 'retired', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                merged.append((row["id"], dup["id"]))
            else:
                conn.execute(
                    "UPDATE lessons SET status = 'approved', updated_at = ?, "
                    "approvals = approvals + 1, confidence = MIN(1.0, confidence + 0.1) "
                    "WHERE id = ?",
                    (now, row["id"]),
                )
                promoted.append(row["id"])
        conn.commit()
        msg = f"Promoted {len(promoted)} lesson(s)."
        if merged:
            msg += f" Merged {len(merged)} duplicate(s) into existing approved rules."
        print("\n" + msg)
    else:
        print("\nRe-run with --write to apply.")
    conn.close()
    return 0


def command_decay(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    ensure_db(conn)
    now = datetime.now(timezone.utc)
    stale_cutoff = (now - timedelta(days=args.stale_days)).isoformat()
    dormant_cutoff = (now - timedelta(days=args.dormant_days)).isoformat()
    retire_cutoff = (now - timedelta(days=args.retire_days)).isoformat()

    params_base: list[Any] = []
    ws_clause = ""
    if args.workspace:
        ws_clause = " AND workspace = ?"
        params_base.append(args.workspace)

    stale_rows = conn.execute(
        "SELECT id, workspace, title, confidence, last_seen_at, status FROM lessons "
        "WHERE status = 'approved' AND last_seen_at <= ?" + ws_clause,
        [stale_cutoff, *params_base],
    ).fetchall()

    dormant_rows = conn.execute(
        "SELECT id, workspace, title, confidence, last_seen_at FROM lessons "
        "WHERE status = 'approved' AND last_seen_at <= ?" + ws_clause,
        [dormant_cutoff, *params_base],
    ).fetchall()

    retire_rows = conn.execute(
        "SELECT id, workspace, title, last_seen_at FROM lessons "
        "WHERE status = 'dormant' AND last_seen_at <= ?" + ws_clause,
        [retire_cutoff, *params_base],
    ).fetchall()

    if not (stale_rows or dormant_rows or retire_rows):
        print("Nothing to decay, demote, or retire.")
        conn.close()
        return 0

    action = "Applying" if args.write else "Would apply (dry-run)"
    print(f"{action} decay pass:\n")
    if stale_rows:
        print(f"  -{args.decay_rate:.2f} confidence to {len(stale_rows)} stale approved lesson(s)")
    if dormant_rows:
        print(f"  {len(dormant_rows)} approved → dormant (last seen > {args.dormant_days}d ago)")
    if retire_rows:
        print(f"  {len(retire_rows)} dormant → retired (last seen > {args.retire_days}d ago)")

    if args.write:
        now_iso = now.isoformat()
        # Observation-weighted decay: well-evidenced rules age slower.
        # scale = 1 / (1 + observations/10) — 0 obs→1.0x, 10 obs→0.5x, 50 obs→0.17x.
        obs_rows = conn.execute(
            "SELECT id, confidence, observations FROM lessons WHERE id IN ("
            + ",".join(str(r["id"]) for r in stale_rows) + ")"
        ).fetchall() if stale_rows else []
        for row in obs_rows:
            obs = row["observations"] or 0
            scale = 1.0 / (1.0 + obs / 10.0)
            new_conf = max(0.0, (row["confidence"] or 0.0) - args.decay_rate * scale)
            conn.execute(
                "UPDATE lessons SET confidence = ?, updated_at = ? WHERE id = ?",
                (new_conf, now_iso, row["id"]),
            )
        if dormant_rows:
            ids = [r["id"] for r in dormant_rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE lessons SET status = 'dormant', updated_at = ? WHERE id IN ({placeholders})",
                [now_iso, *ids],
            )
        if retire_rows:
            ids = [r["id"] for r in retire_rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE lessons SET status = 'retired', updated_at = ? WHERE id IN ({placeholders})",
                [now_iso, *ids],
            )
        conn.commit()
        print("\nApplied.")
    else:
        print("\nRe-run with --write to apply.")
    conn.close()
    return 0


def command_reinforce(args: argparse.Namespace) -> int:
    """Process advice_shown rows for a session: reward rules that held, punish ones that didn't."""
    if not args.session_id:
        return 0  # no-op if hook fired without CLAUDE_SESSION_ID set
    conn = connect_db(args.db)
    ensure_db(conn)
    rows = conn.execute(
        "SELECT id, shown_at, workspace, lesson_id, fingerprint FROM advice_shown "
        "WHERE session_id = ? AND processed = 0",
        (args.session_id,),
    ).fetchall()
    if not rows:
        print(f"No unprocessed advice_shown rows for session {args.session_id}.")
        conn.close()
        return 0

    reinforced = 0
    contradicted = 0
    now_iso = utc_now()
    for row in rows:
        lesson_id = row["lesson_id"]
        fp = row["fingerprint"]
        contradicted_hit = False
        if fp:
            hit = conn.execute(
                "SELECT 1 FROM events WHERE session_id = ? AND workspace = ? "
                "AND fingerprint = ? AND status = 'error' AND created_at > ? LIMIT 1",
                (args.session_id, row["workspace"], fp, row["shown_at"]),
            ).fetchone()
            contradicted_hit = hit is not None
        if contradicted_hit:
            contradicted += 1
            outcome = "contradicted"
            if args.write:
                conn.execute(
                    "UPDATE lessons SET confidence = MAX(0.0, confidence - ?), "
                    "contradictions = contradictions + 1, last_contradicted_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    (args.contradict_penalty, now_iso, now_iso, lesson_id),
                )
        else:
            reinforced += 1
            outcome = "reinforced"
            if args.write:
                conn.execute(
                    "UPDATE lessons SET confidence = MIN(1.0, confidence + ?), "
                    "reinforcements = reinforcements + 1, updated_at = ? WHERE id = ?",
                    (args.reinforce_bonus, now_iso, lesson_id),
                )
        if args.write:
            conn.execute(
                "UPDATE advice_shown SET processed = 1, outcome = ? WHERE id = ?",
                (outcome, row["id"]),
            )

    verb = "Applied" if args.write else "Would apply (dry-run)"
    print(f"{verb}: +{reinforced} reinforced (+{args.reinforce_bonus:.2f}), "
          f"-{contradicted} contradicted (-{args.contradict_penalty:.2f})")
    if args.write:
        conn.commit()
    else:
        print("Re-run with --write to apply.")
    conn.close()
    return 0


def command_suggest_skills(args: argparse.Namespace) -> int:
    """Inverse of mine-skill-miss: find frequently-run Bash commands that no skill pattern covers."""
    workspace = repo_root_for(args.workspace)
    conn = connect_db(args.db)
    ensure_db(conn)
    registry = load_skill_registry(workspace)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    rows = conn.execute(
        "SELECT payload_json FROM events WHERE workspace = ? AND tool_name = 'Bash' "
        "AND created_at >= ? AND event_name IN ('PostToolUse', 'PreToolUse')",
        (workspace, since),
    ).fetchall()

    clusters: dict[str, int] = {}
    samples: dict[str, str] = {}
    for row in rows:
        try:
            payload = json.loads(row["payload_json"]) or {}
        except (ValueError, TypeError):
            continue
        cmd = ((payload.get("tool_input") or {}).get("command") or "").strip()
        if not cmd:
            continue
        if any(pattern.search(cmd) for pattern, _skill, _reason in registry):
            continue
        # Signature: first two tokens (binary + subcommand) — groups `kubectl exec ...`, `docker build ...`, etc.
        tokens = re.split(r"\s+", cmd, maxsplit=3)
        sig = " ".join(tokens[:2]) if tokens else cmd[:40]
        if not sig or sig.startswith(("#", "cd", "ls", "echo", "cat", "pwd")):
            continue
        clusters[sig] = clusters.get(sig, 0) + 1
        samples.setdefault(sig, cmd)

    ranked = sorted(
        ((count, sig, samples[sig]) for sig, count in clusters.items() if count >= args.min_count),
        reverse=True,
    )[: args.top]

    print(f"Uncovered Bash command clusters for {workspace} (last {args.days}d, min {args.min_count} occurrences):")
    if not ranked:
        print("  (none — every frequent command already maps to a registered skill)")
        conn.close()
        return 0
    for count, sig, sample in ranked:
        print(f"  {count:4d}  {sig}")
        print(f"           e.g. {truncate(sample, 100)}")
    print()
    print("If any of these deserve a skill, register a pattern in "
          "<workspace>/.claude/continuous-learning.json so mine-skill-miss can flag future bypasses.")
    conn.close()
    return 0


def command_maintain(args: argparse.Namespace) -> int:
    """Run promote + decay, but only if the last run was more than --min-interval-hours ago."""
    sentinel = LB_HOME / ".last-maintain"
    try:
        last_str = sentinel.read_text().strip()
        last = datetime.fromisoformat(last_str)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
        if hours_since < args.min_interval_hours:
            print(f"Skipping maintain: last ran {hours_since:.1f}h ago "
                  f"(< {args.min_interval_hours:.1f}h interval).")
            return 0
    except (FileNotFoundError, ValueError):
        pass

    promote_args = argparse.Namespace(
        db=args.db, min_observations=5, min_age_days=7, min_confidence=0.6,
        workspace=None, write=args.write,
    )
    decay_args = argparse.Namespace(
        db=args.db, stale_days=60, dormant_days=60, retire_days=180,
        decay_rate=0.02, workspace=None, write=args.write,
    )
    print("== maintain: promote ==")
    command_promote(promote_args)
    print("\n== maintain: decay ==")
    command_decay(decay_args)

    if args.write:
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(datetime.now(timezone.utc).isoformat())
        except OSError:
            pass
    return 0


def command_suggest_hooks(args: argparse.Namespace) -> int:
    """Detect hook-wiring gaps for a workspace and emit actionable suggestions."""
    workspace = repo_root_for(args.workspace)
    conn = connect_db(args.db)
    ensure_db(conn)
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()

    def count(sql: str, params: tuple[Any, ...]) -> int:
        row = conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    total_events = count(
        "SELECT COUNT(*) FROM events WHERE workspace = ? AND created_at >= ?",
        (workspace, since),
    )
    post_tool = count(
        "SELECT COUNT(*) FROM events WHERE workspace = ? AND created_at >= ? AND event_name = 'PostToolUse'",
        (workspace, since),
    )
    advice_rows = count(
        "SELECT COUNT(*) FROM advice_shown WHERE workspace = ? AND shown_at >= ?",
        (workspace, since),
    )
    blocks = count(
        "SELECT COUNT(*) FROM events WHERE workspace = ? AND created_at >= ? AND event_name = 'observe-block'",
        (workspace, since),
    )
    risky_bash = count(
        "SELECT COUNT(*) FROM events WHERE workspace = ? AND created_at >= ? AND tool_name = 'Bash' "
        "AND (payload_json LIKE '%--no-verify%' OR payload_json LIKE '%--force%' "
        "OR payload_json LIKE '% rm -rf %')",
        (workspace, since),
    )

    suggestions: list[str] = []
    if total_events == 0:
        suggestions.append(
            "No hook events recorded in the last "
            f"{args.days} days. Wire at minimum SessionStart + PostToolUse hooks "
            "(see examples/settings.local.json.example)."
        )
    if post_tool == 0 and total_events > 0:
        suggestions.append(
            "No PostToolUse events — mining cannot cluster failures. "
            "Add a PostToolUse hook calling `learning.py observe`."
        )
    if advice_rows == 0:
        suggestions.append(
            "No advice_shown rows — the UserPromptSubmit `advice` hook is not wired "
            "(or not passing `--session-id`). Without it, reinforcement signal is lost."
        )
    if risky_bash > 0 and blocks == 0:
        suggestions.append(
            f"Saw {risky_bash} risky Bash invocation(s) (--no-verify, --force, rm -rf) with zero "
            "`observe-block` events. Consider installing a PreToolUse guard "
            "(examples/guard-template.py)."
        )

    print(f"Hook coverage report for {workspace} (last {args.days}d):")
    print(f"  events: {total_events}  post_tool: {post_tool}  advice_shown: {advice_rows}  "
          f"blocks: {blocks}  risky_bash: {risky_bash}")
    if not suggestions:
        print("\nAll core hooks appear wired.")
    else:
        print("\nSuggestions:")
        for s in suggestions:
            print(f"  - {s}")
    conn.close()
    return 0


def main() -> int:
    args = parse_args()
    if hasattr(args, "agent"):
        args.agent = canonical_agent(args.agent)
    if args.command == "observe":
        return command_observe(args)
    if args.command == "advice":
        return command_advice(args)
    if args.command == "learn":
        return command_learn(args)
    if args.command == "review":
        return command_review(args)
    if args.command == "init-db":
        return command_init_db(args)
    if args.command == "mine":
        return command_mine(args)
    if args.command == "mine-edits":
        return command_mine_edits(args)
    if args.command == "mine-skill-miss":
        return command_mine_skill_miss(args)
    if args.command == "observe-block":
        return command_observe_block(args)
    if args.command == "mine-blocks":
        return command_mine_blocks(args)
    if args.command == "session-check":
        return command_session_check(args)
    if args.command == "promote":
        return command_promote(args)
    if args.command == "decay":
        return command_decay(args)
    if args.command == "reinforce":
        return command_reinforce(args)
    if args.command == "suggest-hooks":
        return command_suggest_hooks(args)
    if args.command == "suggest-skills":
        return command_suggest_skills(args)
    if args.command == "maintain":
        return command_maintain(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
