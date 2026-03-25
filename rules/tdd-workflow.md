# TDD Workflow & Test Integrity

## 1. Red-Green-Refactor Cycle

All new logic and bug fixes **must** follow the TDD cycle:

1. **Red** — Write a failing test that defines the desired behaviour. Run it and confirm it **fails with an assertion error** (not an import error or exception from missing code).
2. **Green** — Write the **minimal** code to make the test pass. Do not anticipate future needs (YAGNI).
3. **Refactor** — Clean up implementation and tests while keeping all tests green.

```python
# Step 1 (Red): write the test FIRST
def test_expected_behavior():
    result = function_under_test(input_data)
    assert result == expected_output

# Step 2 (Green): implement just enough to pass
# Step 3 (Refactor): clean up, extract helpers, improve naming
```

## 2. Tests Before Implementation

- When adding a feature or fixing a bug, **create or update the test file before editing production code**.
- Never generate both the test and the implementation in one shot without running the test in between — this defeats the purpose of TDD.
- If modifying existing behaviour intentionally, update the test first to reflect the new expectation, confirm it fails against the old code, then change the implementation.
- For **multi-phase features** with interdependent components, apply Red-Green-Refactor to each phase individually. Do not implement multiple phases at once and test them together afterward.

## 3. Test File Structure

Tests live in `tests/` at the project root, mirroring the source directory structure:

```
src/module/parser.py       →  tests/module/test_parser.py
src/utils/format.py        →  tests/utils/test_format.py
```

- Shared fixtures: `tests/conftest.py`
- Sample/fixture files: `tests/fixtures/` (tracked by git)

> **Verify test paths before running**: Not all source modules have a 1:1 test file.
> Before running a specific test file, use `Glob` (e.g., `tests/**/test_*.py`) to
> confirm it exists. Never guess test file paths from source file structure alone.

Run commands:
- All tests: `pytest tests/ -v`
- Single module: `pytest tests/module/test_parser.py -v`
- Single test: `pytest tests/module/test_parser.py::test_name -v`

## 4. Never Skip Tests to Dodge Failures

- **Do NOT** add `pytest.mark.skip`, `skipif`, or `xfail` to work around a failure.
- `skipif` is only acceptable for **optional system-level dependencies** the CI may lack.
- Missing fixture? **Provide it** — do not skip.

## 5. Never Modify Tests to Match Broken Results

Fix the code, not the assertion. If expected behaviour has intentionally changed, update the test **and** explain why — but never silently weaken assertions.

```python
# BAD — loosening tolerance to hide a regression
assert result == pytest.approx(expected, abs=999)

# GOOD — keep the original tolerance; fix the code
assert result == pytest.approx(expected, abs=1e-6)
```

## 6. Sample / Fixture Files Belong in the Repo

- Test samples and fixtures are tracked by git.
- If a test needs a new sample, request it from the user or generate a minimal synthetic fixture — do not skip.
