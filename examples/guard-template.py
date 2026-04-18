#!/usr/bin/env python3
"""
Minimal PreToolUse guard template for `learned-behavior`.

Drop this into a project as a PreToolUse hook. It reads the hook payload from
stdin, applies a small set of deny rules, and calls `learned-behavior
observe-block` so recurring blocks get mined into lessons.

Customize the DENY_RULES list for your project. Exit code 2 with stderr tells
Claude Code (and Codex / Copilot equivalents) to refuse the tool call.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# (rule_id, human reason, regex-against-command-string)
DENY_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("no-force-push-main", "Refusing --force push to protected branch",
     re.compile(r"git\s+push\s+[^\n]*--force\b[^\n]*\b(main|master|production|staging)\b")),
    ("no-no-verify", "Refusing --no-verify; fix the hook failure instead",
     re.compile(r"git\s+(commit|push)\s+[^\n]*--no-verify\b")),
]

CLI = Path(os.environ.get("LEARNED_BEHAVIOR_CLI")
           or Path.home() / ".local/bin/learned-behavior").expanduser()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # be permissive if we can't parse
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    for rule_id, reason, pattern in DENY_RULES:
        if not pattern.search(command):
            continue
        try:
            subprocess.run(
                [str(CLI), "observe-block",
                 "--rule", rule_id,
                 "--reason", reason,
                 "--workspace", payload.get("cwd") or os.getcwd()],
                input=json.dumps(payload),
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            pass
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
