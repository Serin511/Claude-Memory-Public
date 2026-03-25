---
allowed-tools: Bash(git status), Bash(git diff), Bash(git log), Bash(git branch), Bash(git push), Bash(gh pr create), Bash(gh pr list)
description: Create a Pull Request without committing
argument-hint: [base branch (optional, default: main)]
---

# Create Pull Request

Create a PR from the current branch without touching staged files or commits.

## 1. Check current state

```
git branch --show-current
git status
git log --oneline -10
```

## 2. Determine base branch

- If `$ARGUMENTS` is provided, use it as the base branch.
- Otherwise, default to `main`.
- If the current branch equals the base branch, abort and notify the user.

## 3. Analyze changes

- Run `git log <base>..<current> --oneline` to list commits to be included.
- Run `git diff <base>...HEAD` to understand what changed.
- Identify the nature of changes (feat / fix / docs / refactor / etc.) and key content.

## 4. Write PR title and body

**Title rules:**
- Under 50 characters, English, imperative mood
- Conventional Commits format: `<type>: <subject>`

**Body template:**
```
## Summary
- 2-3 bullet points summarizing the key changes

## Test plan
- Checklist of how to test / verify the changes
```

## 5. Sync remote branch

- If the current branch has no remote tracking branch, run `git push -u origin <branch>` first.
- If it already exists remotely, skip the push.

## 6. Create PR

- Run `gh pr list` to check for an already-open PR on this branch. If one exists, notify the user and abort.
- Run `gh pr create` using a HEREDOC for the body.
- After completion, print the PR URL for the user.
