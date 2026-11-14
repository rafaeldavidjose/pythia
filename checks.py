"""
Building blocks for each exercise's criteria.py.

A criterion groups tests and is worth some points. Its grade is the share of
passing tests (by weight), rounded to 0.25.

call() runs a function of the student and of the solution with the same
arguments and compares them. program() runs the whole file with fixed answers
to input() and looks for phrases in the output.

Labels, descriptions and hints go into the reports, so they are in Portuguese.
"""

from typing import Any

_NAMES: dict[int, str] = {}


def named(value: Any, name: str) -> Any:
    """Give a value (e.g. a map) a short name to use in report messages."""
    _NAMES[id(value)] = name
    return value


def _show(value: Any) -> str:
    if id(value) in _NAMES:
        return _NAMES[id(value)]
    text = repr(value)
    return text if len(text) <= 40 else "[...]"


def criterion(
    name: str,
    points: float,
    tests: list[dict],
    description: str = "",
    hint: str = "",
    review: bool = False,
) -> dict:
    """
    hint is used when a test fails and has no hint of its own. review flags
    the criterion for manual checking.
    """
    return {
        "name": name,
        "points": points,
        "tests": tests,
        "description": description,
        "hint": hint,
        "review": review,
    }


def call(
    func: str,
    *args: Any,
    check_return: bool = True,
    expected: Any = None,
    output: str | None = None,
    output_contains: tuple | list = (),
    output_excludes: tuple | list = (),
    mutates: tuple | list = (),
    inputs: tuple | list = (),
    weight: float = 1,
    hint: str = "",
    label: str | None = None,
) -> dict:
    """
    By default the return value is compared with the solution's. expected
    replaces that with a fixed value. output="equal" compares what is printed
    (ignoring whitespace, case and accents). mutates lists the argument
    positions that must end up equal to the solution's. inputs feeds input().
    """
    if label is None:
        label = f"{func}({', '.join(_show(arg) for arg in args)})"
    return {
        "kind": "call",
        "func": func,
        "args": list(args),
        "check_return": check_return,
        "expected": expected,
        "has_expected": expected is not None,
        "output": output,
        "output_contains": list(output_contains),
        "output_excludes": list(output_excludes),
        "mutates": list(mutates),
        "inputs": list(inputs),
        "weight": weight,
        "hint": hint,
        "label": label,
        "arg_names": [
            _show(arg) if id(arg) in _NAMES else f"argumento {i + 1}"
            for i, arg in enumerate(args)
        ],
    }


def program(
    inputs: list[str],
    contains: tuple | list = (),
    excludes: tuple | list = (),
    must_finish: bool = True,
    weight: float = 1,
    hint: str = "",
    label: str | None = None,
) -> dict:
    """
    Phrases in contains and excludes ignore case, accents and extra spaces.
    With must_finish the program cannot ask for more input than given.
    """
    if label is None:
        label = f"programa com as entradas {', '.join(inputs)}"
    return {
        "kind": "program",
        "inputs": list(inputs),
        "contains": list(contains),
        "excludes": list(excludes),
        "must_finish": must_finish,
        "weight": weight,
        "hint": hint,
        "label": label,
    }
