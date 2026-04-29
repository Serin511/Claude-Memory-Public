---
allowed-tools: Bash(codex:*), Bash(git rev-parse:*), Bash(mktemp:*), Bash(rm:*), Bash(test:*), Read, Write
description: Agent-invocable Codex adversarial plan review (wraps `codex exec` via Bash to bypass the /codex:adversarial-review disable-model-invocation restriction)
argument-hint: <plan-path>
---

# Codex Adversarial Plan Review (agent-invocable wrapper)

This command replaces `/codex:adversarial-review` for `/plan-create` Phase 4.5. The upstream plugin command ships with `disable-model-invocation: true`, so this project-local wrapper calls the `codex` CLI directly via Bash. The plan document is read **outside** Codex's sandbox and embedded into the review prompt, side-stepping Codex's own filesystem restrictions.

`$ARGUMENTS` is the path to the plan document (e.g. `plans/myproject_plan.md`). When invoked from `/plan-create`, the caller may read `.claude/data/plan-gate.json` → `plan_path` and pass it through.

## Steps

1. Validate the plan document exists:

   ```bash
   test -f "$ARGUMENTS" || { echo "Plan not found: $ARGUMENTS"; exit 1; }
   ```

   If it does not exist, stop and ask the user for the correct path — do not continue.

2. Compose the adversarial review prompt. Use `mktemp -d` to build a scratch directory so named-suffix files work portably on both GNU and BSD/macOS (`mktemp --suffix=…` is GNU-only). Use an unquoted here-doc so `$(cat …)` expands before Codex is invoked:

   ```bash
   TMP_DIR=$(mktemp -d)
   PROMPT_FILE="$TMP_DIR/prompt.md"
   cat > "$PROMPT_FILE" <<EOF
   You are adversarially reviewing a *plan document* (not code). Your job is to challenge the proposed approach. Look for:

   - Logical flaws in the task decomposition or dependency ordering
   - Missing edge cases and unstated assumptions
   - Invalid premises in the problem framing
   - Simpler alternatives the author may have overlooked
   - Hidden risks (correctness, regression, security, migration)

   Classify every finding with a severity tag:
   - [critical] blocks plan approval
   - [high]     must-resolve before execution starts
   - [medium]   should-resolve this cycle
   - [low]      nice-to-have
   - [info]     observation only

   Do NOT propose code edits — this is a planning artefact, not an implementation.

   === Plan document ($ARGUMENTS) ===
   $(cat "$ARGUMENTS")
   EOF
   ```

3. Invoke Codex. Use `read-only` sandbox and stream the prompt via stdin:

   ```bash
   codex exec --sandbox read-only < "$PROMPT_FILE"
   ```

   If `codex` is not on `PATH`, emit the standard skip notice and exit gracefully:

   > codex CLI not installed — skipping adversarial plan review. Install the `codex` CLI (e.g. `npm i -g @openai/codex`) to enable it.

4. Present Codex's verbatim output to the user with brief notes on which findings you accept, dispute, or want to flag as open questions. Do **not** silently accept everything Codex says — its job is to attack the plan, not to design it.

5. Apply accepted feedback directly to the plan document (revise tasks, add risks, refine the verification protocol, split High-difficulty tasks, etc.). The plan-gate hook is still in `plan-creating` mode, so project source files remain blocked — only the plan document itself may be edited.

6. If revisions were material, re-invoke this command to re-review the updated plan. Stop iterating once Codex's remaining feedback is informational only, or the user explicitly accepts the residual risks.

7. Clean up:

   ```bash
   rm -rf "$TMP_DIR"
   ```
