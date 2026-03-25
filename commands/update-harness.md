---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, Skill(insights)
description: Analyze recent session logs to identify failure patterns and anti-patterns, then propose improvements to CLAUDE.md and .claude/rules
argument-hint: [--range all|current] [--sessions N] [--days N] [--review-code]
---

# Update Harness

Analyze Claude Code session history to surface failure patterns and anti-patterns,
then propose targeted improvements to agent configuration files.

The core idea: instead of manually noticing and fixing recurring agent misbehavior,
this command automates the feedback loop — collect evidence from real sessions, identify
what went wrong (and why), and translate findings into concrete rule/skill changes
that prevent recurrence.

## Arguments

Parse `$ARGUMENTS` for these flags:

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--range` | `current`, `all` | `current` | `current`: sessions for the working directory's project only. `all`: sessions across every project on this machine. |
| `--sessions` | integer | `10` | Number of recent sessions to analyze. |
| `--days` | integer | _(no limit)_ | Optionally restrict to sessions from the last N days. |
| `--review-code` | _(flag, no value)_ | off | Also review git diffs from the analysis period. Increases cost significantly — off by default. |

## Phase 1: Collect Data

### Step 1: Extract quantitative signals

Run the extraction script to get a structured summary of recent sessions.
The script may be at one of these paths — use whichever exists:

1. `.claude/scripts/parse_sessions.py` (project-level install via install.sh)
2. `~/.claude-sync/scripts/parse_sessions.py` (global sync install)

```bash
python <script-path> \
  --project-path "$(pwd)" \
  --max-sessions 10
```

Map the user's flags to script arguments:
- `--range all` → replace `--project-path "$(pwd)"` with `--all`
- `--sessions N` → pass `--max-sessions N`
- `--days N` → append `--days N` (omit if the user didn't specify a day limit)

Save the JSON output — it drives the rest of the analysis.

### Step 2: Deep-read flagged moments

The script output identifies specific moments worth investigating: tool failures,
user corrections, and retry clusters. For the **top 15 most informative moments**
(prioritize user corrections over tool failures, since corrections reveal
expectation gaps):

1. Open the session JSONL file indicated by `session_id`
2. Locate the entry by timestamp or line number
3. Read the surrounding context: **5 entries before** through **5 entries after**

This gives the qualitative "why" behind each quantitative signal. Record your
observations — you will need them in Phase 2.

### Step 3: Run /insights (recommended)

If running inside Claude Code, execute `/insights` to generate a broader usage
report, then read the analysis:

1. Check `~/.claude/usage-data/report.html` — if it exists and was generated within
   the last 24 hours, read it directly (skip re-running /insights)
2. Otherwise, recommend the user run `/insights` first
3. Also check `~/.claude/usage-data/facets/` for per-session structured analysis
   (JSON files) — these contain friction points and satisfaction assessments that
   complement the script output

Extract from the insights data:
- Identified friction points
- Workflow patterns that succeeded vs failed
- Any recurring themes

This step is additive. If /insights is unavailable or the user declines, continue
with Steps 1-2 alone.

### Step 4: Review code changes (only if `--review-code`)

Skip unless the user passed `--review-code`.

Determine the analysis period from the sessions analyzed in Step 1 (earliest session
timestamp to now), then:

```bash
git log --since="<earliest-session-date>" --format="%H %s" --no-merges
```

For each commit, review the diff (`git show <hash> --stat` first to gauge size,
then `git show <hash>` for the full diff). Look for:

- **Over-engineering**: abstractions, helpers, or config that nobody asked for
- **Scope creep**: changes outside the stated task
- **Convention violations**: naming, structure, or patterns that contradict CLAUDE.md
- **Unwanted additions**: docstrings, comments, type annotations added unprompted
- **Security concerns**: hardcoded secrets, injection vectors

Record specific examples with commit hashes and file paths — vague observations
are not actionable.

## Phase 2: Analyze Patterns

Synthesize all collected data into categorized findings. Each finding needs a
concrete example from the session data — patterns without evidence are speculation.

### Category 1: Failure Patterns

Recurring situations where the agent fails to accomplish the task:

| Pattern | What to look for |
|---------|-----------------|
| Tool misuse | Wrong tool for the job, repeated Edit failures (non-unique `old_string`), Bash when a dedicated tool exists |
| Instruction blindness | Ignoring rules in CLAUDE.md or .claude/rules (compare the rule text against what the agent actually did) |
| Hallucination | Referencing files, functions, or APIs that don't exist |
| Retry loops | 3+ attempts at the same failing approach without changing strategy |
| Context loss | Forgetting earlier instructions or conversation context |

### Category 2: Anti-Patterns

Behaviors that technically succeed but produce suboptimal results:

| Pattern | What to look for |
|---------|-----------------|
| Over-engineering | Unnecessary abstractions, features not requested, premature optimization |
| Scope creep | Modifying files or adding functionality beyond the request |
| Verbosity | Long explanations when a short answer sufficed |
| Assumption-making | Proceeding without asking when the task was ambiguous |
| Convention drift | Gradually deviating from established project patterns |

### Category 3: Efficiency Issues

Patterns that waste tokens, time, or user attention:

| Pattern | What to look for |
|---------|-----------------|
| Redundant reads | Reading the same file multiple times in one session |
| Sequential work | Not using subagents for independent tasks |
| Incomplete research | Jumping to implementation without reading enough context |
| Excessive confirmation | Asking permission for clearly authorized low-risk actions |

### Cross-referencing

Before finalizing findings, cross-reference against:
- Existing `.claude/rules/` — the pattern may already have a rule that's being ignored
  (enforcement problem, not a missing-rule problem)
- Existing CLAUDE.md sections — the guidance may exist but be buried or unclear
- Memory files in `.claude/projects/*/memory/` — past feedback may already cover this

This prevents proposing duplicate rules. If a rule already exists but is being
ignored, the proposal should be about strengthening or repositioning that rule,
not creating a new one.

## Phase 3: Propose Improvements

For each finding from Phase 2, draft a specific, actionable improvement proposal.

### Proposal format

Present each proposal in this structure:

```
### Proposal N: [Short Title]

**Finding**: [What was observed — cite specific session IDs and timestamps]
**Frequency**: [How often — e.g., "3 of 12 sessions", "every session"]
**Root cause**: [Why the agent behaves this way]

**Proposed fix**:
- **Target**: [CLAUDE.md § section / .claude/rules/filename.md / new skill / hook]
- **Action**: [add / modify / remove / replace]
- **Content**:
  [Exact text that would be written or changed]

**Trade-offs**: [Downsides, edge cases, or risks of this change]
```

### Choosing the right target

Improvements can target both **global** (`~/.claude/rules/`, `~/.claude/CLAUDE.md`)
and **project-level** (`<project>/CLAUDE.md`, `<project>/.claude/rules/`) files.
Pick the right scope and the lightest intervention:

1. **Global `~/.claude/rules/`** — always loaded in every project. Use for universal
   behavioral rules that apply everywhere (e.g., "ask before destructive actions").
2. **Project `CLAUDE.md`** — scoped to one project. Use for project-specific workflows,
   architecture context, or conventions.
3. **Project `.claude/rules/`** — scoped to one project, always loaded. Use for
   project-specific behavioral constraints.
4. **Global `~/.claude/CLAUDE.md`** — applies to all projects. Use sparingly — only
   for cross-project preferences that don't fit in rules files.
5. **New skill** — only when a multi-step workflow is needed. Don't create a skill
   for something a rule can handle.
6. **Hook** — only for enforcement when rules are consistently ignored. Hooks add
   complexity; use them as a last resort.

When `--range all` is used and a pattern appears across multiple projects, prefer
global targets. When it appears only in the current project, prefer project-level.

### Writing effective rules

- Explain **why**, not just **what** — the agent follows reasoning better than commands.
  "Prefer Edit over sed because Edit shows diffs in the review UI" is better than
  "NEVER use sed."
- Keep rules concise — a 3-line rule is more likely to be followed than a 15-line one.
- Avoid overly restrictive rules that block legitimate use cases.
- One rule per concern — don't bundle unrelated constraints.

### Handling ambiguity

If a finding could be addressed multiple ways, or if you're unsure whether a
behavioral pattern is intentional vs accidental, **ask the user explicitly**.
Present the options and let them decide. Do not guess.

### Present all proposals

After drafting, present every proposal at once (numbered) and ask:

```
위 개선안을 검토해주세요. 각 항목에 대해:
- ✅ 승인 (그대로 적용)
- ✏️ 수정 (변경사항을 알려주세요)
- ❌ 거부 (적용하지 않음)

모호한 부분이나 질문이 있으시면 말씀해주세요.
```

**Do NOT proceed to Phase 4 until the user has reviewed every proposal.**

## Phase 4: Apply Approved Changes

Apply only proposals the user approved (✅) or modified (✏️).

For each:
1. Read the target file if it exists
2. Apply with Edit (modifications) or Write (new files)
3. Briefly confirm what was applied

After all changes, present a summary:

```
## Update Harness — Summary

**Sessions analyzed**: N (period: YYYY-MM-DD ~ YYYY-MM-DD)
**Patterns identified**: N
**Proposals**: A approved, R rejected, M modified

### Applied Changes
| # | Pattern | Target | Action |
|---|---------|--------|--------|
| 1 | ...     | ...    | ...    |

### Skipped
| # | Pattern | Reason |
|---|---------|--------|
| 2 | ...     | ...    |

### Recommendations for Next Run
[What to watch for in the next analysis cycle — e.g., verify that applied rules
actually reduce the target failure pattern]
```

## Important Notes

- This command reads session logs but never modifies or deletes them
- All proposed changes require explicit user approval before applying
- When uncertain about a pattern's significance, ask the user rather than guessing
- The `--review-code` flag substantially increases token usage — if the git log is
  large, warn the user before proceeding
- Do NOT commit or push changes unless the user explicitly requests it
- Prefer fewer, well-reasoned rules over many granular ones — rule bloat is itself
  an anti-pattern
