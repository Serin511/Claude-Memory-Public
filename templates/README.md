# Skill Templates

Reusable skill templates that can be copied into any project's `.claude/skills/`
directory. These are **not** installed as active slash commands by `install.sh` —
they live here as starting points, so the global shell and a per-project copy
will never collide.

## Available Templates

| Template | Purpose |
|----------|---------|
| `plan-create/`  | Produce a structured execution plan document for multi-phase projects. |
| `plan-execute/` | Execute a plan-create document by orchestrating subagents per major task. |

The two are designed to be used together: `plan-create` writes the plan, and
`plan-execute` runs it.

## How to Deploy to a Project

From the target project's root directory:

```bash
# Deploy both skills
mkdir -p .claude/skills
cp -r ~/.claude-sync/templates/plan-create  .claude/skills/
cp -r ~/.claude-sync/templates/plan-execute .claude/skills/

# Commit so the team (and future sessions) inherit them
git add .claude/skills/plan-create .claude/skills/plan-execute
git commit -m "chore(skills): add plan-create and plan-execute"
```

After deployment the skills are invokable as `/plan-create` and `/plan-execute`
inside that project only.

## Per-Project Customization

Each template has placeholders (marked `<like-this>`) that should be filled in
for the concrete project. At minimum, edit the following before first use:

1. **Verification commands** — `plan-create` asks the user for L1/L2/L3
   commands at interview time, so you usually don't need to hard-code them.
   But if the project has a canonical test/benchmark/lint runner, mentioning
   it in the skill's "Defaults" section saves the interview round-trip.
2. **Default plan path** — `docs/<project>_plan.md` is the default. Change it
   if the project uses a different docs layout (e.g. `plans/`, `notes/`).
3. **Language-specific examples** — The templates reference generic runner
   names (`<test runner>`, `<benchmark runner>`). Replace with the project's
   actual commands if you want concrete defaults in the skill body.

## Why Templates, Not Global Commands

A global slash command (in `~/.claude/commands/`) is discoverable everywhere
but collides with any same-named project command. For orchestration skills
like these, the project-level copy is the source of truth — it's committed to
the repo, reviewed with the rest of the code, and can diverge per-project
without touching the user's home directory.

Keeping the master copy here (but not symlinking it) gives you a single place
to update the "reference" version while leaving each project free to evolve
its own copy.
