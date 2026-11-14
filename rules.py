"""
Reads exercises/<id>/rules.json and builds the same criteria a criteria.py
would. Each test names a check ("call" or "program") and gives its
parameters, so a simple exercise needs no Python.
"""

import json
from typing import Any

from checks import call, criterion, named, program

TOP_KEYS = {"title", "load_inputs", "ai_trap", "criteria"}
CRITERION_KEYS = {"name", "points", "description", "hint", "review", "tests"}
CALL_KEYS = {
    "check", "function", "args", "expected", "output", "output_contains",
    "output_excludes", "mutates", "inputs", "check_return", "weight", "hint",
    "label", "names",
}
PROGRAM_KEYS = {
    "check", "inputs", "contains", "excludes", "must_finish", "weight",
    "hint", "label",
}


def _check_keys(item: Any, allowed: set[str], where: str) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"{where}: expected an object")
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key '{unknown[0]}' "
                         f"(allowed: {', '.join(sorted(allowed))})")


def _require(item: dict, key: str, where: str) -> Any:
    if key not in item:
        raise ValueError(f"{where}: missing '{key}'")
    return item[key]


def _check_number(value: Any, key: str, where: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: '{key}' must be a number")


def _check_list(value: Any, key: str, where: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{where}: '{key}' must be a list")


def _name_arguments(args: list, names: dict, where: str) -> None:
    """Show a list or dict argument under a short name in the report."""
    for position, name in names.items():
        index = int(position)
        if index >= len(args) or not isinstance(args[index], (list, dict)):
            raise ValueError(f"{where}: 'names' only works on list or "
                             f"object arguments (position {position})")
        named(args[index], name)


def _build_call(item: dict, where: str, has_solution: bool) -> dict:
    _check_keys(item, CALL_KEYS, where)
    function = _require(item, "function", where)
    args = item.get("args", [])
    _check_list(args, "args", where)
    _name_arguments(args, item.get("names", {}), where)
    if not has_solution:
        needs_solution = item.get("mutates") or item.get("output") == "equal"
        if needs_solution:
            raise ValueError(f"{where}: 'mutates' and 'output' need "
                             "a solution.py to compare with")
        if item.get("check_return", True) and "expected" not in item:
            raise ValueError(f"{where}: add 'expected' or a solution.py")
    options = {
        key: value for key, value in item.items()
        if key not in ("check", "function", "args", "names")
    }
    return call(function, *args, **options)


def _build_program(item: dict, where: str) -> dict:
    _check_keys(item, PROGRAM_KEYS, where)
    inputs = [str(answer) for answer in _require(item, "inputs", where)]
    options = {key: value for key, value in item.items()
               if key not in ("check", "inputs")}
    return program(inputs, **options)


def _build_test(item: Any, where: str, has_solution: bool) -> dict:
    check = item.get("check") if isinstance(item, dict) else None
    if check == "call":
        return _build_call(item, where, has_solution)
    if check == "program":
        return _build_program(item, where)
    raise ValueError(f"{where}: 'check' must be \"call\" or \"program\"")


def _build_criterion(item: Any, number: int, has_solution: bool) -> dict:
    where = f"criterion {number}"
    _check_keys(item, CRITERION_KEYS, where)
    name = _require(item, "name", where)
    where += f" ({name})"
    points = _require(item, "points", where)
    _check_number(points, "points", where)
    tests_data = _require(item, "tests", where)
    _check_list(tests_data, "tests", where)
    tests = [
        _build_test(test, f"{where}, test {index}", has_solution)
        for index, test in enumerate(tests_data, 1)
    ]
    options = {key: value for key, value in item.items()
               if key in ("description", "hint", "review")}
    return criterion(name, points, tests, **options)


def load_rules(path: str, has_solution: bool) -> dict:
    """Return title, load_inputs, ai_trap and criteria, like criteria.py."""
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"rules.json is not valid JSON: {error}") from None
    _check_keys(data, TOP_KEYS, "rules.json")
    criteria_data = _require(data, "criteria", "rules.json")
    _check_list(criteria_data, "criteria", "rules.json")
    return {
        "title": data.get("title"),
        "load_inputs": [str(answer) for answer in data.get("load_inputs", [])],
        "ai_trap": [str(word) for word in data.get("ai_trap", [])],
        "criteria": [
            _build_criterion(item, number, has_solution)
            for number, item in enumerate(criteria_data, 1)
        ],
    }
