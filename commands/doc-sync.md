---
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
description: Sync Google-style docstrings for all staged or modified files
---

# Doc Sync

Update docstrings in all staged and unstaged changed files to conform to the project's
documentation standard. Re-stage the files automatically after updating.

---

## Documentation Standard

### Python Docstrings — Google Style (English)

All Python files must use **Google-style docstrings in English** at module, class, and
function/method level. NumPy/Sphinx style (`Parameters`, `Returns` with `---` underlines)
is **prohibited**.

**Required sections per level:**
- **Module docstring:** purpose, key exports, usage context.
- **Class docstring:** responsibility, key attributes, usage context.
- **Function/method docstring:** one-line summary + `Args:`, `Returns:`, `Raises:` as applicable.

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

# BAD — numpydoc style (prohibited)
def process(data, timeout):
    """Process data.

    Parameters
    ----------
    data : str
        ...
    """
```

Update docstrings **once before committing** (not during active development).

### JavaScript / TypeScript Docstrings — JSDoc (English)

```typescript
/**
 * Fetches user data from the API.
 *
 * @param userId - The unique identifier of the user.
 * @returns A promise resolving to the user object.
 * @throws {ApiError} If the request fails.
 */
async function fetchUser(userId: string): Promise<User> { ... }
```

### `__init__.py` Docstrings

Every `__init__.py` must have a module-level docstring listing the public exports and a
one-line usage example:

```python
"""String utilities for common text transformations.

Exports:
    slugify, truncate, normalize_whitespace, to_camel_case.

Example:
    >>> from myproject.utils.strings import slugify
    >>> slugify("Hello World")
    'hello-world'
"""
```

### Consistency Rules

- Docstrings and code comments → **English only**.
- Do **not** add comments that merely narrate what the code does.
- Only comment non-obvious intent, trade-offs, or constraints.
- Follow the existing documentation depth already present in the file being modified.

---

## Steps

### 1. Identify changed files

```
git diff --cached --name-only --diff-filter=ACM
git diff --name-only --diff-filter=ACM
```

Merge the results of both commands. Filter to `.py`, `.ts`, `.tsx` files only.
Exclude test files (`test_*.py`, `*.test.ts`, `*.test.tsx`) and type declarations (`*.d.ts`).
Remove duplicates. If no files are found, report "no files to update" and skip to step 4.

### 2. Review and update docstrings for each file

For each file:

1. Run `git diff HEAD -- <file>` to inspect the actual changes.
2. Read the full file with `Read`.
3. Review against the **Documentation Standard** above:
   - **Module docstring** — top of file, purpose + key exports + usage context.
   - **Class docstring** — responsibility, key attributes, usage example.
   - **Public function/method docstring** — one-line summary + `Args:` + `Returns:` + `Raises:` (only where applicable).
4. Update only docstrings that are missing or no longer match the changed logic. Leave everything else untouched.
5. Apply changes with `Edit`. Multiple items in one call is fine.

### 3. Re-stage updated files

```
git add <modified files>
```

### 4. Foundation file checklist

After running doc-sync, verify and update if needed:

- [ ] **`README.md`** — update when public API or installation steps change.
- [ ] **`CLAUDE.md`** — update when architecture, module structure, or commands change.
- [ ] **`.gitignore`** — add new artifact types if not already covered.
- [ ] **Dependency files** (`requirements.txt`, `pyproject.toml`, `package.json`) — sync dependencies when they change. **Do NOT modify `version`**.

Stage any updated foundation files.

### 5. Report completion

- Briefly summarise which files were updated and what changed.
- Also list files that required no changes.
- Remind the user of the workflow order: run `/doc-sync` first, then `git commit`.
