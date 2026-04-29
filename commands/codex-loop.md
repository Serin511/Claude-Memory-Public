---
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
description: Iteratively delegate one fix-loop cycle to Codex until a termination condition is met
argument-hint: [task description] --until <verification command>
---

# Codex Loop

Delegate a fix-loop to Codex one cycle at a time, with the Claude orchestrator
checking the termination gate between cycles. Each Codex invocation runs fresh
via `codex exec --full-auto`; the orchestrator carries prior-cycle context in
the prompt text.

Raw user request:
$ARGUMENTS

## Parse Arguments

Split `$ARGUMENTS` into:

- **Task** — what Codex should fix or improve each cycle
- **Termination condition** — a shell command or observable criterion whose
  result tells the orchestrator when to stop. Prefer a pass/fail command such
  as `pytest -q` or a counting command such as
  `pytest -q 2>&1 | tail -1 | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+'`.

If either part is unclear, use `AskUserQuestion` once. Do not guess.

Convention: the user may use `--until <command>` to separate the two, e.g.
`/codex-loop fix flaky integration tests --until 'pytest tests/integration -q'`.
If no `--until` is given, infer from the phrasing and confirm with the user.

## Prerequisites

- Codex CLI must be installed and authenticated. Quick check:

  ```bash
  command -v codex
  ```

  If Codex is missing, stop and tell the user to install it
  (e.g. `npm i -g @openai/codex`).

- Project rules (CLAUDE.md, `.claude/rules/`) apply to every Codex cycle. If
  the project defines a `## Fix Loop` section in CLAUDE.md, its regression
  gate and "do not weaken assertions" constraints apply to every cycle here
  as well.

## Preflight

Run the termination check **once** before the first Codex cycle.

- If already satisfied → report and exit; no cycles needed.
- Otherwise record the baseline value for the summary table.

## Loop

Repeat without a hard cap until the termination check is satisfied or the user
intervenes.

### Step 1 — Dispatch one Codex cycle

Exactly one `Bash` call per cycle.

```bash
mkdir -p /tmp/codex-loop-logs
PROMPT_FILE=/tmp/codex-loop-logs/cycle-<N>-prompt.md
LOG_FILE=/tmp/codex-loop-logs/cycle-<N>.log
# Write the prompt to PROMPT_FILE first (Write tool).
codex exec --full-auto "$(cat "$PROMPT_FILE")" \
  > "$LOG_FILE" 2>&1
# Run as a Bash call with run_in_background=true.
```

The `<prompt>` must contain:

- The task description, verbatim from the user.
- The regression gate command.
- An explicit constraint: **run exactly one measure-diagnose-fix-verify cycle,
  then stop. Do not start another cycle.**
- An explicit "do not push" line.
- A short prior-cycle summary so the fresh Codex session does not repeat a
  failed approach, e.g.:

  ```text
  Prior cycles (this session):
  - Cycle 1: touched src/foo/bar.<ext>; failure count 12 → 9
  - Cycle 2: touched src/util/format.<ext>; failure count 9 → 9 (no progress)
  Avoid re-trying: <summary of approaches already tried>
  ```

### Step 2 — Wait for the completion notification

The `codex exec` command was launched via `run_in_background=true` Bash —
Claude receives a completion notification when the background task finishes.
Do not poll status in a loop (this would violate the "No Manual Polling
Loops" guidance in `rules/subagent.md`).

When the notification arrives, read the tail of the log file:

```bash
tail -200 /tmp/codex-loop-logs/cycle-<N>.log
```

Look for the final assistant message, the `tokens used` line, and any
trailing error output. Codex writes its structured summary to stdout, so the
log is the canonical result artifact.

Then record which files changed with `git diff --stat` (read-only; no
commit).

### Step 3 — Check termination

Run the termination check command. Compare the new metric to the value before
this cycle.

- **Satisfied** → break out of the loop, go to the summary.
- **Progressing** (metric improved, target not reached) → continue to the next
  cycle. Update the prior-cycle summary for the next prompt.
- **Stalled** (no measurable progress for two consecutive cycles) → surface the
  stall to the user and ask whether to continue, reshape the prompt, or abort.
  Do not auto-abort — the user chose unlimited iterations, but a silent stall
  wastes tokens without their awareness.
- **Regressed** (metric worse than before this cycle) → ask the user whether to
  revert this cycle's files (`git checkout -- <files>`), keep them and continue,
  or abort. Do not auto-revert; the user may see value in the partial change.

## Summary

When the loop ends, report:

```text
## Codex Loop — Summary

Task: <task>
Termination: <verification command>
Baseline: <starting metric>
Final: <ending metric>
Cycles: <N>

| Cycle | Root cause | Files | Metric before | Metric after |
|-------|-----------|-------|----------------|---------------|
| 1     | ...       | ...   | ...            | ...           |

Terminated because: <condition met | user aborted | stall acknowledged>
```

## Working Rules

- Fresh Codex session every cycle (clean one-shot `codex exec` invocation);
  continuity lives in the prompt text, not in Codex's session state.
- `run_in_background=true` Bash + completion notification; no status polling,
  no `sleep` loops.
- `--full-auto` — Codex auto-approves and edits the working tree directly.
  Do not commit between cycles unless the user explicitly asks.
- One root cause per cycle. If the returned diff bundles unrelated changes,
  flag it to the user before the next cycle.
- Respect the project's regression gate on every cycle — the same gate
  `/fix-loop` enforces.
- Never weaken assertions, skip tests, or add foreign fallback logic to force
  the termination check to pass.
