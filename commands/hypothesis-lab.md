---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
description: Orchestrate parallel hypothesis-driven experimentation with isolated git worktrees
argument-hint: [goal description]
---

# Hypothesis Lab

Systematic parallel experimentation framework: derive action items from a goal, test
each in an isolated git worktree, and merge validated results with full regression gates.

## Why this exists

Complex engineering problems often have multiple potential solutions. Testing them
sequentially is slow; testing them in the same workspace creates interference. This command
isolates each experiment in its own git worktree, runs independent experiments in parallel,
and ensures no merged change degrades the codebase through a strict sequential merge queue
with full verification.

## Prerequisites

The project's CLAUDE.md must have a `## Hypothesis Lab` section defining:

1. **Targeted verification** — fast, scoped checks for individual action items (specific
   test files, individual benchmark samples). Subagents run only these.
2. **Full verification pipeline** — ordered list of commands covering the entire codebase.
   Run during merge verification and final validation.

If this section is missing, ask the user to define these commands before proceeding.

## Phase 0: Goal Analysis & Planning

The user provides a work goal. Your tasks:

1. **Analyze** the goal — understand what changes are needed and why
2. **Derive action items** — each is a concrete, independently testable hypothesis
3. **Map dependencies** — build a DAG of which items depend on which
4. **Batch by dependency level** — topological sort into parallel batches:
   - Batch 0: no dependencies (all run in parallel)
   - Batch 1: depends on batch 0 (run after batch 0 merges complete)
   - etc.
5. **Identify targeted tests** per item — which specific tests/benchmarks verify it
6. **Present the plan** and wait for user confirmation:

```
| Batch | Item | Description | Depends On | Targeted Verification |
|-------|------|-------------|------------|-----------------------|
| 0     | A1   | ...         | —          | pytest tests/x.py     |
| 0     | A2   | ...         | —          | benchmark sample Y    |
| 1     | A3   | ...         | A1         | pytest tests/z.py     |
```

7. **Partition file ownership** — assign each file to exactly one agent. No two agents
   may edit the same file. Include the partition table in the plan:

```
| Agent | Owned Files         | Read-Only             |
|-------|---------------------|-----------------------|
| A1    | parser.py           | config.py, utils.py   |
| A2    | optimizer.py        | parser.py             |
```

Do not proceed until the user approves the plan.

## Phase 1: Parallel Experimentation

**Before launching any worktree agents:**
- Commit (or stash) all pending changes in the main working tree. Uncommitted changes
  will be silently lost when worktrees are cleaned up.
- Verify the file ownership partition — no two agents should edit the same file.

For each batch, spawn worktree subagents for all items **in a single message** (parallel).
If there's only one item in the batch, that's fine — use one subagent.

Each subagent MUST use `isolation: "worktree"`.

### Subagent prompt template

```
You are working in an isolated git worktree to experiment with one hypothesis.

## Action Item
{description}

## Goal Context
{overall_goal — so you understand the bigger picture}

## File Ownership
You may ONLY edit these files: {owned_files}
Do NOT modify any other files — other agents own them.

## Instructions
1. Implement the change described above.
2. ALL git and file operations must target your worktree directory only.
   NEVER run `cd` to the main project directory or execute git commands there.
3. Run ONLY these targeted verification commands (NOT the full suite):
   {targeted_verification_commands}
4. You MUST commit your changes before finishing — uncommitted worktree changes
   are lost on cleanup. Use a descriptive commit message.
5. Report your results:
   - What you changed (files + one-line summary each)
   - Test/benchmark results (pass/fail, key metrics)
   - Confidence: HIGH / MEDIUM / LOW with reasoning

If tests fail, attempt up to 3 fix iterations. If still failing after 3 attempts,
report FAILURE with what you tried and why it didn't work.

CRITICAL: Never run destructive git commands (checkout --, reset, stash, clean)
on the main working tree. Operate exclusively within your worktree.
```

### Collect results

When all subagents in the batch complete:
- **SUCCESS**: record the worktree branch name, changes summary, and confidence
- **FAILURE**: record the analysis for the final report

If every item in a batch fails, pause and ask the user how to proceed.

## Phase 2: Sequential Merge Queue

After a batch's experiments finish, merge successful results **one at a time**.

### Build the queue

Order successful subagents by: highest confidence first, then broadest impact.
Discard items that reported FAILURE or negligible improvement.

### Process each entry (strictly sequential)

**CRITICAL: Do not start processing the next entry until the current entry's
entire merge cycle — including ALL verification command runs — is fully complete.**

#### Step 1: Evaluate

Review the subagent report. Discard if:
- Improvement is marginal or uncertain (ask user if unclear)
- Conflicts with an already-merged item from this batch

#### Step 2: Apply changes

**Always use `git merge --squash` — never manually copy files with `cp`.** Manual
copying bypasses git's conflict detection and leaves changes outside version control.

```bash
git merge <worktree-branch> --squash --no-commit
```

If merge conflicts arise from previously merged items, attempt resolution.
If conflicts are too complex to resolve cleanly, discard this entry.

**Verify the merge applied the expected files:**
```bash
git diff --cached --stat
```

#### Step 3: Full verification

Run every command in the project's `## Hypothesis Lab` → **Full verification
pipeline**, in the specified order. Use `run_in_background=true` for long-running
commands. **Wait for each command to complete before running the next.**

#### Step 4: Regression decision

**No regression →** Commit the merge and proceed to the next queue entry:

```bash
git add -A && git commit -m "$(cat <<'EOF'
{type}: {concise summary of the change} (hypothesis-lab merge)

{optional body — what changed and why, 1-3 lines}
EOF
)"
```

Where `{type}` follows conventional commits: `fix`, `feat`, `perf`, `refactor`, etc.

Example: `fix: resolve edge case in input validation (hypothesis-lab merge)`

**Regression detected →**

1. Revert:
   ```bash
   git reset HEAD -- . && git checkout -- . && git clean -fd
   ```

2. Resume the original subagent (using its agent ID) with regression context:
   ```
   Your changes caused a regression when merged into the main branch.

   ## Regression Details
   {which commands failed, which tests/metrics regressed, before→after values}

   ## Your Original Changes
   {summary of what you changed}

   ## Task
   Fix the regression while preserving your intended improvement.
   Run BOTH your original targeted verification AND the regression-causing
   tests/benchmarks to confirm the fix addresses both:
   - Original: {original_targeted_verification_commands}
   - Regression: {commands that revealed the regression, e.g. specific failing
     test names, specific benchmark samples that regressed}
   Then commit.
   ```

3. On subagent completion:
   - Fixed → retry from Step 2
   - Declared unsolvable → discard, log reason, move to next entry

4. Max **5 retry cycles** per entry. After 5 failures, discard and log.

### Batch complete

After all entries are processed, log:

```
## Batch N Results
| # | Action Item | Status    | Attempts | Notes                |
|---|-------------|-----------|----------|----------------------|
| 1 | A1          | MERGED    | 1        |                      |
| 2 | A2          | DISCARDED | 5        | Regression in test_X |
```

Clean up stale worktrees:
```bash
git worktree prune
```

### Next batch

If there are more dependency-ordered batches, return to **Phase 1** for the next
batch. Subagents now start from the updated branch (with prior merges applied).

## Phase 3: Final Validation

After ALL batches are processed:

1. Run the **full verification pipeline** one final time
2. Compare results against the starting state (before any experiments)
3. Present the final report:

```
## Hypothesis Lab — Final Report

### Goal
{original_goal}

### Results
- Planned: N action items
- Merged: M
- Discarded: K

### Verification (Final)
{full pipeline results — test counts, benchmark metrics, accuracy}

### Changes Merged
| Item | Files Changed | Summary |
|------|---------------|---------|
| A1   | foo.py, bar.py | ... |
| A3   | baz.py        | ... |

### Discarded Items
| Item | Reason |
|------|--------|
| A2   | Regression in test_X after 5 retry cycles |

### Remaining Issues
{anything unresolved or needing follow-up}
```

## Important Notes

- Every subagent MUST use `isolation: "worktree"` — never experiment in the main worktree
- Only ONE merge at a time — wait for full verification before starting the next
- Subagents run only targeted verification; full checks happen during merge
- Subagents MUST commit in their worktrees — uncommitted changes are lost on cleanup
- This workflow creates intermediate commits during Phase 2 as part of the merge process —
  invoking this command implies consent for these workflow commits
- If the CLAUDE.md `## Hypothesis Lab` section is missing, ask the user before starting

### Merge Coordination Safety

These rules prevent the most common merge tangling failures observed in practice:

- **Commit main tree first.** Uncommitted changes vanish when worktrees are cleaned up.
- **File ownership is mandatory.** Two agents editing the same file causes silent overwrites
  and merge conflicts. Partition files before launching any batch.
- **Never `cp` files from worktrees.** Always use `git merge --squash`. Manual copies
  bypass conflict detection and leave changes untracked.
- **Kill zombie agents.** A worktree agent running >30 min without progress can drift to
  the main tree and run destructive git commands (`checkout --`, `reset`, `stash`) that
  wipe other agents' work. Stop it immediately.
- **Verify after each merge.** Run `git diff --stat` after every worktree merge to confirm
  the expected files were modified. If changes are missing, re-apply before continuing.
