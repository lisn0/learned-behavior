"""Smoke test for the reinforce round-trip.

Seeds a lesson + an advice_shown row, inserts a matching error event that
post-dates the advice, then runs command_reinforce --write and asserts that
the lesson's confidence dropped by --contradict-penalty and that
contradictions incremented.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import learning


def _seed(conn: sqlite3.Connection, workspace: str, session_id: str, fp: str) -> int:
    now = learning.utc_now()
    cur = conn.execute(
        "INSERT INTO lessons (created_at, updated_at, workspace, status, agent, "
        "title, rule_text, rationale, fingerprint, confidence, observations, "
        "approvals, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now, now, workspace, "approved", "claude", "Test rule",
         "Do X, not Y", "because Y breaks", fp, 0.80, 10, 1, now),
    )
    lesson_id = cur.lastrowid
    conn.execute(
        "INSERT INTO advice_shown (shown_at, session_id, workspace, lesson_id, "
        "fingerprint, processed) VALUES (?,?,?,?,?,0)",
        (now, session_id, workspace, lesson_id, fp),
    )
    # Error event with matching fingerprint, post-dating the advice_shown row.
    from datetime import datetime, timedelta, timezone
    later = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    conn.execute(
        "INSERT INTO events (created_at, agent, source, workspace, event_name, "
        "status, session_id, tool_name, prompt, summary, fingerprint, payload_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (later, "claude", "test", workspace, "PostToolUseFailure", "error",
         session_id, "Bash", None, "boom", fp, "{}"),
    )
    conn.commit()
    return lesson_id


def test_reinforce_contradicts_when_error_recurs(tmp_path: Path) -> None:
    db = tmp_path / "learning.db"
    conn = learning.connect_db(str(db))
    learning.ensure_db(conn)
    session_id = "sess-test-1"
    workspace = str(tmp_path)
    fp = "fp-test-contradict"

    lesson_id = _seed(conn, workspace, session_id, fp)
    conn.close()

    args = argparse.Namespace(
        db=str(db),
        session_id=session_id,
        reinforce_bonus=0.03,
        contradict_penalty=0.1,
        write=True,
    )
    rc = learning.command_reinforce(args)
    assert rc == 0

    check = sqlite3.connect(db)
    check.row_factory = sqlite3.Row
    row = check.execute(
        "SELECT confidence, contradictions, reinforcements, last_contradicted_at "
        "FROM lessons WHERE id = ?", (lesson_id,),
    ).fetchone()
    advice = check.execute(
        "SELECT processed, outcome FROM advice_shown WHERE lesson_id = ?",
        (lesson_id,),
    ).fetchone()
    check.close()

    assert row is not None
    assert abs(row["confidence"] - (0.80 - 0.1)) < 1e-9
    assert row["contradictions"] == 1
    assert row["reinforcements"] == 0
    assert row["last_contradicted_at"] is not None
    assert advice["processed"] == 1
    assert advice["outcome"] == "contradicted"


def test_reinforce_rewards_when_error_does_not_recur(tmp_path: Path) -> None:
    db = tmp_path / "learning.db"
    conn = learning.connect_db(str(db))
    learning.ensure_db(conn)
    session_id = "sess-test-2"
    workspace = str(tmp_path)
    fp = "fp-test-reinforce"

    now = learning.utc_now()
    cur = conn.execute(
        "INSERT INTO lessons (created_at, updated_at, workspace, status, agent, "
        "title, rule_text, rationale, fingerprint, confidence, observations, "
        "approvals, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now, now, workspace, "approved", "claude", "Calm rule",
         "Do A", "because A is right", fp, 0.50, 5, 1, now),
    )
    lesson_id = cur.lastrowid
    conn.execute(
        "INSERT INTO advice_shown (shown_at, session_id, workspace, lesson_id, "
        "fingerprint, processed) VALUES (?,?,?,?,?,0)",
        (now, session_id, workspace, lesson_id, fp),
    )
    conn.commit()
    conn.close()

    args = argparse.Namespace(
        db=str(db),
        session_id=session_id,
        reinforce_bonus=0.03,
        contradict_penalty=0.1,
        write=True,
    )
    rc = learning.command_reinforce(args)
    assert rc == 0

    check = sqlite3.connect(db)
    check.row_factory = sqlite3.Row
    row = check.execute(
        "SELECT confidence, reinforcements, contradictions FROM lessons WHERE id = ?",
        (lesson_id,),
    ).fetchone()
    check.close()

    assert abs(row["confidence"] - (0.50 + 0.03)) < 1e-9
    assert row["reinforcements"] == 1
    assert row["contradictions"] == 0
