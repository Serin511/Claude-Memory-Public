---
allowed-tools: Bash(git status), Bash(git diff), Bash(git log), Bash(git add), Bash(git commit), Bash(git push), Bash(git branch), Read
description: Prepare, commit, and push changes to GitHub
argument-hint: [commit message (optional)]
---

# Git Commit & Push

Execute the steps below in order.

## 1. Inspect current state

```
git status
git diff
git log --oneline -5
git branch --show-current
```

## 2. Analyse changes

- Review staged / unstaged / untracked files.
- Determine the nature of the changes from the diff (feat / fix / refactor / test / docs / chore / etc.).
- Warn the user and exclude from staging any files that must not be committed (`.env`, secrets, large binaries).

## 3. Update project foundation files (mandatory)

Before committing, **always** update the files below to reflect the current work — only if they need it:

- `README.md` — reflect any changes to the public API, installation steps, or usage examples.
- `CLAUDE.md` — reflect any changes to architecture, module structure, or commands.
- `.gitignore` — add new artifact types if not already covered.
- `requirements.txt` / `pyproject.toml` / `package.json` — sync dependencies if they changed. (**Do not modify `version`**.)

Leave files that need no changes untouched. Include any updated files in staging.

## 4. Commit message rules

- Write in **English**.
- Conventional Commits format: `<type>: <subject>` (lowercase)
  - Allowed types: `feat`, `fix`, `refactor`, `chore`, `test`, `docs`, `style`, `perf`
- Keep the subject under 50 characters, imperative mood (e.g. "add", "fix", "update" — not "added", "fixed").
- Add a body after a blank line if more detail is needed.
- Use `$ARGUMENTS` as a hint for the commit message if provided.
- Don't mention about 'co-author claude'

## 5. Stage files

- Selectively `git add` only the relevant files, excluding any sensitive ones.

## 6. Docstring sync (only when the project has the doc-sync command)

Check with Read whether `.claude/commands/doc-sync.md` exists.
If it does, follow the **Steps** instructions in that file to update docstrings in staged Python files and re-stage them.
If it does not, skip this step.

## 7. Commit

- Show the final commit message to the user and get confirmation.
- After approval, commit using a HEREDOC.

## 8. Push

- Check the current branch and run `git push` (or `git push -u origin <branch>` for a first push).
- Summarise the result after the push completes.
