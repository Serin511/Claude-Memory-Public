"""Plan Gate — block implementation tools while /plan-create is mid-planning.

PreToolUse hook for Edit | Write | MultiEdit | NotebookEdit. Enforces the
/plan-create / /plan-execute Codex review contract by reading a session-scoped
state file written by those commands.

State file
----------
Location: ``<project>/.claude/data/plan-gate.json`` (gitignored).

Schema:
    {
        "stage": "plan-creating" | "plan-approved" | "executing" | "inactive",
        "plan_path": "<absolute path to the plan markdown>",
        "session_id": "<claude session id>",
        "started_at": "<ISO 8601>",
        "approved_at": "<ISO 8601, optional>"
    }

Stage semantics
---------------
- *file absent* / ``"inactive"`` — gate disabled; allow all tool calls.
- ``"plan-creating"`` — /plan-create command is drafting the plan and waiting
  for ``/codex-adversarial-review`` to bless it. Implementation tools are
  blocked so Claude cannot start coding before the plan is approved,
  **except** for writes to the command's own artefacts (see Allowlist).
- ``"plan-approved"`` — Codex review accepted (or the user dismissed the
  feedback). /plan-execute may run; implementation tools are allowed.
- ``"executing"`` — /plan-execute is actively running. Allow.

Allowlist during ``plan-creating``
----------------------------------
Two classes of writes are permitted even while the gate is blocking
production code edits, because the ``/plan-create`` command itself has to
produce them during Phase 0 and Phase 4:

- The gate state file ``.claude/data/plan-gate.json`` (the command
  transitions the stage across phases and needs to rewrite this file).
- Any file under ``plans/`` (the default location for the plan document
  and its supporting reference files).

Paths are resolved against ``$CLAUDE_PROJECT_DIR`` and must be inside it;
any file outside the project, or any file inside but not on the
allowlist, is still blocked. A payload lacking ``tool_input.file_path``
cannot be proven allowlisted and is also blocked.

Manual override
---------------
If the gate is wrongly stuck, delete the state file::

    rm "$CLAUDE_PROJECT_DIR/.claude/data/plan-gate.json"

Install
-------
This file is per-project. Copy it to ``<project>/.claude/hooks/plan_gate.py``
and register it in ``<project>/.claude/settings.json``::

    {
      "hooks": {
        "PreToolUse": [{
          "matcher": "Edit|Write|MultiEdit|NotebookEdit",
          "hooks": [{
            "type": "command",
            "command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/hooks/plan_gate.py\\""
          }]
        }]
      }
    }

Also add ``.claude/data/plan-gate.json`` to the project ``.gitignore``.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


_GATED_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_BLOCK_EXIT_CODE = 2  # PreToolUse: stderr is shown to the model

# Paths (project-root-relative, POSIX) that may be written during
# ``plan-creating`` so the /plan-create command can manage its own artefacts.
_ALLOWED_FILES_DURING_PLANNING = frozenset({".claude/data/plan-gate.json"})
_ALLOWED_PREFIXES_DURING_PLANNING = ("plans/",)


def _state_path(project_dir: Optional[Path]) -> Optional[Path]:
    """Resolve the plan-gate state file path.

    Args:
        project_dir: Project root derived from ``$CLAUDE_PROJECT_DIR``
            if available, otherwise ``None``.

    Returns:
        The absolute path to ``.claude/data/plan-gate.json`` under the
        project root; falls back to a path computed from this script's
        own location. Returns ``None`` only when neither resolution
        succeeds.
    """
    if project_dir is not None:
        return project_dir / ".claude" / "data" / "plan-gate.json"
    try:
        return Path(__file__).resolve().parents[1] / "data" / "plan-gate.json"
    except (OSError, IndexError):
        return None


def _read_state(path: Path) -> Optional[dict]:
    """Read the state JSON, returning ``None`` on any read or parse failure."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _is_allowed_during_planning(
    file_path: Optional[str], project_dir: Optional[Path]
) -> bool:
    """Check whether ``file_path`` is on the plan-creating allowlist.

    Args:
        file_path: The value of ``tool_input.file_path`` from the
            PreToolUse payload, or ``None`` if missing.
        project_dir: Project root (``$CLAUDE_PROJECT_DIR``). Required
            to anchor the relative-path check; ``None`` disables the
            allowlist.

    Returns:
        ``True`` when the path resolves to either the gate state file
        or a location under ``plans/`` within the project root;
        ``False`` otherwise (including missing input or paths outside
        the project).
    """
    if not file_path or project_dir is None:
        return False
    try:
        resolved_project = project_dir.resolve()
        resolved_file = Path(file_path).resolve()
        rel = resolved_file.relative_to(resolved_project)
    except (OSError, ValueError):
        return False
    rel_posix = rel.as_posix()
    if rel_posix in _ALLOWED_FILES_DURING_PLANNING:
        return True
    return any(rel_posix.startswith(prefix) for prefix in _ALLOWED_PREFIXES_DURING_PLANNING)


def main() -> int:
    """PreToolUse hook entry point.

    Returns:
        ``0`` to allow the tool call, ``2`` to block it (Claude sees stderr).
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    tool = payload.get("tool_name", "")
    if tool not in _GATED_TOOLS:
        return 0

    project_dir_env = os.environ.get("CLAUDE_PROJECT_DIR")
    project_dir = Path(project_dir_env) if project_dir_env else None

    path = _state_path(project_dir)
    if path is None:
        return 0

    state = _read_state(path)
    if state is None:
        return 0

    stage = state.get("stage", "inactive")
    if stage in {"inactive", "plan-approved", "executing"}:
        return 0

    if stage == "plan-creating":
        tool_input = payload.get("tool_input") or {}
        file_path = tool_input.get("file_path")
        if _is_allowed_during_planning(file_path, project_dir):
            return 0

        plan_path = state.get("plan_path", "<unknown>")
        sys.stderr.write(
            "Plan Gate: BLOCKED — /plan-create is in the planning phase.\n"
            f"  Plan: {plan_path}\n"
            "  Implementation tools (Edit/Write/MultiEdit/NotebookEdit) are\n"
            "  disabled until /codex-adversarial-review approves the plan.\n"
            "  Writes to plans/** and .claude/data/plan-gate.json are allowed\n"
            "  so the /plan-create command can author its own artefacts.\n"
            "  Either:\n"
            "    - finish /plan-create's Phase 4.5 (writes stage='plan-approved'), or\n"
            f"    - clear the gate manually: rm {path}\n"
        )
        return _BLOCK_EXIT_CODE

    return 0


if __name__ == "__main__":
    sys.exit(main())
