# Claude Memory

A portable configuration system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Sync your slash commands, behavioral rules, and global instructions across machines via Git.

## What's Included

```
├── install.sh              # One-line installer
├── sync.sh                 # Push/pull sync engine
├── CLAUDE.md               # Global instructions (loaded in every project)
├── commands/               # Slash commands (invoked with /<name>)
│   ├── push.md             # /push — commit and push with foundation file checks
│   ├── make-pr.md          # /make-pr — create a PR from the current branch
│   ├── doc-sync.md         # /doc-sync — sync Google-style docstrings for staged files
│   ├── fix-loop.md         # /fix-loop — iterative measure→diagnose→fix→verify cycle
│   ├── hypothesis-lab.md   # /hypothesis-lab — parallel experiments in isolated worktrees
│   ├── perf-optimize.md    # /perf-optimize — profile and optimize bottlenecks
│   ├── update-harness.md   # /update-harness — analyze session logs, propose rule improvements
│   ├── add-command.md      # /add-command — guide for creating new slash commands
│   ├── system-prompt-editor.md  # /system-prompt-editor — edit global CLAUDE.md
│   ├── plan-create.md      # /plan-create — produce a structured execution plan doc
│   └── plan-execute.md     # /plan-execute — orchestrate subagents to run a plan doc
├── rules/                  # Behavioral rules (always loaded, no invocation needed)
│   ├── documentation-standard.md  # Google-style docstrings, JSDoc, test requirements
│   ├── tdd-workflow.md     # Red-green-refactor cycle enforcement
│   ├── read-before-guessing.md   # Read class/API definitions before accessing attributes
│   └── subagent.md         # Worktree isolation safety, background task constraints
└── scripts/
    └── parse_sessions.py   # Extract failure signals from session logs (used by /update-harness)
```

## Quick Start

### 1. Create your own private copy

GitHub forks of public repos are always public. To keep your config private, create a new repo from this one:

```bash
# 1. Create a new private repo on GitHub (do NOT use Fork)
gh repo create my-claude-memory --private

# 2. Clone this repo, swap the remote to yours, and push
git clone https://github.com/Serin511/Claude-Memory-Public.git ~/.claude-sync
cd ~/.claude-sync
git remote set-url origin https://github.com/<you>/my-claude-memory.git
git push -u origin main
```

Or via the GitHub UI: click **Use this template** → **Create a new repository** → set visibility to **Private** (if the template button is available), then clone normally.

### 2. Install

```bash
# If you already cloned in Step 1, just run the installer
~/.claude-sync/install.sh

source ~/.zshrc  # or ~/.bashrc
```

Or as a one-liner (replace with your private repo URL):

```bash
curl -fsSL https://raw.githubusercontent.com/<you>/my-claude-memory/main/install.sh | bash -s -- https://github.com/<you>/my-claude-memory.git
source ~/.zshrc  # or ~/.bashrc
```

This will:
1. Clone your repo to `~/.claude-sync/`
2. Symlink configurations into `~/.claude/` (commands, rules, CLAUDE.md)
3. Add auto-sync hooks to your shell RC file

### 3. Staying up to date with upstream

Add this repo as a remote to pull future updates:

```bash
cd ~/.claude-sync
git remote add upstream https://github.com/Serin511/Claude-Memory-Public.git

# Pull upstream changes when needed
git fetch upstream
git merge upstream/main
```

Your local customizations stay intact — only new or updated files from upstream are merged.

## How It Works

### Symlink Architecture

The installer creates symlinks from `~/.claude/` (where Claude Code reads config) to `~/.claude-sync/` (the Git repo):

```
~/.claude/commands/  →  ~/.claude-sync/commands/
~/.claude/rules/     →  ~/.claude-sync/rules/
~/.claude/CLAUDE.md  →  ~/.claude-sync/CLAUDE.md
```

This means Claude Code reads directly from the Git-managed directory. Any changes you make are tracked by Git.

### Auto Sync

The installer adds shell hooks to your `.zshrc` / `.bashrc`:

- **`ssh`**: Automatically pushes local config before SSH-ing to a remote machine
- **Login shell**: Automatically pulls latest config when you log in (with 5-minute cooldown)
- **`claude-sync push`**: Manually push local changes
- **`claude-sync pull`**: Manually pull remote changes

### Symlink Repair

Claude Code occasionally replaces symlinks with regular files. The sync engine detects this, copies the content back to the repo, and re-creates the symlink — no manual intervention needed.

## Slash Commands

### `/push` — Commit & Push
Stages changes, updates foundation files (README, CLAUDE.md, .gitignore, dependency files), writes a conventional commit message, and pushes.

### `/make-pr` — Create Pull Request
Creates a GitHub PR from the current branch using `gh`. Analyzes commits, writes title/body, and handles remote branch setup.

### `/doc-sync` — Docstring Sync
Scans staged and modified `.py` / `.ts` / `.tsx` files, updates missing or outdated docstrings to Google style (Python) or JSDoc (TypeScript), and re-stages.

### `/fix-loop` — Iterative Fix Cycle
Generic measure → classify → fix → verify → repeat framework. Define your baseline measurement, verification commands, and termination condition in your project's CLAUDE.md, then run `/fix-loop` to iterate until the target is met.

### `/hypothesis-lab` — Parallel Experimentation
Tests multiple solution strategies simultaneously using isolated git worktrees. Each approach runs in its own worktree subagent, verified independently, then merged sequentially through a regression-gated queue.

### `/perf-optimize` — Performance Optimization
Profiles application performance, identifies bottlenecks, and optimizes using the `/fix-loop` cycle. Supports Python (cProfile) and Node.js profiling, with parallel strategy testing via `/hypothesis-lab`.

### `/update-harness` — Session Analysis
Parses Claude Code session logs to find failure patterns (tool errors, retry loops, user corrections), cross-references with existing rules, and proposes improvements to CLAUDE.md and rules files.

### `/add-command` — Command Creator Guide
Reference guide for creating new slash commands — covers frontmatter options, security restrictions, and common patterns.

### `/system-prompt-editor` — Edit Global Prompt
Opens `~/.claude/CLAUDE.md` for direct editing with backup support.

### `/plan-create` — Execution Plan Creation
Breaks down a multi-phase goal into a structured plan document with major tasks, sub-tasks, dependency ordering, verification gates, and carry-forward rules. The plan document is a durable Markdown artifact that survives session boundaries and is executable by `/plan-execute`.

### `/plan-execute` — Plan Execution Orchestration
Reads a plan document produced by `/plan-create` and executes it — one major task at a time. Each task is delegated to a dedicated subagent with full context, verification commands, and progress tracking. Handles crash recovery, dependency resolution, and discovered work routing.

## Rules

Rules are always loaded into Claude Code's context. Unlike commands, they don't need to be invoked.

| Rule | Purpose |
|------|---------|
| `documentation-standard.md` | Enforce Google-style docstrings (Python) and JSDoc (TypeScript) |
| `tdd-workflow.md` | Red → Green → Refactor cycle; tests before implementation |
| `read-before-guessing.md` | Read class/API definitions before accessing attributes; inspect JSON before parsing |
| `subagent.md` | Worktree isolation safety, background task constraints, zombie agent prevention |

## Customization

### Adding Your Own Commands

Create a markdown file in `~/.claude-sync/commands/`:

```markdown
---
allowed-tools: Read, Edit, Bash(git:*)
description: What this command does
---

# My Command

Instructions for Claude here.
```

Then run `claude-sync push` to sync across machines.

### Adding Your Own Rules

Create a markdown file in `~/.claude-sync/rules/`:

```markdown
## My Rule

Always do X when Y happens because Z.
```

Rules are loaded automatically — no frontmatter needed.

### Syncing Project Memory

By default, per-project memory (`~/.claude/projects/*/memory/`) is **not** synced. To enable it, export `CLAUDE_SYNC_PROJECTS=1` in your shell RC file before the claude-sync block:

```bash
export CLAUDE_SYNC_PROJECTS=1
```

When enabled, `claude-sync push` collects project memory into the repo and `claude-sync pull` symlinks it back. This is useful for syncing memory across machines, but the memory may contain project-specific context you don't want in version control.

### Modifying Global Instructions

Edit `~/.claude-sync/CLAUDE.md` or use `/system-prompt-editor` within Claude Code.

## Manual Sync

```bash
claude-sync push    # commit and push local changes
claude-sync pull    # pull remote changes and repair symlinks
```

## Uninstall

1. Remove the sync block from your shell RC file (between `# >>> claude-sync >>>` and `# <<< claude-sync <<<`)
2. Remove symlinks: `rm ~/.claude/commands ~/.claude/rules ~/.claude/CLAUDE.md`
3. Remove the repo: `rm -rf ~/.claude-sync`

## Requirements

- macOS or Linux
- Git
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- `gh` CLI (only for `/make-pr`)

## License

MIT
