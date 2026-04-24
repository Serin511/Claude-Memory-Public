<!-- 규칙은 ~/.claude/rules/ 에서 관리됩니다 -->

# Global Instructions

## Chat Rules

IMPORTANT: For anything ambiguous or that requires my decision, **always** ask me a clarifying question. Never make assumptions and proceed on your own.

## Parallelism
- Spawn sub-agents for independent file modifications to process them in parallel.
- Run tests, linting, and type checking concurrently.
- Allow parallel execution for tasks with no risk of branch conflicts.

## Sub-agent Guidelines
- Assign each sub-agent a single, clear responsibility.
- Report results back to the main agent upon completion.

## Memory

- Always write memory files in English.
