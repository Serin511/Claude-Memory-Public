#!/usr/bin/env python3
"""Extract failure signals from Claude Code session logs.

Scans JSONL session files and outputs a structured JSON summary of tool failures,
retry patterns, user-correction signals, and usage statistics. Designed to be run
by the update-harness skill as a preprocessing step before qualitative analysis.

Usage:
    python parse_sessions.py --project-path /path/to/project [--days 7] [--max-sessions 20]
    python parse_sessions.py --all [--days 7] [--max-sessions 20]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Keywords suggesting user correction or dissatisfaction.
# Each entry is (keyword, is_strict). Strict keywords require word-boundary-like
# matching to avoid false positives (e.g., "아니" in "아니면" = "or", not a correction).
CORRECTION_PATTERNS: list[tuple[str, bool]] = [
    # English — matched case-insensitively
    ("don't do", False),
    ("do not do", False),
    ("stop doing", False),
    ("that's wrong", False),
    ("that's not what", False),
    ("not what i asked", False),
    ("not what i wanted", False),
    ("i said", False),
    ("i asked you to", False),
    ("try again", False),
    ("undo that", False),
    ("revert", False),
    ("go back", False),
    ("why did you", False),
    ("i already told", False),
    ("that broke", False),
    ("still failing", False),
    ("still broken", False),
    ("not working", False),
    # Korean — strict matching to avoid substring false positives
    ("하지마", False),
    ("하지 마", False),
    ("잘못", False),
    ("그게 아니", False),
    ("되돌려", False),
    ("왜 그렇게", False),
    ("이미 말했", False),
    ("안 돼", False),
    ("안돼", False),
    ("틀렸", False),
    ("다시 해", False),
    ("다시해", False),
    # Short Korean keywords that need boundary checks to avoid "아니면", "아니라" etc.
    ("아니야", False),
    ("아니요", False),
    ("아니 ", False),  # trailing space acts as boundary
]


def find_project_dir(project_path: str) -> Path | None:
    """Find the Claude project directory matching a filesystem path."""
    encoded = project_path.replace("/", "-")
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and encoded.lstrip("-") in d.name:
            return d
    return None


def find_sessions(
    project_dir: Path | None,
    days: int | None,
    max_sessions: int,
    scan_all: bool,
) -> list[Path]:
    """Find recent session JSONL files, sorted newest-first."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
        if days is not None
        else None
    )
    dirs = (
        [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
        if scan_all
        else [project_dir] if project_dir else []
    )
    files = []
    for d in dirs:
        for f in d.glob("*.jsonl"):
            if cutoff is None or f.stat().st_mtime >= cutoff.timestamp():
                files.append(f)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:max_sessions]


def extract_text(content) -> str:
    """Extract plain text from a message content field (string or block array)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", "") or block.get("content", ""))
        return " ".join(parts)
    return ""


def check_error(content) -> tuple[bool, str]:
    """Check if tool result content indicates an error. Returns (is_error, excerpt).

    Prioritizes the explicit `is_error` field over text heuristics to avoid
    false positives from normal file content that happens to contain error-like words.
    """
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("is_error"):
                text = str(block.get("text", "") or block.get("content", ""))
                return True, text[:500]
    # Only use text heuristics for short string content (likely stderr, not file reads)
    if isinstance(content, str) and len(content) < 2000 and _text_has_error(content):
        return True, content[:500]
    return False, ""


def _text_has_error(text: str) -> bool:
    """Heuristic for error detection — only reliable on short tool output.

    Requires multiple signals or strong indicators to reduce false positives
    from normal file content that contains words like 'Error' in comments/docs.
    """
    if not text or len(text) < 10:
        return False
    # Strong signals: these almost always indicate a real error
    strong = [
        "Traceback (most recent call last)",
        "command not found", "Permission denied", "No such file or directory",
        "ENOENT", "EACCES", "non-zero exit", "exit code 1",
        "ModuleNotFoundError:", "FileNotFoundError:",
    ]
    if any(s in text for s in strong):
        return True
    # Weaker signals: require the text to be short (likely stderr, not file content)
    if len(text) < 500:
        weak = ["Error:", "ERROR", "FAILED", "SyntaxError:", "TypeError:",
                "ValueError:", "KeyError:", "AttributeError:", "IndexError:"]
        return any(s in text for s in weak)
    return False


def find_corrections(text: str) -> list[str]:
    """Find correction/dissatisfaction signals in user text.

    Only matches patterns that indicate the user is correcting or expressing
    dissatisfaction with the agent's behavior. Skips text that is too long
    (likely pasted content or system prompts, not direct user speech).
    """
    if len(text) > 1000:
        return []
    lower = text.lower()
    return [pattern for pattern, _ in CORRECTION_PATTERNS if pattern in lower]


def parse_session(path: Path) -> dict:
    """Parse a session JSONL file and extract signals."""
    entries = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f):
            if line.strip():
                try:
                    entries.append((line_num, json.loads(line)))
                except json.JSONDecodeError:
                    continue

    session_id = None
    timestamps = []
    tool_uses = []
    tool_failures = []
    corrections = []

    for line_num, entry in entries:
        ts = entry.get("timestamp")
        if ts:
            timestamps.append(ts)
        if not session_id:
            session_id = entry.get("sessionId")

        msg = entry.get("message", {})
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        entry_type = entry.get("type")

        # --- Assistant messages: extract tool_use blocks ---
        if entry_type == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses.append({
                        "id": block.get("id"),
                        "tool": block.get("name", "unknown"),
                        "input_summary": _input_summary(
                            block.get("name"), block.get("input", {})
                        ),
                        "timestamp": ts,
                    })

        # --- User messages: tool results + correction signals ---
        if entry_type == "user":
            if isinstance(content, str):
                # Plain text user message
                found = find_corrections(content)
                if found:
                    corrections.append({
                        "timestamp": ts,
                        "excerpt": content[:300],
                        "keywords": found,
                        "line_num": line_num,
                    })
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # Tool result block — check is_error flag first
                    if block.get("type") == "tool_result":
                        is_err, excerpt = check_error(
                            block.get("content", "")
                        )
                        # Also treat explicit is_error on the block itself
                        if block.get("is_error"):
                            excerpt = extract_text(block.get("content", ""))[:500]
                            is_err = True
                        if is_err:
                            tool_failures.append({
                                "tool_use_id": block.get("tool_use_id"),
                                "error_excerpt": excerpt,
                                "timestamp": ts,
                                "line_num": line_num,
                            })
                    # Text block within user turn
                    elif block.get("type") == "text":
                        text = block.get("text", "")
                        found = find_corrections(text)
                        if found:
                            corrections.append({
                                "timestamp": ts,
                                "excerpt": text[:300],
                                "keywords": found,
                                "line_num": line_num,
                            })

    # Map failures back to tool names via tool_use_id
    tool_id_map = {tu["id"]: tu["tool"] for tu in tool_uses if tu.get("id")}
    for fail in tool_failures:
        fail["tool"] = tool_id_map.get(fail.get("tool_use_id"), "unknown")

    retries = _detect_retries(tool_uses)

    # Tool distribution
    dist: dict[str, int] = {}
    for tu in tool_uses:
        dist[tu["tool"]] = dist.get(tu["tool"], 0) + 1

    duration = _compute_duration(timestamps)

    return {
        "session_id": session_id or path.stem,
        "file": str(path),
        "project": _project_name(path),
        "message_count": len(entries),
        "duration_min": duration,
        "tool_calls": len(tool_uses),
        "failure_count": len(tool_failures),
        "failures": tool_failures[:25],
        "correction_count": len(corrections),
        "corrections": corrections[:25],
        "retries": retries,
        "tool_distribution": dict(sorted(dist.items(), key=lambda x: -x[1])),
    }


def _input_summary(tool: str | None, inp: dict) -> str:
    """Brief summary of tool input for retry detection."""
    if tool == "Bash":
        return (inp.get("command") or "")[:200]
    if tool in ("Read", "Edit", "Write"):
        return inp.get("file_path", "?")
    if tool in ("Glob", "Grep"):
        return inp.get("pattern", "")[:100]
    if tool == "Agent":
        return inp.get("description", "")[:100]
    return str(inp)[:100]


def _detect_retries(tool_uses: list[dict]) -> list[dict]:
    """Detect sequences of 3+ similar consecutive tool calls."""
    retries = []
    i = 0
    while i < len(tool_uses):
        run = 1
        while (
            i + run < len(tool_uses)
            and tool_uses[i + run]["tool"] == tool_uses[i]["tool"]
            and _similar(
                tool_uses[i]["input_summary"], tool_uses[i + run]["input_summary"]
            )
        ):
            run += 1
        if run >= 3:
            retries.append({
                "tool": tool_uses[i]["tool"],
                "count": run,
                "input": tool_uses[i]["input_summary"],
                "first_timestamp": tool_uses[i].get("timestamp"),
            })
        i += max(run, 1)
    return retries


def _similar(a: str, b: str) -> bool:
    """Check if two tool inputs are similar enough to be retries."""
    if not a or not b:
        return a == b
    if a == b:
        return True
    prefix = os.path.commonprefix([a, b])
    return len(prefix) > min(len(a), len(b)) * 0.5


def _compute_duration(timestamps: list) -> float | None:
    """Compute session duration in minutes."""
    parsed = []
    for ts in timestamps:
        try:
            if isinstance(ts, str):
                parsed.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            elif isinstance(ts, (int, float)):
                # Handle both seconds and milliseconds
                val = ts / 1000 if ts > 1e12 else ts
                parsed.append(datetime.fromtimestamp(val, tz=timezone.utc))
        except (ValueError, OSError):
            continue
    if len(parsed) < 2:
        return None
    return round((max(parsed) - min(parsed)).total_seconds() / 60, 1)


def _project_name(path: Path) -> str:
    """Extract encoded project name from session file path."""
    try:
        idx = path.parts.index("projects")
        return path.parts[idx + 1] if idx + 1 < len(path.parts) else "unknown"
    except ValueError:
        return "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="Extract failure signals from Claude Code session logs"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project-path", help="Project directory path")
    group.add_argument("--all", action="store_true", help="Scan all projects")
    parser.add_argument(
        "--days", type=int, default=None,
        help="Look back N days (default: no limit)",
    )
    parser.add_argument(
        "--max-sessions", type=int, default=10,
        help="Max sessions to analyze (default: 10)",
    )
    args = parser.parse_args()

    project_dir = None
    if args.project_path:
        project_dir = find_project_dir(args.project_path)
        if not project_dir:
            json.dump(
                {"error": f"No Claude project found for: {args.project_path}"},
                sys.stdout,
            )
            sys.exit(1)

    files = find_sessions(project_dir, args.days, args.max_sessions, args.all)

    if not files:
        json.dump(
            {"error": "No recent sessions found", "days": args.days},
            sys.stdout,
        )
        sys.exit(0)

    sessions = [parse_session(f) for f in files]

    # --- Aggregate statistics ---
    total_calls = sum(s["tool_calls"] for s in sessions)
    total_fails = sum(s["failure_count"] for s in sessions)
    total_corrs = sum(s["correction_count"] for s in sessions)

    agg_dist: dict[str, int] = {}
    for s in sessions:
        for tool, count in s["tool_distribution"].items():
            agg_dist[tool] = agg_dist.get(tool, 0) + count

    all_failures = []
    all_corrections = []
    all_retries = []
    for s in sessions:
        sid = s["session_id"]
        proj = s["project"]
        for f in s["failures"]:
            f["session_id"] = sid
            f["project"] = proj
            all_failures.append(f)
        for c in s["corrections"]:
            c["session_id"] = sid
            c["project"] = proj
            all_corrections.append(c)
        for r in s["retries"]:
            r["session_id"] = sid
            r["project"] = proj
            all_retries.append(r)

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": "all" if args.all else args.project_path,
        "days": args.days,
        "session_count": len(sessions),
        "sessions": sessions,
        "aggregate": {
            "total_tool_calls": total_calls,
            "total_failures": total_fails,
            "failure_rate": (
                round(total_fails / total_calls, 4) if total_calls else 0
            ),
            "total_corrections": total_corrs,
            "tool_distribution": dict(
                sorted(agg_dist.items(), key=lambda x: -x[1])
            ),
            "top_failures": all_failures[:50],
            "top_corrections": all_corrections[:50],
            "retry_patterns": all_retries[:20],
        },
    }

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
