"""`review --output json` emits a stable, untruncated shape; text output is unchanged."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import learning


def _seed(db: Path, workspace: str) -> None:
    conn = learning.connect_db(str(db))
    learning.ensure_db(conn)
    now = learning.utc_now()
    long_rule = "Use sh -c instead of bash -lc because the image has no bash " * 4  # > 150 chars
    conn.execute(
        "INSERT INTO lessons (created_at, updated_at, workspace, status, agent, "
        "title, rule_text, rationale, fingerprint, confidence, observations, "
        "approvals, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now, now, workspace, "approved", "claude", "No bash in image",
         long_rule, "observed", "fp-bash", 0.8, 3, 1, now),
    )
    for _ in range(2):  # HAVING COUNT(*) >= 2
        conn.execute(
            "INSERT INTO events (created_at, agent, source, workspace, event_name, "
            "status, session_id, tool_name, prompt, summary, fingerprint, payload_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (now, "claude", "test", workspace, "PostToolUseFailure", "error",
             "s1", "Bash", None, "npm ERR! peer dep conflict", "fp-npm", "{}"),
        )
    conn.commit()
    conn.close()


def _args(db: Path, workspace: str, output: str) -> argparse.Namespace:
    return argparse.Namespace(db=str(db), workspace=workspace, days=14, limit=10,
                              all=True, output=output)


def test_review_json_is_structured_and_untruncated(tmp_path: Path, capsys) -> None:
    db = tmp_path / "learning.db"
    workspace = str(tmp_path)
    _seed(db, workspace)

    assert learning.command_review(_args(db, workspace, "json")) == 0
    data = json.loads(capsys.readouterr().out)

    assert data["workspace"] == learning.repo_root_for(workspace)
    assert data["include_candidates"] is True
    assert data["repeated_failures"][0]["count"] == 2
    assert data["repeated_failures"][0]["tool_name"] == "Bash"
    lesson = data["lessons"][0]
    assert lesson["status"] == "approved" and lesson["confidence"] == 0.8
    assert len(lesson["rule_text"]) > 150  # text mode truncates; json must not


def test_review_text_output_unchanged(tmp_path: Path, capsys) -> None:
    db = tmp_path / "learning.db"
    workspace = str(tmp_path)
    _seed(db, workspace)

    assert learning.command_review(_args(db, workspace, "text")) == 0
    out = capsys.readouterr().out
    assert out.startswith("Continuous learning review for ")
    assert "Repeated failures:" in out and "Stored lessons:" in out
