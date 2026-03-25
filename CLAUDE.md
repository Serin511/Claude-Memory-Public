<!-- 규칙은 ~/.claude/rules/ 에서 관리됩니다 -->

# Global Instructions

## Parallelism
- Spawn sub-agents for independent file modifications to process them in parallel.
- Run tests, linting, and type checking concurrently.
- Allow parallel execution for tasks with no risk of branch conflicts.

## Sub-agent Guidelines
- Assign each sub-agent a single, clear responsibility.
- Report results back to the main agent upon completion.

## Memory

- When the `/push` command is invoked by the user, both `git commit` and `git push` are considered explicitly requested. Proceed without additional confirmation.
- Always write memory files in English.
