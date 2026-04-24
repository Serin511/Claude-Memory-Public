---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
description: Create a structured execution plan document for multi-phase projects
argument-hint: <goal or spec description>
---

# Plan Create

Create a structured execution plan document that `plan-execute` can run. The plan
captures major tasks, sub-tasks, dependencies, verification commands, and carry-forward
rules in a single Markdown file.

## Why this exists

Large projects fail when the plan lives only in the agent's context window. A durable
plan document solves this: it survives session boundaries, tracks progress via git
commits, and gives subagents the full picture when they're spawned for a major task.
This skill produces that document.

## Workflow

### Phase 0: Open the Plan Gate

Before doing anything else, mark the project plan-gate so the
`PreToolUse` hook (`.claude/hooks/plan_gate.py`, if installed) blocks
implementation tools (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`) for
the duration of planning. This guarantees no code changes happen until
Codex has adversarially reviewed the plan in Phase 4.5. If the project
has not installed the hook, still write the gate file — it remains the
single source of truth that the plan is in draft state, and any future
plan-execute invocation keys off it.

Write `.claude/data/plan-gate.json` (create the directory if missing):

```json
{
  "stage": "plan-creating",
  "plan_path": "<intended plan document path; use \"<pending>\" if not yet chosen>",
  "session_id": "<current Claude session id if available, else \"<unknown>\">",
  "started_at": "<ISO 8601 timestamp now>"
}
```

Once the plan path is decided in Phase 4, update the `plan_path` field.
This file is gitignored.

### Phase 1: Gather Context

1. **Read `$ARGUMENTS`** — the user may have provided a goal, a spec file path, or a
   description. If `$ARGUMENTS` references a file, read it.
2. **Explore the codebase** — use Grep/Glob/Read to understand the project structure,
   existing tests, build system, and CI configuration. This informs task breakdown and
   verification command selection. The project's language and tooling are discovered
   here — do not assume any particular stack.
3. **Check for existing plans** — search for `docs/*_plan.md` or similar. If a plan
   already exists, ask the user whether to extend it or start fresh.
   - **Extending**: see "Extending an Existing Plan" below.
   - **Fresh**: create a new plan document from scratch.

### Phase 2: Interview

Ask the user to clarify anything that can't be inferred from the codebase. Keep the
interview concise — group related questions into a single message. Key questions:

1. **Goal** — What is the end state? What does "done" look like?
2. **Scope boundaries** — What is explicitly out of scope?
3. **Constraints** — Deadlines, API compatibility requirements, performance budgets,
   dependencies on external systems.
4. **Verification commands** — Does the user want to specify L1/L2/L3 verification
   commands? If not, propose them based on what you found in the codebase:
   - L1 (every sub-task): the project's **fast unit-test runner** — whatever command
     completes in seconds and gates individual commits
   - L2 (accuracy/integration-affecting sub-tasks): a **narrower integration or
     benchmark subset** that takes a minute or two
   - L3 (major task boundary): the **full test suite and/or full benchmark sweep** —
     the command that declares the codebase healthy
5. **Carry-forward rules** — Any invariants specific to this plan that every sub-task
   must respect? (e.g., "read reference source before porting", "no changes to public
   API signatures", "threshold X must not be relaxed")

**Discovering verification commands** (when the user doesn't specify them):

Inspect config and CI files to propose sensible defaults. Examples across common
ecosystems — use whichever apply to the project in front of you:

- **Python**: `pytest`, `tox`, `nox`, `hatch run test`; config in `pyproject.toml`,
  `pytest.ini`, `setup.cfg`
- **Node / TypeScript**: `npm test`, `pnpm test`, `yarn test`, `vitest`, `jest`;
  config in `package.json` `scripts`
- **Go**: `go test ./...`; config implicit
- **Rust**: `cargo test`, `cargo nextest run`; config in `Cargo.toml`
- **Java / Kotlin**: `mvn test`, `gradle test`; config in `pom.xml` / `build.gradle`
- **Generic**: a `Makefile` target, a `justfile` recipe, a shell script under
  `scripts/`, or a CI job defined in `.github/workflows/` / `.gitlab-ci.yml`

If none of the above apply, ask the user directly what command they use to run tests
and benchmarks. Propose defaults and confirm before writing them into the plan.

### Phase 3: Task Breakdown

Break the goal into major tasks. For each major task:

1. **Identify the deliverable** — what concrete change does this task produce?
2. **Estimate difficulty** — Low / Medium / High based on scope and uncertainty
3. **Map dependencies** — which other tasks must complete first?
4. **List relevant files** — which files/modules are the likely starting points?
   This is informational guidance for the subagent, not a hard restriction.
5. **Write context** — past attempts, known pitfalls, reference materials.
   Keep this concise — subagents have limited context windows. If the context
   is extensive, write it in a separate reference file and point to it.
6. **Define sub-tasks** — ordered steps within the major task, each = 1 commit.
   Aim for **7 or fewer sub-tasks per major task**. If more are needed, consider
   splitting into two major tasks — large sub-task counts risk exhausting the
   subagent's context window.
   - **Description length**: 10–60 characters. Long enough to be unambiguous
     ("Implement curvature-adaptive knot placement"), short enough to fit in a
     table row and be reliably matched by the Edit tool.
7. **Mark L2 applicability** — for each sub-task, decide whether it needs L2
   verification (accuracy-affecting, integration-affecting, etc.) and mark it
   in the sub-task table's L2 column (`yes` or leave blank)
8. **Define verification gate** — specific pass/fail criteria for task completion

Ordering principles:
- Independent tasks before dependent ones
- Lower-risk tasks before higher-risk ones (build confidence early)
- Foundation/infrastructure before features that depend on it

### Phase 4: Draft the Plan Document

Write the plan using the format below. Save to the path the user specifies, or
default to `docs/<project-name>_plan.md`. Update `plan_path` in
`.claude/data/plan-gate.json` to the final path now that it is decided.

### Phase 4.5: Codex Adversarial Plan Review (MANDATORY when Codex is available)

After saving the plan document, run an adversarial review against it through
the Codex plugin. **This phase is mandatory when Codex is installed** — do
not advance to Phase 5 without it. The plan-gate hook (if installed) is
still in `plan-creating` mode, so any attempt to edit project source files
in this phase will be blocked.

**Precondition — Codex availability check**

Before invoking any `/codex:*` command, verify Codex is installed:

1. **CLI**: `command -v codex` returns a path (e.g. `/usr/bin/codex`).
2. **Plugin**: the `openai-codex/codex` plugin is installed — either
   `~/.claude/plugins/cache/openai-codex/codex/` exists, or
   `~/.claude/plugins/installed_plugins.json` contains a
   `codex@openai-codex` entry, or the `/codex:adversarial-review` skill
   appears in the available skills list for this session.

If either check fails, **skip this phase** and emit a one-line notice to
the user:

> Codex CLI or plugin not installed — skipping adversarial plan review.
> Install the `codex` CLI and the `codex@openai-codex` plugin to enable it.

Then proceed directly to Phase 5. The plan-gate will still transition to
`plan-approved` after user sign-off — execution is not blocked by a missing
review step. If only one of the two components is present, still skip and
list which piece is missing so the user can fix the installation.

Steps (run only when the precondition above passes):

1. Confirm the plan file exists on disk (Phase 4 wrote it).
2. **Commit + push the plan document before invoking the review.**
   Codex's review sandbox blocks local `bash`/`git diff`, so the only
   diff source that works reliably is GitHub via the Codex GitHub MCP.
   Running `/codex:adversarial-review --scope working-tree` against an
   uncommitted or unpushed file frequently returns "no actionable
   defects" because Codex cannot fetch the file contents. Commit with
   a descriptive WIP message and push before continuing — ask the user
   for explicit push approval first if the project git rules prohibit
   unprompted pushes. Typical sequence:

   ```bash
   git add <plan-path>
   git commit -m "docs(plan): draft <plan-name> for adversarial review"
   git push origin <current-branch>
   ```

   Capture the commit SHA (`git rev-parse HEAD~1`, or whichever was the
   previous HEAD) as `<pre-plan-sha>` — it will be the review base.

3. Invoke (only after push succeeds), using branch-diff scope so the
   pushed commit is visible to GitHub-backed diff tools:

   ```
   /codex:adversarial-review --wait --base <pre-plan-sha> Focus on the plan
   document at <plan-path>. Challenge the proposed approach for: logical
   flaws, missing edge cases, invalid or unstated assumptions, simpler
   alternatives, and hidden risks (correctness, regression, security,
   migration). This is a planning artefact — do not propose code edits.
   ```

   Use `--wait` so the review blocks the conversation; the plan must be
   approved before any execution. Codex's default model is governed by
   `~/.codex/config.toml`, so no per-call model flag is typically needed.

4. Read Codex's verbatim output and present it to the user with brief
   notes on which findings you accept, dispute, or want to flag as open
   questions. Do not silently accept everything Codex says — its job is
   to attack the plan, not to design it.
5. Apply the accepted feedback to the plan document (revise tasks, add
   risks, refine the verification protocol, split High-difficulty tasks,
   etc.).
6. If revisions are material, commit + push the revision (same push
   approval flow as step 2) and re-run step 3 against the updated plan
   using the original `<pre-plan-sha>` as the base so the review sees the
   full accumulated diff. Stop iterating once Codex's remaining feedback
   is informational only or the user explicitly accepts the residual
   risks.

### Phase 5: Review

Present the plan to the user. Specifically call out:
- Total task count and estimated dependency chain length
- Any tasks where difficulty is High — ask if the user wants them split further
- Any tasks with 8+ sub-tasks — recommend splitting
- Any assumptions you made about verification commands or scope
- L2 markings on sub-tasks — ask if the user agrees with which sub-tasks need L2

Incorporate feedback and finalize.

After the user signs off on the final plan, mark the gate as approved so
that `plan-execute` may proceed in the same or a future session. Update
`.claude/data/plan-gate.json`:

```json
{
  "stage": "plan-approved",
  "plan_path": "<final plan path>",
  "session_id": "<same as Phase 0>",
  "started_at": "<original timestamp>",
  "approved_at": "<ISO 8601 timestamp now>"
}
```

---

## Extending an Existing Plan

When extending a plan that already has completed tasks:

1. **Never reopen a DONE task.** Completed tasks and their commits are final.
2. **New work that overlaps a DONE task's scope** → create a follow-up task:
   `T9: Follow-up — <original task name>`. Set its dependency to include the
   original task (already satisfied). This ensures the follow-up appears as
   NOT STARTED and won't be missed by plan-execute.
3. **New work that fits a NOT STARTED task** → append sub-tasks to that task.
4. **Truly new scope** → create a new major task at the end.

Example follow-up task:
```markdown
## T9: Follow-up — T3 amendments

**Status:** NOT STARTED
**Difficulty:** Low
**Dependencies:** T3
**Files:** `src/module.<ext>`
**Goal:** Address gaps discovered after T3 was completed.

### Context
T3 shipped in session X but subsequent work revealed that <description>.
This follow-up adds the missing handling.
```

---

## Plan Document Format

The plan document must follow this exact structure so that `plan-execute` can parse it.

````markdown
# <Plan Name>

Created: YYYY-MM-DD
Branch: `<branch-name>`
Last updated: YYYY-MM-DD (<update description>)

## Current State

- **Tests:** X passed, Y failed
- <other relevant metrics for this project — coverage, benchmark pass rate, lint
  warnings, build time, whatever the team tracks>

## Configuration

### Verification Protocol

| Level | Command | When |
|-------|---------|------|
| L1 | `<fast unit-test command>`               | Every sub-task |
| L2 | `<integration / benchmark subset>`       | Sub-tasks marked L2 |
| L3 | `<full test suite and/or full sweep>`    | Major task boundary (all sub-tasks done) |

### Carry-Forward Rules

Rules specific to this plan. General project rules (coding conventions, git workflow,
etc.) are inherited from CLAUDE.md and `.claude/rules/` — do not duplicate them here.

- <plan-specific rule 1>
- <plan-specific rule 2>

---

## T1: <Task Name>

**Status:** NOT STARTED
**Difficulty:** Low | Medium | High
**Dependencies:** None | T1, T2
**Files:** `path/to/file.<ext>`, `path/to/other.<ext>`
**Goal:** <One-line description of what this achieves>

### Context

<Why this task exists, past attempts, reference materials, known pitfalls.
Keep concise — if extensive, put details in a reference file and link to it.>

### Sub-tasks

| # | Description | L2 | Status | Commit | Notes |
|---|-------------|-----|--------|--------|-------|
| 1.1 | <step description> | yes | | | |
| 1.2 | <step description> | | | | |

### Verification Gate

- <Specific measurable criterion>
- <Another criterion>

---

(repeat for T2, T3, ... )

---

## Summary

| Task | Description | Status | Difficulty | Dependencies |
|------|------------|--------|------------|-------------|
| T1 | <name> | NOT STARTED | Low | None |
| T2 | <name> | NOT STARTED | Medium | T1 |
````

### Format Rules

- Major tasks are numbered `T1`, `T2`, `T3`, ... (no upper limit)
- Sub-task numbering: `<major>.<sub>` (e.g., 1.1, 1.2, 2.1)
- **Sub-task Status:** *(empty)* = not started, `DONE`, `SKIPPED` (verification failed,
  deferred), `REVERTED` (git-reverted due to L3 regression)
- **Major Task Status:**
  - `NOT STARTED` — no work has begun
  - `IN PROGRESS` — subagent is working on this task
  - `DONE` — all sub-tasks complete, verification gate passed
  - `DEFERRED` — all sub-tasks reverted; will re-attempt after a specified dependency.
    Must include a note: "Deferred until after T5" with reason.
  - `SKIPPED` — task determined to be unnecessary or fundamentally wrong.
    Must include a note explaining why.
- The L2 column indicates whether that sub-task requires L2 verification (`yes` or blank)
- The Summary table at the bottom must mirror all tasks for quick reference
- Horizontal rules (`---`) separate each major task section
- The plan document contains only **data** (tasks, configuration, metrics) — not
  execution instructions. How to run the plan lives in the `plan-execute` skill.
- **Files** is informational guidance (where to start looking), not a hard restriction

## Important Notes

- Do NOT start implementing during plan creation — this skill only produces the plan
- The plan document is a living artifact — `plan-execute` updates it as work progresses
- Carry-Forward Rules are for **plan-specific** invariants only. Do not duplicate
  rules already present in CLAUDE.md or `.claude/rules/` — subagents inherit those
  automatically
- Aim for ≤7 sub-tasks per major task to stay within subagent context limits
- Do NOT commit or push unless the user explicitly requests it
