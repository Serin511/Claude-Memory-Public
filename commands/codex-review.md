---
allowed-tools: Bash(codex:*), Bash(git diff:*), Bash(git log:*), Bash(git rev-parse:*), Bash(git ls-files:*), Bash(mktemp:*), Bash(rm:*), Write, Read
description: Agent-invocable Codex review (wraps `codex exec` via Bash to bypass the /codex:review disable-model-invocation restriction). Supports code/document/mixed modes and committed/uncommitted scopes.
argument-hint: <base-sha | --uncommitted> [code|document|mixed]
---

# Codex Implementation Review (agent-invocable wrapper)

This command replaces `/codex:review` for `/plan-execute` Phase 6. The upstream plugin command ships with `disable-model-invocation: true`, which prevents agents from auto-invoking it. This project-local wrapper avoids that restriction by calling the `codex` CLI directly via Bash — the diff is captured **outside** Codex's sandbox, so Codex's own `bash`/`git diff` block does not apply.

`$ARGUMENTS` takes the form `<scope> [mode]`:

- **`<scope>`** (required):
  - A base commit SHA → review the span `<sha>..HEAD` (the typical case for committed code/document tasks).
  - The literal `--uncommitted` → review the working tree against `HEAD`, intended for document-only tasks where deliverables haven't been committed yet (Phase 6 has a routing branch for this).
- **`[mode]`** (optional, default `code`):
  - `code` — adversarial code review (correctness bugs, test gaps, over-engineering, regression risk).
  - `document` — document content review (factual accuracy of cited paths/line numbers, cross-reference correctness, internal consistency, contradictions with other rules/plans).
  - `mixed` — both (for tasks that produced both code and documents).

## Steps

1. **Parse arguments.** Set `SCOPE` to the first whitespace-separated token of `$ARGUMENTS` and `MODE` to the second (default `code`). Validate `MODE` is one of `code`, `document`, `mixed`; abort with a clear error if not.

2. **Resolve scope and capture diff/log into temp files.** Use `mktemp -d` for a portable scratch directory (`mktemp --suffix=…` is GNU-only):

   ```bash
   TMP_DIR=$(mktemp -d)
   DIFF_FILE="$TMP_DIR/diff.patch"
   LOG_FILE="$TMP_DIR/commits.log"

   if [ "$SCOPE" = "--uncommitted" ]; then
     # Working tree + index + untracked vs HEAD — for review of
     # uncommitted deliverables.
     # `git diff HEAD` captures BOTH unstaged and staged changes to
     # tracked files (so a deliverable that has been `git add`-ed but
     # not yet committed is in scope). Plain `git diff` would only
     # show unstaged hunks.
     # Untracked NEW files (not yet `git add`-ed at all) are invisible
     # to `git diff HEAD`, so render each one as a new-file diff via
     # `git diff --no-index /dev/null <f>` and append to the diff file.
     # `--no-index` returns 1 on differences (the normal case), so
     # swallow the exit code.
     git diff HEAD > "$DIFF_FILE"
     git ls-files --others --exclude-standard | while IFS= read -r f; do
       [ -z "$f" ] && continue
       git diff --no-index -- /dev/null "$f" >> "$DIFF_FILE" 2>/dev/null || true
     done
     printf "(uncommitted changes — working tree + staged + untracked vs HEAD; no commit log)\n" > "$LOG_FILE"
   else
     git rev-parse --verify "$SCOPE" || {
       echo "Bad base SHA: $SCOPE" >&2
       rm -rf "$TMP_DIR"
       exit 1
     }
     git diff "$SCOPE"..HEAD > "$DIFF_FILE"
     git log --oneline "$SCOPE"..HEAD > "$LOG_FILE"
   fi
   ```

   If the diff file is empty (`[ ! -s "$DIFF_FILE" ]`), stop and report the problem — there is nothing to review. The caller should re-invoke with the correct scope or skip Phase 6 for this task.

3. **Compose the review prompt.** Use a here-doc with unquoted terminator so `$(cat …)` expands before the prompt reaches Codex. The prompt body branches on `MODE`:

   ```bash
   PROMPT_FILE="$TMP_DIR/prompt.md"
   ```

   **For `code` mode** (default):

   ```bash
   cat > "$PROMPT_FILE" <<EOF
   You are reviewing a Claude-authored implementation that just finalised a major task in a multi-phase plan. Your job is adversarial: surface correctness bugs, test gaps, over-engineering, simpler alternatives, and regression risks.

   Classify every finding with a severity tag:
   - [critical] ship-blocker
   - [high]     must-fix before the next task
   - [medium]   should-fix this cycle
   - [low]      nice-to-have
   - [info]     observation only

   Do NOT propose implementation edits — this is a review, not a rewrite.

   === Commits ===
   $(cat "$LOG_FILE")

   === Diff ===
   $(cat "$DIFF_FILE")
   EOF
   ```

   **For `document` mode**:

   ```bash
   cat > "$PROMPT_FILE" <<EOF
   You are reviewing a Claude-authored document deliverable that just finalised a major task in a multi-phase plan. Focus on factual accuracy, internal consistency, and cross-reference correctness — NOT on writing style.

   Apply these criteria (verbatim from the canonical list in /plan-execute.md — keep word-for-word identical across all four review-path copies):
   - All cited file paths and line numbers are verifiable via \`grep\` against the actual codebase.
   - No claims about code behaviour that contradict the actual implementation.
   - Internal consistency: no contradictions between sections within the same document, or between this deliverable and existing \`.claude/rules/\` content / other plan documents.
   - Policy vs runtime distinction (when applicable): decided policy is not presented as current runtime behaviour.
   - Migration roadmap completeness: all identified NEEDS_MIGRATION items are covered by sub-tickets with correct dependency ordering.
   - Cross-reference accuracy: ticket IDs, rule IDs, and external references are correct.

   Classify every finding with a severity tag:
   - [critical] ship-blocker (factual error that misleads the reader)
   - [high]     must-fix before the next task (incorrect cross-reference, broken citation)
   - [medium]   should-fix this cycle (consistency drift, mild inaccuracy)
   - [low]      nice-to-have
   - [info]     observation only

   Do NOT propose rewrites — flag issues only.

   === Commits ===
   $(cat "$LOG_FILE")

   === Diff ===
   $(cat "$DIFF_FILE")
   EOF
   ```

   **For `mixed` mode**:

   ```bash
   cat > "$PROMPT_FILE" <<EOF
   You are reviewing a Claude-authored deliverable that includes BOTH code changes and document updates, finalising a major task in a multi-phase plan. Apply both code-review and document-review criteria — judge each hunk by what it is.

   For code hunks, surface: correctness bugs, test gaps, over-engineering, simpler alternatives, regression risks.

   For document hunks, apply the canonical document-deliverable criteria (verbatim from /plan-execute.md — keep word-for-word identical across all four review-path copies):
   - All cited file paths and line numbers are verifiable via \`grep\` against the actual codebase.
   - No claims about code behaviour that contradict the actual implementation.
   - Internal consistency: no contradictions between sections within the same document, or between this deliverable and existing \`.claude/rules/\` content / other plan documents.
   - Policy vs runtime distinction (when applicable): decided policy is not presented as current runtime behaviour.
   - Migration roadmap completeness: all identified NEEDS_MIGRATION items are covered by sub-tickets with correct dependency ordering.
   - Cross-reference accuracy: ticket IDs, rule IDs, and external references are correct.

   Classify every finding with a severity tag:
   - [critical] ship-blocker
   - [high]     must-fix before the next task
   - [medium]   should-fix this cycle
   - [low]      nice-to-have
   - [info]     observation only

   Do NOT propose edits or rewrites — flag issues only.

   === Commits ===
   $(cat "$LOG_FILE")

   === Diff ===
   $(cat "$DIFF_FILE")
   EOF
   ```

4. **Invoke Codex.** Use `read-only` sandbox (review only, no edits) and stream the prompt via stdin:

   ```bash
   codex exec --sandbox read-only < "$PROMPT_FILE"
   ```

   If `codex` is not on `PATH`, emit the standard skip notice and exit gracefully:

   > codex CLI not installed — skipping implementation review. Install the `codex` CLI (e.g. `npm i -g @openai/codex`) to enable it. The caller should fall back to a Claude subagent review (see `/plan-execute` Phase 6 precondition).

5. **Present Codex's verbatim output to the user.**

6. **Classify each finding** per the `/plan-execute` Phase 6 contract:
   - **Bug** or **test gap** (code) → propose a follow-up sub-task.
   - **Factual error** or **broken cross-reference** (document) → propose a follow-up sub-task, or fix immediately if trivial.
   - **Consistency issue** (document) → flag for user decision.
   - **Over-engineering** / **simpler alternative** → surface for user decision.
   - **Informational** → note briefly, no action.

   Do **not** auto-apply Codex suggestions. The user owns every decision.

7. **Clean up temp files:**

   ```bash
   rm -rf "$TMP_DIR"
   ```
