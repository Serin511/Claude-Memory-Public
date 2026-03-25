# Documentation Standard

## 1. Python Docstrings — Google Style (English)

All Python files must use **Google-style docstrings in English** at module, class, and function/method level. Numpydoc style (`Parameters`, `Returns`, `Raises` sections with `---` underlines) is **prohibited**.

**Required sections per level:**

- **Module docstring:** Purpose, key exports, usage context.
- **Class docstring:** Responsibility, key attributes, usage context.
- **Function/method docstring:** One-line summary + `Args:`, `Returns:`, `Raises:` as applicable.

```python
# GOOD — Google style
def process(data: str) -> dict:
    """Process the input string and return structured data.

    Args:
        data: Raw input string to parse.

    Returns:
        A dictionary containing parsed fields.

    Raises:
        ValueError: If ``data`` is empty or malformed.
    """

# BAD — numpydoc style
def process(data: str) -> dict:
    """Process input.

    Parameters
    ----------
    data : str
        ...

    Returns
    -------
    dict
        ...
    """
```

### `__init__.py` Docstrings

Every `__init__.py` must have a module-level docstring listing the public exports and a one-line usage example:

```python
"""Utility functions for data transformation.

Exports:
    parse_input, validate_schema, transform_output.

Example:
    >>> from mypackage.utils import parse_input
    >>> result = parse_input("raw data")
"""
```

## 2. JavaScript / TypeScript Docstrings — JSDoc (English)

All JS/TS files must use **JSDoc-style docstrings in English** at module, class, and function level.

```typescript
// GOOD
/**
 * Fetches user data from the API.
 *
 * @param userId - The unique identifier of the user.
 * @returns A promise resolving to the user object.
 * @throws {ApiError} If the request fails.
 */
async function fetchUser(userId: string): Promise<User> { ... }
```

## 3. Test Code Requirements

When adding new logic or modifying existing logic, **always add or update test code**:

- **Python**: Use `pytest`. Place tests under `tests/` matching the module structure.
  - Mock external service calls (LLM, DB, API) in unit tests.
  - Use real services only in optional integration tests (mark with `@pytest.mark.skipif`).
  - Update the test file's module docstring to reflect new test scenarios.
- **JavaScript / TypeScript**: Use `Jest` or `Vitest`. Colocate tests in `__tests__/` or `.test.ts` files.

## 4. Pre-commit Documentation Sync

Docstring updates and foundation file checks are done **once before committing**, not during active development. Run `/doc-sync` to update docstrings in staged files and verify foundation files (`README.md`, `CLAUDE.md`, `.gitignore`, dependency files).

See `.claude/skills/doc-sync/SKILL.md` for the full workflow.

## 5. Consistency Rules

- Docstrings and code comments → **English only**
- User-facing strings (UI, logs, error messages) → may follow project locale
- Do **not** add comments that merely narrate what the code does (e.g., `// increment counter`)
- Only comment non-obvious intent, trade-offs, or constraints
- Keep `CLAUDE.md` and `README.md` in sync when architecture, flow, or run steps change
- Docstring depth for `__init__.py` files: list public exports and brief usage example
- Follow the existing documentation depth and detail level already present in the codebase
