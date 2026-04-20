---
name: plan-execute
description: >
  Execute a structured plan document by orchestrating major tasks through dedicated subagents.
  Reads a plan-create formatted document, resolves dependencies, spawns one subagent per major
  task, tracks progress via plan document updates, and routes discovered work. Invoke explicitly
  via /plan-execute.
argument-hint: <path to plan document>
---

<!--
  TEMPLATE NOTICE
  ───────────────
  This file is a reusable template shipped from ~/.claude-sync/templates/plan-execute/.
  The skill is language- and tooling-agnostic — the actual L1/L2/L3 verification commands
  live inside the plan document (produced by plan-create), not in this file. You usually
  do not need to edit this template per project; just drop it into .claude/skills/ and
  remove this notice.

  Plan Gate dependency: Phase 0 reads `.claude/data/plan-gate.json` and Phase 3
  transitions it to `executing`. These writes coordinate with a `PreToolUse` hook
  (`.claude/hooks/plan_gate.py`, optional) that blocks Edit/Write/MultiEdit/
  NotebookEdit when planning is incomplete. The gate file itself is the source
  of truth even if the hook is not installed — plan-execute refuses to run when
  it shows `plan-creating` or is missing after a fresh `plan-create` call.
-->

# Plan Execute

Execute a structured plan document by delegating major tasks to dedicated subagents,
tracking progress, and routing discovered work.

## Why this exists

Large projects span multiple sessions and involve many interdependent tasks. Without
a persistent orchestration layer, context is lost between sessions, progress tracking
drifts, and discovered work falls through the cracks. This skill reads a plan document
(produced by `plan-create`) and systematically executes it — one major task at a time,
with verification gates and progress tracking baked in.

## Prerequisites

- A plan document in `plan-create` format
- The plan must contain a `Verification Protocol` table with L1/L2/L3 commands
- The plan must contain at least one major task (T1, T2, ...) with sub-tasks

If `$ARGUMENTS` is a file path, use that as the plan document. Otherwise, search for
`docs/*_plan.md` files and ask the user which plan to execute.

## Workflow

### Phase 0: Verify the Plan Gate

Before parsing the plan, read `.claude/data/plan-gate.json`. The
project's `PreToolUse` hook (`.claude/hooks/plan_gate.py`, if installed)
enforces the same contract — this phase exists so failures are caught
up front with a clear message instead of mid-implementation.

Three cases:

1. **File missing or `stage == "inactive"`** — no `plan-create` has run
   for this plan. Stop and ask the user to either:
   - run `plan-create` first (recommended), or
   - manually mark the gate as approved (only when resuming an
     already-Codex-reviewed plan in a fresh session) by writing
     `.claude/data/plan-gate.json` with
     `{"stage":"plan-approved","plan_path":"<path>","session_id":"…","started_at":"…","approved_at":"…"}`.

2. **`stage == "plan-creating"`** — `plan-create` did not finish its
   adversarial review. Refuse to proceed and tell the user to either
   complete `plan-create` (so it writes `stage: plan-approved`) or
   delete the gate file to start over.

3. **`stage` is `plan-approved` or `executing`** — proceed.

Then, immediately before spawning the subagent in Phase 3, update the
gate to `executing` (preserves all previous fields):

```json
{
  "stage": "executing",
  "plan_path": "<plan path>",
  "session_id": "<current session id>",
  "started_at": "<original>",
  "approved_at": "<original>",
  "execution_started_at": "<ISO 8601 now>"
}
```

### Phase 1: Load and Parse the Plan

1. **Read the plan document** from the path provided
2. **Parse the structure:**
   - Extract the Verification Protocol (L1/L2/L3 commands)
   - Extract Carry-Forward Rules
   - For each major task: status, difficulty, dependencies, files, goal, sub-tasks,
     verification gate
3. **Determine the next executable task:**
   - Skip tasks with status `DONE`, `SKIPPED`, or `DEFERRED`
   - A task is executable when all its dependencies have status `DONE`
   - If multiple tasks are executable, pick the first one in document order
   - If a task is `IN PROGRESS` with some sub-tasks DONE, this is a **resume**
     scenario — see "Crash Recovery" in Phase 2
4. **Show the user** which task will be executed next, its sub-tasks, and estimated
   scope. Get confirmation before proceeding.

### Phase 2: Pre-flight Checks

Before spawning the subagent:

1. **Git state** — run `git status` and `git diff --stat`.
2. **Crash recovery** — check for three cases:

   **Case A: IN PROGRESS + 0 DONE sub-tasks + uncommitted changes.**
   The subagent crashed while implementing the first sub-task.
   - Show the user the diff and identify which sub-task it likely belongs to
     (the first one in the table)
   - Ask the user: **keep and commit** (treating as the first sub-task), or
     **discard** (`git checkout -- .`)

   **Case B: IN PROGRESS + DONE sub-tasks + uncommitted changes.**
   The subagent crashed mid-sub-task after completing earlier ones.
   - Show the user the diff and the last completed sub-task
   - The uncommitted changes likely belong to the next incomplete sub-task
   - Ask the user: **keep and commit**, or **discard** (`git checkout -- .`)

   **Case C: IN PROGRESS + DONE sub-tasks + clean working tree.**
   The subagent completed a code commit but crashed before the plan-update
   commit — the plan doesn't reflect the latest completed work.
   - Run `git log --oneline -10` and compare recent commit messages against
     incomplete sub-task descriptions
   - If a matching commit is found: update the plan to mark that sub-task as
     DONE with the found SHA, then commit the plan update
   - If no match: report the inconsistency to the user for manual resolution

   After any case is resolved, the subagent will resume from the first sub-task
   without DONE status.

3. **Clean working tree** — if there are uncommitted changes but NO task is
   IN PROGRESS, ask the user to commit or discard them before proceeding.
4. **Dependency verification** — confirm that dependency tasks are truly `DONE`
   (check the plan document, not just memory).

### Phase 3: Spawn Subagent for Major Task

Spawn a single subagent (using the Agent tool) with the following prompt structure.
The subagent receives everything it needs to work autonomously.

**Model requirement:** always spawn the Agent with the largest-context model
available (e.g. Claude Opus 4.7 1M-context or equivalent). Plan-execute
subagents perform multi-gate tasks (sub-task code edits + L1 + optional L2 +
L3 verification + verification-gate checks) that reliably overflow a standard
context window; a mid-verification bail-out leaves the working tree dirty,
no commits made, and requires either crash-recovery (Phase 2) or main-agent
takeover. The larger window prevents this. Do not downgrade to a smaller
model even for "simple" sub-tasks — the verification tail alone consumes
most of a standard context window.

**Subagent prompt template:**

The prompt MUST include these sections in order. Fill in values from the plan document.
Do not wrap Remaining Works format in a code fence (to avoid nested fence issues).

~~~~
You are executing Major Task T<N> from a structured plan.

## Your Mission
<goal from the plan>

## Context
<context section from the plan — keep concise; if the plan references a separate
file for detailed context, tell the subagent to read that file>

## Files (guidance)
<files from the plan — these indicate where to start looking, not a hard restriction>

## Sub-tasks (execute in order)
<sub-task table from the plan>
If some sub-tasks already have status DONE or SKIPPED, skip them — resume from
the first sub-task with an empty Status column.

For each sub-task:

**Step 1 — Implement** the change.

**Step 2 — Verify.** Run L1: `<L1 command>`
If this sub-task has L2 marked `yes`, also run L2: `<L2 command>`

**If verification fails** (code is NOT yet committed):
- Path A (simple fix): diagnose, fix, re-run verification
- Path B (needs future task): run `git diff --name-only` to identify changed
  files, then **discard** them (`git checkout -- <file1> <file2> ...`).
  Update the sub-task's plan row with Status `SKIPPED` and Notes explaining
  why (e.g., "L1 fail — needs T5 first"). Commit the plan update:
  `docs(plan): skip T<N> sub-task <X.Y> — blocked by T5`.
  Report in Remaining Works with the dependency.
- Path C (non-trivial): same as Path B, but report as Remaining Works for
  a new Major Task instead of an existing one.
Do NOT commit code that fails verification.

**Step 3 — Commit** the code change:
`<type>(<scope>): <sub-task description>`
Choose the appropriate type: feat, fix, refactor, test, docs, perf, chore.

**Step 4 — Update the plan** at `<plan-path>`:
Replace the sub-task's ENTIRE table row with the updated version.
Example — before:
  `| 1.1 | Implement feature X | yes | | | |`
After:
  `| 1.1 | Implement feature X | yes | DONE | abc1234 | Fixed edge case |`
Always match and replace the full row from first `|` to last `|`.
Fill the Commit column with the short SHA from Step 3.

**Step 5 — Commit** the plan update:
`docs(plan): update T<N> sub-task <X.Y> status`

**Step 6** — Move to the next sub-task.

## Carry-Forward Rules
<rules from the plan>

## L3 Verification and Regression Protocol
After completing all sub-tasks (or when stopping early due to context pressure),
run L3 verification: `<L3 command>`

**If L3 passes** → proceed to Verification Gate below.

**If L3 fails (regression detected):**
1. Identify which sub-task commit(s) caused the regression
2. Choose ONE path:

   **Path A — Simple fix, resolvable now:**
   Fix it, add a new sub-task row to the plan, commit (code + plan separately),
   and re-run L3.

   **Path B — Requires a future Major Task's work:**
   The regression needs work that a later task (e.g., T5) will provide.
   Revert the causing commit(s) with `git revert <SHA>`, update their sub-task
   Status to `REVERTED` in the plan (+ plan commit), and note in Remaining Works
   that this sub-task should be re-attempted after T5. Include the dependency:
   "re-attempt after T5".

   **Path C — Non-trivial new work needed:**
   Revert the causing commit(s), update sub-task Status to `REVERTED` (+ plan
   commit), and report as Remaining Works recommending a new Major Task.

## Verification Gate
<gate criteria from the plan>
After L3 passes, check each criterion:
- **Automated criteria** (test results, metrics, measurable thresholds): verify
  them yourself and report pass/fail.
- **Manual criteria** (API compatibility, design review, subjective quality): flag
  them as NEEDS REVIEW — the main agent will confirm these with the user.

## Remaining Works
Collect any out-of-scope work discovered during implementation and report at the end.
Include reverted sub-tasks with their re-attempt dependencies.

Format (plain text in your final output):

  REMAINING WORKS:
  - <description> → suggested target: T5
  - <description> → suggested target: NEW
  - <reverted sub-task 2.3> → re-attempt after T5 (dependency: T5)

## Context Window Management
If you notice context pressure (very long conversation, difficulty recalling earlier
instructions, tool results getting truncated), stop after finishing the current
sub-task's commit cycle:
1. Complete the current sub-task (Steps 1–6)
2. Proceed directly to L3 Verification (even if sub-tasks remain)
3. Report uncompleted sub-tasks — the main agent will spawn a fresh subagent

## Important Rules
- Two commits per sub-task: code change first, then plan document update
- Choose the correct commit type (feat/fix/refactor/test/docs/perf/chore)
- Do NOT push — the main agent handles push
- Do NOT commit code that fails verification
- Read source code before modifying — never guess APIs or attribute names
- When editing the plan's sub-task table, always replace the ENTIRE row
~~~~

### Phase 4: Process Subagent Results

When the subagent completes:

1. **Read the updated plan document** — verify sub-task statuses and commit SHAs
   were filled in by the subagent. Check for any REVERTED sub-tasks.
2. **Check sub-task completion** — if some sub-tasks still have an empty Status
   column (subagent bailed out early due to context pressure or failure):
   - Do NOT mark the Major Task as DONE yet
   - **Progress check**: compare which sub-tasks were DONE before this subagent
     started vs. now. If the subagent completed **zero new sub-tasks** (bailed out
     on the same sub-task as the previous attempt), do NOT re-spawn. Instead,
     report to the user that this sub-task may be too large for a single subagent
     and recommend splitting it in the plan.
   - If progress was made: process Remaining Works (Step 4), then report
     progress to the user (which sub-tasks completed, which remain, L3 results).
     Do NOT enter Phase 5's Finalize block — the task is not complete yet.
     Ask the user whether to continue (loop back to **Phase 3** for a fresh
     subagent) or stop here.
3. **Verify L3 was run** — check the subagent's output for L3 results. If the
   subagent failed to run L3 (e.g., crashed before reaching that step), run L3 now.
4. **Check for Remaining Works** in the subagent's output:
   - If work fits a **future** major task's scope → add to that task's sub-tasks
   - If work fits no existing task → create a new major task and append to the plan
   - If work is a re-attempt of a REVERTED sub-task with a dependency (e.g.,
     "re-attempt after T5") → create a follow-up task with that dependency:
     `T<new>: Follow-up — T<N> re-attempts` with `Dependencies: T5`
5. **Handle terminal failure cases** (no user confirmation needed):
   - If ALL sub-tasks were REVERTED → set major task to `DEFERRED` with a note
     explaining which dependency to wait for, plus a cross-reference to the
     follow-up task: "Deferred until after T5. See T10 for re-attempts."
     If the task itself is fundamentally wrong rather than blocked by a
     dependency → set to `SKIPPED` with reason.
   - Update Summary table, `Current State` (from L3 output), and `Last updated`.
   - Commit all updates now and proceed to Phase 5 (no gate check needed).
6. **Prepare plan updates** (do NOT commit yet):
   - Update `Current State` — refresh test counts / metrics from L3 output
   - Update `Last updated` — today's date and brief description
   - Do NOT mark the major task as DONE yet — Phase 5 must confirm the
     Verification Gate first

### Phase 5: Report and Continue

Report to the user:
- Which major task was completed (or partially completed)
- L3 verification results (pass/fail, any regressions)
- **Verification Gate results** — present automated criteria pass/fail, and ask
  the user to confirm any criteria flagged as NEEDS REVIEW by the subagent.
  Do NOT mark the task as DONE until all gate criteria are confirmed.
- REVERTED sub-tasks and their re-attempt plan (if any)
- DEFERRED/SKIPPED decisions (if any)
- Remaining Works that were routed
- Current overall progress (X of Y tasks done)
- Which major task is next (if any)

**Finalize the Major Task:**
- Once the user confirms all NEEDS REVIEW gate criteria (or if all criteria
  were automated and passed), mark the major task as `DONE`.
- If the user rejects a manual gate criterion, do NOT mark as DONE. Discuss
  with the user whether to fix it now (spawn another subagent) or defer.
- Update the Summary table to reflect the final status.
- **Commit** all pending plan updates:
  `docs(plan): complete T<N> — update status and summary`

**Ask the user:**
1. Whether to **push** the completed work to remote
2. Whether to **continue** with the next task or stop here

If continuing, loop back to Phase 1 (re-read the plan to get fresh state).

### Phase 6: Codex Implementation Review (MANDATORY when Codex is available)

After the major task is finalised in Phase 5 (status `DONE`, Summary
table updated, plan commit made), run a Codex review of the actual
code changes shipped in this iteration. This is the implementation-
side counterpart of plan-create's Phase 4.5 — do not skip it when
Codex is installed.

**Precondition — Codex availability check**

Before invoking any `/codex:*` command, verify Codex is installed:

1. **CLI**: `command -v codex` returns a path (e.g. `/usr/bin/codex`).
2. **Plugin**: the `openai-codex/codex` plugin is installed — either
   `~/.claude/plugins/cache/openai-codex/codex/` exists, or
   `~/.claude/plugins/installed_plugins.json` contains a
   `codex@openai-codex` entry, or the `/codex:review` skill appears
   in the available skills list for this session.

If either check fails, **skip this phase** and emit a one-line notice to
the user:

> Codex CLI or plugin not installed — skipping implementation review.
> Install the `codex` CLI and the `codex@openai-codex` plugin to enable it.

Still release the plan-gate before returning control to the user — the next
session should not be blocked by a stale `executing` state regardless of
whether the review ran. Use the *stage-selection rule* in the post-review
block below (end of Phase 6): `plan-approved` when the plan still has
unfinished Major Tasks, `inactive` (or delete the file) when the plan is
fully complete or the user is abandoning it.

Steps (run only when the precondition above passes):

1. Determine the diff scope:
   - Single completed major task → review every sub-task commit made
     in this run. Capture the pre-task SHA before Phase 3
     (`git rev-parse HEAD` at that point) so it can be passed as the
     base.
   - Multiple tasks completed in one run → review the full span from
     the first pre-task SHA to current HEAD.
2. **Push the branch to origin before invoking the review.** Codex's
   review sandbox blocks local `bash`/`git diff <sha>` invocations, so
   the only diff source that reliably works is GitHub via the Codex
   GitHub MCP (`codex_apps/github_compare_commits` /
   `github_fetch_file`). If the branch is not pushed, the remote view
   of `<pre-task-sha>..HEAD` is empty and the review returns
   "no actionable defects" because it never saw the changes. Ask the
   user for explicit approval before pushing if project git rules
   prohibit unprompted pushes. Typical command:

   ```bash
   git push origin <current-branch>
   ```

   If the user declines to push, either defer Phase 6 (leave the gate
   at `executing` for resume) or skip the review with explicit user
   acknowledgement that the implementation is unreviewed.
3. Invoke (only after push succeeds):

   ```
   /codex:review --background --base <pre-task-sha>
   ```

   Use `--background` so the review does not block follow-up actions
   (it is typically non-trivial). Track progress with `/codex:status`
   and pull the result with `/codex:result` once complete. Codex's
   model is governed by `~/.codex/config.toml`.
4. When the review completes, surface findings to the user and
   classify each one:
   - **Bug** or **test gap** → propose a follow-up sub-task on the
     completed major task or, if out of scope, a new major task.
     Append it via the same plan-update mechanism used during Phase 4.
   - **Over-engineering** or **simpler-alternative** → present the
     suggestion; let the user decide whether to refactor now or defer.
   - **Informational** → report briefly, no action.
5. **Do not** auto-apply Codex suggestions. The user owns the decision.

After the review is complete (or running in the background and
acknowledged by the user), transition the gate out of `executing` so the
next session is not blocked by a stale state. The correct target stage
depends on whether the plan still has unfinished work:

**Stage-selection rule:**

- *Plan still has Major Tasks that are NOT STARTED or IN PROGRESS (the
  common case — one task just finished, others remain):* set stage to
  `plan-approved`. The plan is still the active, Codex-reviewed
  execution artifact; the next `plan-execute` invocation should resume
  on the next executable task without requiring a fresh `plan-create`
  cycle.

  ```json
  {
    "stage": "plan-approved",
    "plan_path": "<plan path>",
    "session_id": "<same as before>",
    "started_at": "<original>",
    "approved_at": "<original>",
    "execution_started_at": "<original, optional>",
    "last_completed_task": "T<N>",
    "last_completed_at": "<ISO 8601 now>"
  }
  ```

- *Plan is fully DONE (all Major Tasks in final status: DONE / DEFERRED
  / SKIPPED with no executable tasks left), or the user is abandoning
  the plan:* set stage to `inactive`, or delete the file outright.

  ```json
  {"stage": "inactive"}
  ```

  ```bash
  rm "$CLAUDE_PROJECT_DIR/.claude/data/plan-gate.json"
  ```

If the user chose to defer the Codex review (e.g. they want to push
first), leave the gate at `executing` and the next plan-execute
invocation will resume from there.

---

## Plan Document Format Reference

The plan document must follow the `plan-create` format. Key elements this skill
depends on for parsing:

### Required Sections

- **Verification Protocol** — table with Level, Command, When columns
- **Carry-Forward Rules** — bulleted list of plan-specific invariants
- **Major Task sections** — headed with `## T<N>: Task Name`
  - **Status:** line
  - **Dependencies:** line (None or comma-separated like T1, T2)
  - **Files:** line (informational guidance)
  - **Goal:** line
  - **Sub-tasks** table with #, Description, L2, Status, Commit, Notes columns
  - **Verification Gate** — bulleted criteria
- **Summary** table at the bottom

### Status Values

**Sub-task status:**

| Status | Meaning |
|--------|---------|
| *(empty)* | Not started |
| DONE | Completed and committed |
| SKIPPED | Verification failed; discarded and deferred (Path B/C). Notes must explain why. |
| REVERTED | Committed but later git-reverted due to L3 regression |

**Major Task status:**

| Status | Meaning |
|--------|---------|
| NOT STARTED | No work has begun |
| IN PROGRESS | Subagent is currently working on this task |
| DONE | All sub-tasks complete, verification gate passed |
| DEFERRED | All sub-tasks reverted; re-attempt after a specified dependency. Notes must explain which task and why. |
| SKIPPED | Task determined unnecessary or fundamentally wrong. Notes must explain why. |

### Sub-task Table Editing

The sub-task table is the primary progress tracking mechanism. To ensure reliable
editing by the subagent:

- Each row is uniquely identifiable by its sub-task number (e.g., `| 1.1 |`)
  combined with its description
- Always replace the **entire row** from first `|` to last `|`
- Never attempt to edit individual cells within a row
- The sub-task number uses `<major>.<sub>` format (1.1, 1.2, 2.1) which is
  globally unique across the entire document

## Resuming Across Sessions

This skill is designed to survive session boundaries. When invoked in a new session:

1. It reads the plan document (which is committed to git)
2. It finds the next task: either an `IN PROGRESS` task to resume, or the next
   `NOT STARTED` task whose dependencies are `DONE`
3. For resumed tasks, the subagent skips sub-tasks already marked DONE or SKIPPED
4. Crash recovery handles any uncommitted changes from a previous session

No memory or context from the previous session is needed — the plan document is the
single source of truth.

## Error Handling

- **Subagent context exhaustion** — subagent stops early, runs L3, reports remaining
  sub-tasks. Phase 4 detects incomplete sub-tasks and spawns a fresh subagent.
- **Subagent crashes** — Phase 2 crash recovery handles three cases: dirty tree
  with no DONE sub-tasks (Case A), dirty tree with some DONE (Case B), and clean
  tree with plan/git desync (Case C).
- **L1/L2 verification fails** (pre-commit) — subagent applies 3-path protocol.
  Path A: fix. Path B: **discard** uncommitted changes + skip + defer.
  Path C: **discard** + skip + new task.
- **L3 verification fails** — subagent follows regression protocol (Path A/B/C).
- **All sub-tasks REVERTED** — major task becomes DEFERRED (with dependency) or
  SKIPPED (if fundamentally wrong). Main agent creates follow-up tasks as needed.
- **Dependency cycle detected** — report to user, ask to resolve plan structure.
- **All tasks DONE** — report completion and show the final Summary table.

## Important Notes

- Two commits per sub-task: code change, then plan document update (solves SHA timing)
- Main agent commits Phase 4 plan updates (Summary, Current State, task status)
- Push is offered to the user after each major task — never automatic
- One major task at a time — never run multiple major tasks in parallel
- Re-read the plan at the start of each iteration (subagent may have added/reverted)
- Summary table is maintained by the main agent only — subagents update individual
  sub-task rows, main agent reconciles the Summary
- General project rules (CLAUDE.md, `.claude/rules/`) are inherited automatically —
  the plan's Carry-Forward Rules contain only plan-specific additions
- Files field is guidance, not restriction — subagents may modify other files if needed
