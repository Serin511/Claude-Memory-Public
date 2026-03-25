---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent
description: Run an iterative measure-diagnose-fix-verify cycle until a target metric is met
argument-hint: [target description (optional)]
---

# Fix Loop

Iterative improvement framework: measure → classify → fix → verify → repeat until
the target is reached.

## Why this exists

Many engineering tasks share a pattern: a measurable metric (failure count, PASS rate,
execution time, accuracy) needs to reach a target. Each fix must be verified individually
to prevent regressions, and progress must be tracked cumulatively. This command provides
the generic cycle so domain-specific skills can focus on *what* to fix rather than
*how* to structure the iteration.

## Prerequisites

The project's CLAUDE.md must have a `## Fix Loop` section defining:

1. **Baseline measurement** — commands to measure the current state of target metric(s)
2. **Per-cycle verification** — commands to verify a fix didn't regress anything
3. **Regression gate** — criteria that must hold after every fix
4. **Termination condition** — when to stop iterating

If this section is missing, ask the user to define it before starting.

## Workflow

Each cycle executes **Phase 1 → 2 → 3 → (repeat 3) → 4**. After Phase 4, loop back
to Phase 1 to re-baseline — this catches regressions and keeps bottleneck rankings
accurate as the landscape shifts.

### Phase 1: Establish Baseline

Run the **baseline measurement** commands from the project's CLAUDE.md `## Fix Loop`
section. Use `run_in_background=true` for long-running commands.

Record:
- All metric values (the numbers being improved)
- Regression gate baseline (the floor that must not drop)

### Phase 2: Classify Issues

Analyze measurements to identify what's causing the gap between current state and target.

1. Group by **root cause**, not by individual symptom
2. Prioritize by **impact** (issue count x severity)
3. Create a TodoWrite checklist: one item per root-cause cluster, ordered by impact

If a domain-specific skill is active (e.g., `benchmark-fix`, `mesh-accuracy`,
`perf-optimize`), follow its classification guidance for this phase.

### Phase 3: Fix Cycle

For each root-cause cluster (highest-impact first):

#### Step 1: Reproduce

Pick 2-3 representative cases. Run them individually with targeted commands to
confirm the issue and understand its exact manifestation.

#### Step 2: Diagnose

Trace to root cause in the code. Read the relevant source — understand *why*
before changing anything. Use domain-specific diagnosis techniques if available.

#### Step 3: Fix

Write the minimal change that addresses the root cause:
- Fix root cause, not symptom
- Don't refactor surrounding code
- Preserve existing edge-case handling
- Keep public APIs identical
- Respect project conventions (constants, utilities, naming)

#### Step 4: Verify & Regression Gate

Run **per-cycle verification** commands from CLAUDE.md `## Fix Loop`.
Check every **regression gate criterion**.

- **Gate passes** → proceed to Step 5
- **Gate fails** →
  1. Revert immediately
  2. Diagnose which criterion failed and why
  3. Write a revised fix that avoids the regression
  4. Re-run verification
  5. If unresolvable after reasonable effort, skip this cluster and log why

#### Step 5: Re-measure

Run **baseline measurement** commands again to quantify improvement.
Record new metric values.

#### Step 6: Log

Record:
- Root-cause cluster fixed (what + how many cases)
- Files changed
- Root cause (one sentence)
- Metrics: before → after

Check **termination condition**:
- Met → proceed to Phase 4
- Not met → next cluster (back to Step 1)

### Phase 4: Summary Report

```
## Fix Loop — Summary

**Target:** {metric and goal}
**Starting:** {baseline}
**Final:** {current}

| Cycle | Root Cause | Fix | Files | Before | After |
|-------|-----------|-----|-------|--------|-------|
| 1     | ...       | ... | ...   | ...    | ...   |

**Target reached:** YES / NO
**Remaining:** {count} — {description}
```

## Integration with /hypothesis-lab

When multiple fix strategies are viable for a single root cause, use `/hypothesis-lab`
to test them in parallel worktree subagents:

1. Formulate each approach as an action item
2. Run parallel experiments via /hypothesis-lab
3. Merge the best result
4. Continue fix-loop from Step 4 (verify)

This is optional — use when diagnosis is clear but the best approach is uncertain.

## Important Notes

- One fix per cycle — don't bundle unrelated changes
- Verify before measuring — a fix that breaks verification is invalid
- The regression gate is non-negotiable
- Re-measure after every fix to keep baselines accurate
- Do NOT commit or push unless the user explicitly requests it
