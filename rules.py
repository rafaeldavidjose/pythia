"""
Reads exercises/<id>/rules.json. As in an egrader rules file, every test
names a check and gives its params. The params are checked against the
check's function in checks.py, so a typo is reported with its place in the
file instead of failing silently while grading.
"""

import json
from typing import Any

import checks

TOP_KEYS = {"title", "load_inputs", "ai_trap", "criteria"}
CRITERION_KEYS = {
    "criterion", "points", "description", "hint", "review", "tests",
}
TEST_KEYS = {"name", "params", "weight", "hint", "label"}

PARAM_TYPES = {
    "function": str, "args": list, "inputs": list, "contains": list,
    "excludes": list, "names": dict, "position": int, "must_finish": bool,
}
TYPE_NAMES = {
    str: "a string", list: "a list", dict: "an object", int: "an integer",
    bool: "true or false", float: "a number",
}


def _check_type(value: Any, expected: type, key: str, where: str) -> None:
    if expected is float:
        valid = isinstance(value, (int, float))
    elif expected is int:
        valid = isinstance(value, int)
    else:
        valid = isinstance(value, expected)
    if expected is not bool and isinstance(value, bool):
        valid = False
    if not valid:
        raise ValueError(f"{where}: '{key}' must be {TYPE_NAMES[expected]}")


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


def _check_params(name: str, params: dict, where: str) -> None:
    accepted = {parameter.name: parameter
                for parameter in checks.parameters(name)}
    for key, value in params.items():
        if key not in accepted:
            raise ValueError(f"{where}: check '{name}' has no param '{key}' "
                             f"(params: {', '.join(accepted)})")
        if key in PARAM_TYPES:
            _check_type(value, PARAM_TYPES[key], key, where)
    for key, parameter in accepted.items():
        if parameter.default is parameter.empty and key not in params:
            raise ValueError(f"{where}: check '{name}' needs param '{key}'")
    position = params.get("position", 0)
    if "args" in params and name == "mutates":
        if not 0 <= position < len(params["args"]):
            raise ValueError(f"{where}: 'position' {position} is not "
                             f"one of the args")


def _build_test(item: Any, where: str, has_solution: bool) -> dict:
    _check_keys(item, TEST_KEYS, where)
    name = _require(item, "name", where)
    if name not in checks.available():
        raise ValueError(f"{where}: unknown check '{name}' "
                         f"(checks: {', '.join(checks.available())})")
    params = item.get("params", {})
    _check_type(params, dict, "params", where)
    _check_params(name, params, where)
    if not has_solution and checks.needs_solution(name, params):
        raise ValueError(f"{where}: add 'expected' to the params "
                         "or a solution.py to compare with")
    weight = item.get("weight", 1)
    _check_type(weight, float, "weight", where)
    if weight < 0:
        raise ValueError(f"{where}: 'weight' cannot be negative")
    label = item.get("label") or checks.default_label(
        name, checks.decode(params))
    return {"name": name, "params": params, "weight": weight,
            "hint": item.get("hint", ""), "label": label}


def _build_criterion(item: Any, number: int, has_solution: bool) -> dict:
    where = f"criterion {number}"
    _check_keys(item, CRITERION_KEYS, where)
    name = _require(item, "criterion", where)
    _check_type(name, str, "criterion", where)
    where += f" ({name})"
    points = _require(item, "points", where)
    _check_type(points, float, "points", where)
    tests_data = item.get("tests", [])
    _check_type(tests_data, list, "tests", where)
    tests = [
        _build_test(test, f"{where}, test {index}", has_solution)
        for index, test in enumerate(tests_data, 1)
    ]
    return {
        "name": name,
        "points": points,
        "description": item.get("description", ""),
        "hint": item.get("hint", ""),
        "review": bool(item.get("review", False)),
        "tests": tests,
    }


def parse_rules(text: str, has_solution: bool) -> dict:
    """Return title, load_inputs, ai_trap and the criteria with their tests."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"rules.json is not valid JSON: {error}") from None
    _check_keys(data, TOP_KEYS, "rules.json")
    for key in ("load_inputs", "ai_trap"):
        _check_type(data.get(key, []), list, key, "rules.json")
    criteria_data = _require(data, "criteria", "rules.json")
    _check_type(criteria_data, list, "criteria", "rules.json")
    criteria = [
        _build_criterion(item, number, has_solution)
        for number, item in enumerate(criteria_data, 1)
    ]
    names = [criterion["name"] for criterion in criteria]
    for name in names:
        if names.count(name) > 1:
            raise ValueError(f"rules.json: two criteria are called '{name}'")
    return {
        "title": str(data.get("title") or ""),
        "load_inputs": [str(answer) for answer in data.get("load_inputs", [])],
        "ai_trap": [str(word) for word in data.get("ai_trap", [])],
        "criteria": criteria,
    }


def load_rules(path: str, has_solution: bool) -> dict:
    with open(path, encoding="utf-8-sig") as file:
        return parse_rules(file.read(), has_solution)
