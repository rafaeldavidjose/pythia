"""
Building blocks for each exercise's criteria.py.

A criterion groups tests and is worth a number of points. Its automatic grade
is proportional to the weight of the tests that pass, rounded to 0.25.

Available tests:

    call(func, *args, ...)   calls the student's function and the reference
                             solution's function with the same arguments and
                             compares the results
    program(inputs, ...)     runs the whole file with these answers to input()
                             and looks for phrases in the output

Labels, descriptions and hints are shown to students in the reports, so they
are written in Portuguese.
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
    name         short name shown in the report table
    points       maximum grade for this criterion
    tests        list of call(...) / program(...) tests
    description  what was asked (shown in the Exercises tab)
    hint         shown when a test fails and that test has no hint of its own
    review       True to flag this criterion for manual review
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
    check_return     compare the returned value with the solution's
    expected         compare with this value instead of the solution's
    output           "equal" compares what the function prints with the
                     solution (ignores whitespace, case and accents)
    output_contains  phrases that must appear in what the function prints
    output_excludes  phrases that must not appear
    mutates          argument positions (0, 1, ...) whose state after the call
                     must match the solution's
    inputs           answers given to input() during the call
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
    inputs       answers given to input(), in order
    contains     phrases that must appear in the output (case, accents and
                 extra spaces are ignored)
    excludes     phrases that must not appear
    must_finish  the program must end without asking for more inputs
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
