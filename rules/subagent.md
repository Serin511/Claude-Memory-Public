# Sub-Agent Worktree Isolation

When launching multiple sub-agents with `isolation: "worktree"`:

1. **No two agents may edit the same file.** Before launching a batch, partition files
   so each agent has exclusive ownership. If two tasks need the same file, run them
   sequentially or assign both changes to one agent.
2. **Commit before launching worktree agents.** Uncommitted changes in the main working
   tree can be silently lost when worktrees are cleaned up. Always commit first — never
   stash (stash/pop cycles lose staged state and compound data loss across sessions).
3. **Kill long-running agents promptly.** A worktree agent running for 30+ minutes
   without progress should be stopped — zombie agents cause repeated worktree cleanup
   events that revert main-tree changes.
4. **Verify changes survived after each agent completes.** Run `git diff --stat` after
   each ExitWorktree to confirm the expected files were modified. If changes are missing,
   re-apply immediately before launching the next agent.
5. **No background tasks in worktree subagents.** Worktree subagents must **never** use
   `run_in_background` for Bash commands. When the subagent completes, its worktree is
   cleaned up but orphaned background tasks continue running — they queue behind the
   resource gate and flood the main agent with stale notifications minutes to hours later.
   Run benchmarks/tests in the **foreground** within the subagent. If parallel execution
   is needed, the **main agent** should launch background tasks after merging results.

## Background Tasks Must Not Modify Git State

`run_in_background=true` Bash commands must be **read-only** with respect to git.
They must never run `git stash`, `git checkout`, `git reset`, `git add`, or any
command that modifies the working tree, index, or refs.

**Why:** Background tasks run in the main working tree as separate processes. When the
session's context window fills up and compaction occurs, the main agent terminates but
background tasks keep running. If a background task runs `git stash pop` or
`git checkout` after the session ends, it mutates the working tree silently. The next
session inherits a git state that doesn't match the compacted summary — leading to
data loss when the new session runs further git operations on the corrupted state.

**Allowed:** read-only commands (test runners, benchmarks, linters, `git log`, `git diff`)

**Forbidden:** `git stash && cmd && git stash pop`, `git checkout <branch> && cmd`,
any script that writes to tracked files.

**Session-start check:** When a session starts with orphaned task notifications,
run `git status` + `git stash list` before trusting the compacted summary's
description of git state.

## Commit Before Experimental Comparisons

Before testing HEAD performance or comparing branches, **always commit** current
changes (even as a WIP commit). Never use `git stash` to temporarily set aside
changes for comparison.

**Why:** `git stash pop` (without `--index`) silently converts staged changes to
unstaged, losing the index state. Repeated stash/pop cycles compound the loss.
Recovering from dangling stash commits gives only partial snapshots (index version
only for non-pathspec files). A commit is the only safe checkpoint.

**If stash recovery is needed:** Use `git show <sha>^2:<file>` — the `^2` parent
is the working tree snapshot. `git checkout <sha> -- <file>` retrieves only the
index version, which is incomplete.

**Pattern:**
```bash
git commit -m "wip: checkpoint before baseline comparison"
# ... run comparison ...
git reset HEAD~1   # restore working state cleanly
```

> If the project's git rules require explicit user approval for commits, ask
> before creating the WIP commit.

## No Pipes in Background Commands

Never use `| grep`, `| tail`, `| head` or other pipe filters when running commands
with `run_in_background=true`.

**Why:** Pipe commands buffer all input before producing output. The background task
output file captures the pipeline's final output, so it stays 0 bytes for the entire
duration of the upstream command. This makes it look like the command produced no output
when it's actually still running.

**Instead:** Run the raw command without pipes in background. After the task completes,
use `Read` or `Bash` to extract the relevant lines from the output.

## Zombie Subagent Contamination Prevention

Worktree subagents or background tasks from prior sessions can modify tracked files
after the session ends. These changes persist as unstaged modifications and get mixed
with intentional changes in later sessions.

**Prevention protocol:**

1. At the **start of each session**, run `git diff --stat` to check for unexpected
   unstaged changes. If present, investigate before proceeding.
2. Before staging for commit, always run `git diff --cached --stat` and verify each
   file's changes are intentional. Use `git diff --cached -- <file>` to review
   line-by-line.
3. When launching subagents for code modifications, explicitly instruct them to
   **only** modify the specific files/functions listed — never "also optimize nearby
   code."
4. After a session with many subagents, do a contamination check: `git diff --stat`
   should show only the files you explicitly intended to modify.
5. If contamination is found, restore files to HEAD (`git checkout -- <file>`) and
   re-apply only intentional changes manually.

## Compare Approaches Before Multi-File Refactoring

Before starting a refactoring that touches 3+ files, briefly compare the candidate
approaches (1-2 sentences each) and verify no existing mechanism already solves the
problem. Check related modules first — a round-trip refactoring (build then revert)
wastes far more tool calls than a 5-minute design check.
