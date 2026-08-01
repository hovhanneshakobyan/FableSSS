---
name: python-testing
description: Write and run pytest tests for this project, including fixtures, parametrization, and coverage checks. Use when adding new functionality that needs tests, fixing a bug that needs a regression test, or when the user asks to run or write tests.
---

# Python Testing (pytest)

## Quick start

1. Mirror the source layout: code in `src/pkg/module.py` gets tests in
   `tests/test_module.py` (or `tests/pkg/test_module.py` for larger trees).
2. One behavior per test function; name tests
   `test_<unit>_<condition>_<expected_result>`.
3. Prefer `pytest` plain asserts over `unittest`-style assertions — no need for
   `self.assertEqual`, just `assert a == b`.
4. Use fixtures for shared setup instead of copy-pasted setup code.
5. Run the target test file/case while iterating; run the full suite before
   finishing:

```bash
pytest tests/test_module.py -k "test_name" -v   # fast iteration
pytest                                            # full suite before done
```

## Structure template

```python
import pytest

from pkg.module import thing_under_test


@pytest.fixture
def sample_input():
    return {...}


def test_thing_under_test_valid_input_returns_expected(sample_input):
    result = thing_under_test(sample_input)
    assert result == expected


def test_thing_under_test_invalid_input_raises_value_error():
    with pytest.raises(ValueError):
        thing_under_test(None)
```

## Parametrization

Use `@pytest.mark.parametrize` for multiple similar cases instead of
duplicating test bodies:

```python
@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        (0, 0),
        (1, 1),
        (-1, 1),
    ],
)
def test_abs_returns_non_negative(input_value, expected):
    assert abs(input_value) == expected
```

## Regression tests

Every bug fix gets a test that fails on the old code and passes on the fix.
Name it to reference the bug if there's an issue/PR number, otherwise describe
the scenario (`test_parse_config_empty_file_does_not_raise`).

## Checklist

- [ ] Test file mirrors source module path
- [ ] Test names describe unit + condition + expected result
- [ ] Edge cases covered (empty input, `None`, boundary values, errors)
- [ ] No hidden shared mutable state between tests
- [ ] `pytest` passes locally before calling the work done
