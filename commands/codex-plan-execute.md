---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, AskUserQuestion
description: Execute a structured plan document by dispatching major tasks to Codex CLI sessions instead of Claude subagents. Review phase uses Claude subagents. Reads a /plan-create formatted document, resolves dependencies, dispatches one Codex session per major task, tracks progress, and routes discovered work.
argument-hint: <path to plan document>
---

# Codex Plan Execute

Execute a structured plan document by delegating major tasks to **Codex CLI
sessions** instead of Claude subagents. The review phase (Phase 6) uses a
**Claude subagent** for deliverable review — the inverse of `/plan-execute`,
which uses Claude subagents for execution and Codex for review.

## Why this exists

Codex brings a different model's strengths to the implementation phase. By
dispatching each major task to a Codex CLI session, this command leverages
Codex's coding capabilities while keeping Claude's orchestration, crash
recovery, and review oversight. The trade-off: Codex cannot be steered
mid-task the way a Claude subagent can, so the prompt must be fully
self-contained.

## Prerequisites

- A plan document in `/plan-create` format (default location: `plans/<name>_plan.md`)
- The plan must contain a `Verification Protocol` table with L1/L2/L3 commands
- The plan must contain at least one major task (T1, T2, ...) with sub-tasks
- **Codex CLI** must be installed and authenticated. Quick check:

  ```bash
  command -v codex
  ```

  If Codex is missing, stop and tell the user to install it
  (e.g. `npm i -g @openai/codex`).

If `$ARGUMENTS` is a file path, use that as the plan document. Otherwise, search
`plans/*.md` and `docs/*_plan.md` and ask the user which plan to execute.

## Workflow

### Phase 0: Verify the Plan Gate

Before parsing the plan, read `.claude/data/plan-gate.json`.

Three cases:

1. **File missing or `stage == "inactive"`** — no `/plan-create` has run for this
   plan. Stop and ask the user to either run `/plan-create` first, or manually
   mark the gate as approved. If the user chooses manual approval, write the
   gate file with all required fields:
   ```json
   {"stage":"plan-approved","plan_path":"<path>","session_id":"<unknown>","started_at":"<unknown>","approved_at":"<ISO 8601 now>"}
   ```

2. **`stage == "plan-creating"`** — `/plan-create` did not finish. Refuse to
   proceed.

3. **`stage` is `plan-approved` or `executing`** — proceed.

Update the gate to `executing` before dispatching in Phase 3:

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

Before dispatching to Codex:

1. **Git state** — run `git status` and `git diff --stat`.
2. **Crash recovery** — same three cases as `/plan-execute`:

   **Case A: IN PROGRESS + 0 DONE sub-tasks + uncommitted changes.**
   - Show the user the diff
   - Ask: **keep and commit**, or **discard** (`git checkout -- .`)

   **Case B: IN PROGRESS + DONE sub-tasks + uncommitted changes.**
   - Show the user the diff and last completed sub-task
   - Ask: **keep and commit**, or **discard**

   **Case C: IN PROGRESS + DONE sub-tasks + clean working tree.**
   - Compare `git log --oneline -10` against incomplete sub-task descriptions
   - If match found: update plan, commit plan update
   - If no match: report to user

3. **Clean working tree** — ask user to commit or discard stray changes.
4. **Dependency verification** — confirm deps are truly `DONE`.

### Phase 3: Dispatch Codex Session for Major Task

Dispatch a single Codex session for the major task. The prompt must be fully
self-contained because Codex runs fresh each time with no prior context.

**Compose the Codex prompt** with these sections:

~~~~
You are executing Major Task T<N> from a structured execution plan.

## Your Mission
<goal from the plan>

## Context
<context section from the plan — if the plan references a separate file for
detailed context (e.g. plans/refs/*.md), read that file and include its content>

## Project Context
<Inline the project's invariants here so the Codex session sees them despite
running with no prior conversation context. Pull from the project's CLAUDE.md
and `.claude/rules/` and quote only the rules that apply to this task. Do not
hand Codex the entire CLAUDE.md verbatim — quote the load-bearing constraints.
Examples of what belongs here: API stability requirements, performance
budgets, "do not weaken X" invariants, required reading before touching
specific subsystems.>

## Files (guidance — not a hard restriction)
<files from the plan>

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
- Path B (needs future task): discard changes (`git checkout -- <files>`).
  Update the sub-task row in the plan at `<plan-path>` with Status `SKIPPED`
  and Notes explaining why. Commit the plan update:
  `docs(plan): skip T<N> sub-task <X.Y> — blocked by T<M>`.
  Report in Remaining Works with the dependency.
- Path C (non-trivial): same as Path B, report as new Major Task.
Do NOT commit code that fails verification.

**Step 3 — Commit** the code change:
`<type>(<scope>): <sub-task description>`

**Step 4 — Update the plan** at `<plan-path>`:
Replace the sub-task's ENTIRE table row. Fill Commit with the short SHA.

**Step 5 — Commit** the plan update:
`docs(plan): update T<N> sub-task <X.Y> status`

**Step 6** — Move to the next sub-task.

## Carry-Forward Rules
<rules from the plan>

## L3 Verification
After completing all sub-tasks (or when stopping), run L3: `<L3 command>`

**If L3 fails:**
- Path A — Simple fix: fix, add sub-task row, commit, re-run L3
- Path B — Needs future task: `git revert <SHA>`, mark REVERTED in plan,
  note in Remaining Works
- Path C — Non-trivial: revert, mark REVERTED, report as new Major Task

## Verification Gate
<gate criteria from the plan>
After L3 passes, check automated criteria and report pass/fail.
Flag manual criteria as NEEDS REVIEW.

## Remaining Works
Report any discovered out-of-scope work at the end:

  REMAINING WORKS:
  - <description> → suggested target: T5
  - <description> → suggested target: NEW

## Context Window Management
If you are running low on context (long conversation, difficulty recalling earlier
instructions), stop after finishing the current sub-task's commit cycle:
1. Complete the current sub-task (Steps 1–6)
2. Proceed directly to L3 Verification (even if sub-tasks remain)
3. Report uncompleted sub-tasks — the orchestrator will dispatch a fresh session

## Important Rules
- Two commits per sub-task: code first, then plan update
- Do NOT push
- Do NOT commit code that fails verification
- Read source code before modifying — never guess APIs
- Replace ENTIRE plan table rows when updating
- Run exactly the sub-tasks listed, then stop
~~~~

**Dispatch the prompt:**

```bash
mkdir -p /tmp/codex-plan-logs
PROMPT_FILE=/tmp/codex-plan-logs/T<N>-prompt.md
LOG_FILE=/tmp/codex-plan-logs/T<N>.log
# Write the prompt to PROMPT_FILE first (Write tool).
codex exec --full-auto "$(cat "$PROMPT_FILE")" \
  > "$LOG_FILE" 2>&1
# Run as Bash with run_in_background=true.
```

### Phase 3.5: Wait for Codex Completion

Do NOT poll status in a loop. The `codex exec` command was launched via
`run_in_background=true` Bash — Claude receives a completion notification
when the background task finishes. After the notification arrives, read the
result from the log file:

```bash
tail -200 /tmp/codex-plan-logs/T<N>.log
```

Look for the final assistant message, the `tokens used` line, and any trailing
error output. Codex writes its structured summary to stdout, so the log is the
canonical result artifact.

Record changed files: `git diff --stat` (read-only; no commit).

### Phase 4: Process Codex Results

When Codex completes:

1. **Read the updated plan document** — verify sub-task statuses and commit SHAs.
2. **Check sub-task completion:**
   - **Progress check**: if **zero new sub-tasks** completed, do NOT re-dispatch.
     Report to the user that this sub-task may need manual intervention or
     a different approach.
   - If progress was made: process Remaining Works, report progress, ask the
     user whether to continue (loop back to Phase 3) or stop.
3. **Verify L3 was run** — if Codex failed to run L3, run it now from the
   orchestrator.
4. **Check for Remaining Works** in Codex's output:
   - Work that fits a future task → add sub-tasks
   - Work that fits no existing task → create new major task
   - Reverted re-attempts → create follow-up task with dependency
5. **Handle terminal failure cases:**
   - ALL sub-tasks REVERTED → set to `DEFERRED` or `SKIPPED`
   - Update Summary, Current State, Last updated
   - Commit and proceed to Phase 5
6. **Prepare plan updates** (do NOT commit yet):
   - Update Current State from L3 output
   - Update Last updated
   - Do NOT mark task as DONE yet — Phase 5 confirms the gate

### Phase 5: Report and Continue

Report to the user:
- Which major task was completed (or partially completed)
- L3 verification results
- **Verification Gate results** — automated pass/fail + NEEDS REVIEW items
- REVERTED sub-tasks and re-attempt plan
- Remaining Works that were routed
- Current overall progress (X of Y tasks done)
- Which major task is next

**Finalize the Major Task:**
- Once the user confirms all gate criteria, mark as `DONE`.
- Update Summary table.
- **Commit**: `docs(plan): complete T<N> — update status and summary`

Proceed to Phase 6 review before offering push/continue.

### Phase 6: Claude Subagent Deliverable Review (MANDATORY)

After the major task is finalised in Phase 5, run a **Claude subagent** review
of all deliverables shipped in this iteration. This is the inverse of
`/plan-execute`'s Phase 6 (which uses Codex for review) — here Claude reviews
Codex's implementation.

**Scope**: Phase 6 applies to every major task that produced a deliverable:
- **Code tasks** → review code changes via diff
- **Document tasks** → review document content
- **Mixed tasks** → review both

Steps:

0. **Capture pre-Phase-6 SHA:** `phase6_pre_sha = $(git rev-parse HEAD)`

1. **Determine review scope.** Capture the pre-task SHA (the `git rev-parse
   HEAD` snapshot taken before Phase 3 dispatch — the diff base). Build the
   scope from up to two parts: a **committed range** and an **uncommitted
   set**. Either part can be empty; both empty means there is nothing to
   review and Phase 6 should abort with an error to the user.

   **Committed range** — populated when there are commits in
   `<pre-task-sha>..HEAD`:

   ```bash
   COMMIT_RANGE_LOG=$(git log --oneline "<pre-task-sha>..HEAD")
   COMMIT_RANGE_STAT=$(git diff --stat "<pre-task-sha>..HEAD")
   COMMIT_RANGE_DIFF=$(git diff "<pre-task-sha>..HEAD")
   ```

   If `COMMIT_RANGE_LOG` is empty, leave the committed-range fields blank
   when assembling the prompt.

   **Uncommitted set** — populated when the deliverable lives (in whole or
   in part) in the working tree. This branch fires whenever there are
   uncommitted/untracked changes at the time Phase 6 runs, regardless of
   whether `<pre-task-sha>..HEAD` is empty. The reason: with a Phase 5
   plan-update commit, `<pre-task-sha>..HEAD` is rarely empty, so a "no
   commits" trigger would never fire — but the actual deliverable can
   still be uncommitted (e.g. a code task whose Codex session forgot to
   commit, or a document task orchestrated outside the subagent commit
   cycle).

   Detect uncommitted material by checking BOTH:

   ```bash
   git diff --quiet HEAD || UNCOMMITTED_TRACKED=yes      # tracked unstaged + staged differs from HEAD
   [ -n "$(git ls-files --others --exclude-standard)" ] && UNCOMMITTED_UNTRACKED=yes
   ```

   If either flag is set, build the uncommitted scope as:

   1. **Per-file enumeration** — covers tracked changes (unstaged AND
      staged AND deletions) plus untracked additions:

      ```bash
      UNCOMMITTED_FILES=$(
        { git diff --name-only HEAD;
          git ls-files --others --exclude-standard;
        } | sort -u
      )
      ```

      `git diff --name-only HEAD` lists every tracked path that differs
      from `HEAD` (so staged-only edits and tracked deletions are
      covered). `git ls-files --others --exclude-standard` lists
      untracked additions one-per-file (whereas `git status --short`
      would only emit `?? dir/` shorthand for untracked directories
      and miss the files inside).
   2. **Tracked-change diff**: `git diff HEAD` (covers unstaged AND
      staged changes against HEAD, including deletions).
   3. **Untracked new-file diffs**: for each path from
      `git ls-files --others --exclude-standard`, render a synthetic
      new-file diff via `git diff --no-index -- /dev/null <path>`
      (returns 1 on differences, which is the normal case — swallow
      the exit code).

   Concatenate (2) and (3) into `UNCOMMITTED_DIFF`. Set `UNCOMMITTED_STAT`
   to `UNCOMMITTED_FILES` (the per-file list from (1)).

   **Empty-scope abort.** If both `COMMIT_RANGE_DIFF` and `UNCOMMITTED_DIFF`
   are empty, stop Phase 6 and report the problem — there is nothing to
   review. Do NOT spawn the subagent on an empty scope.

   When BOTH parts are non-empty (Codex committed some sub-tasks and
   left others uncommitted), include both in the prompt — the
   subagent reviews everything that constitutes the deliverable.

2. **Spawn Claude review subagent** (Agent tool — always spawn with the
   largest-context model available, e.g. `model: "opus"` at the time of
   writing; do not downgrade to a smaller model):

   ~~~~
   You are reviewing a Codex-authored implementation that just completed Major
   Task T<N> from a structured plan.

   ## Review Mission
   Surface correctness bugs, test gaps, project-invariant regressions,
   over-engineering, simpler alternatives, and regression risks.

   ## Project Context
   <Inline the project's invariants from CLAUDE.md / `.claude/rules/` here, so
   the review subagent can judge "regression" against the actual rules. Quote
   only the load-bearing constraints, not the entire ruleset.>

   ## Review Criteria

   ### Code Tasks
   - Functional bugs and edge cases
   - Project-invariant regressions (use the Project Context above as the bar)
   - Parser or file-handling safety risks
   - Performance regressions in hot paths
   - Test coverage gaps — are new behaviors tested?
   - Commit hygiene — one work unit per commit, tests travel with code

   ### Document Tasks
   Apply the canonical document-deliverable criteria (verbatim from
   `/plan-execute.md` — keep word-for-word identical across all four
   review-path copies):
   - All cited file paths and line numbers are verifiable via `grep` against the actual codebase.
   - No claims about code behaviour that contradict the actual implementation.
   - Internal consistency: no contradictions between sections within the same document, or between this deliverable and existing `.claude/rules/` content / other plan documents.
   - Policy vs runtime distinction (when applicable): decided policy is not presented as current runtime behaviour.
   - Migration roadmap completeness: all identified NEEDS_MIGRATION items are covered by sub-tickets with correct dependency ordering.
   - Cross-reference accuracy: ticket IDs, rule IDs, and external references are correct.

   ## Severity Classification
   - [critical] ship-blocker
   - [high]     must-fix before the next task
   - [medium]   should-fix this cycle
   - [low]      nice-to-have
   - [info]     observation only

   ## Commits (committed range)
   <COMMIT_RANGE_LOG — leave blank if no commits in <pre-task-sha>..HEAD>

   ## Changed Files (committed range)
   <COMMIT_RANGE_STAT — leave blank if no commits>

   ## Diff (committed range)
   <COMMIT_RANGE_DIFF — leave blank if no commits>

   ## Uncommitted Files (working tree)
   <UNCOMMITTED_STAT — per-file list (UNCOMMITTED_FILES) built from
   `git diff --name-only HEAD` (tracked unstaged + staged + deletions) plus
   `git ls-files --others --exclude-standard` (untracked additions),
   sort -u'd; leave blank if no uncommitted/untracked changes>

   ## Diff (uncommitted)
   <UNCOMMITTED_DIFF — git diff HEAD plus per-untracked-file new-file
   diffs; leave blank if no uncommitted/untracked changes>

   Either or both of the two scope sections may be populated; review
   everything that is non-empty as part of the deliverable.

   Read the actual source files when the diff alone is not enough to judge
   correctness. Use Grep/Read to verify claims about existing behavior.

   Report findings with: severity, file:line, issue, impact, and fix direction.
   Do NOT auto-apply fixes — report only.
   ~~~~

3. **Process review findings:**
   - **Bug** or **test gap** → propose follow-up sub-task on the plan
   - **Factual error** (document) → fix if trivial, else follow-up
   - **Consistency issue** → flag contradictions
   - **Over-engineering** → present for user decision
   - **Informational** → note briefly

4. **Do not** auto-apply suggestions. The user owns every decision.

5. **Route accepted findings** to the plan:
   - Add follow-up sub-tasks to existing tasks, or create new major tasks
   - Commit plan updates

6. **Squash Phase 6 plan commits.** Collapse plan-document commits made during
   Phase 6 into a single commit:

   - Skip if `git rev-list --count <phase6_pre_sha>..HEAD` is `0`
   - Safety check: all modified files must be plan documents
   - Soft-reset + recommit:
     ```bash
     git reset --soft <phase6_pre_sha>
     git commit -m "docs(plan): apply T<N> Claude review feedback"
     ```
   - Force-push only with explicit user approval, `--force-with-lease`, never
     on `main`

**Gate cleanup after Phase 6:**

- If the user chose to **defer** the review (e.g. "I'll review later"), leave
  the gate at `executing` so the next `/codex-plan-execute` invocation resumes
  from Phase 6.
- Only clear/delete the gate when Phase 6 review is actually complete. Use the
  same stage-selection rule as `/plan-execute`:

  - Plan still has Major Tasks NOT STARTED or IN PROGRESS → set stage to
    `plan-approved` (the next invocation resumes on the next executable task).
  - Plan fully DONE / abandoned → set stage to `inactive`, or delete the file:

    ```bash
    rm "$CLAUDE_PROJECT_DIR/.claude/data/plan-gate.json"
    ```

**Ask the user** (after gate cleanup):
1. Whether to **push**
2. Whether to **continue** with the next task or stop

If continuing, loop back to Phase 1.

---

## Differences from /plan-execute

| Aspect | /plan-execute | /codex-plan-execute |
|--------|--------------|---------------------|
| Phase 3 executor | Claude subagent (Agent tool) | Codex CLI session |
| Phase 6 reviewer | Codex CLI (`/codex-review`) | Claude subagent (Agent tool) |
| Mid-task steering | Possible (subagent in context) | Not possible (Codex runs independently) |
| Prompt requirements | Can reference conversation context | Must be fully self-contained |
| Dispatch | Single (Agent tool) | `codex exec --full-auto` via Bash |

## When to use which

- **`/plan-execute`** — when tasks require nuanced judgment, mid-task steering,
  or heavy interaction with the plan orchestrator during execution.
- **`/codex-plan-execute`** — when tasks are well-defined with clear verification
  gates, and you want a different model's implementation perspective. Also useful
  for parallelism: Codex runs independently while Claude can do other work.

## Resuming Across Sessions

Same as `/plan-execute` — the plan document is the single source of truth.
Crash recovery (Phase 2) handles all three cases identically.

## Error Handling

- **Codex timeout / crash** — Phase 4 detects incomplete sub-tasks. If zero
  progress, report to user (do not re-dispatch blindly).
- **Codex produces invalid changes** — Phase 6 Claude review catches issues.
  User decides whether to fix or revert.
- **Codex exec fails to start** — report to user with error output.
- **All other cases** — same as `/plan-execute`.

## Important Notes

- Two commits per sub-task: code change, then plan document update
- Main agent commits Phase 4 plan updates
- Push is offered — never automatic
- One major task at a time — never parallel Codex dispatches
- Re-read the plan at the start of each iteration
- Codex prompt must be fully self-contained (no conversation context)
- Summary table is maintained by the main agent only
- General project rules are included in the Codex prompt explicitly
