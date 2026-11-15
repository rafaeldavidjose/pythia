"""
Reads exercises/<id>/rules.json. As in an egrader rules file, every test
names a check and gives its params. The params are checked against the
check's function in checks.py, so a typo is reported with its place in the
file instead of failing silently while grading.

A value used by many tests, like a map, can be written once under "values"
and used as {"$value": "mapa"}. When it is too long to write out in the
report, it shows there as mapa.
"""

import copy
import json
from typing import Any

import checks

TOP_KEYS = {"title", "load_inputs", "ai_trap", "values", "criteria"}
CRITERION_KEYS = {
    "criterion", "points", "description", "hint", "review", "tests",
}
TEST_KEYS = {"name", "params", "weight", "hint", "label"}

PARAM_TYPES = {
    "function": str, "args": list, "inputs": list, "contains": list,
    "excludes": list, "names": dict, "position": int, "must_finish": bool,
    "check_return": bool, "same_output": bool, "mutates": list,
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
    positions = []
    if name == "mutates":
        positions = [params.get("position", 0)]
    elif name == "call":
        positions = params.get("mutates", [])
    for position in positions:
        _check_type(position, int, "position", where)
        if not 0 <= position < len(params.get("args", [])):
            raise ValueError(f"{where}: position {position} is not "
                             f"one of the args")


def _is_reference(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"$value"}


def _resolve(value: Any, values: dict, where: str) -> Any:
    """Replace each {"$value": name} with a copy of that shared value."""
    if isinstance(value, list):
        return [_resolve(item, values, where) for item in value]
    if _is_reference(value):
        if value["$value"] not in values:
            raise ValueError(f"{where}: unknown value '{value['$value']}' "
                             f"(values: {', '.join(values) or 'none'})")
        return copy.deepcopy(values[value["$value"]])
    if isinstance(value, dict):
        return {key: _resolve(item, values, where)
                for key, item in value.items()}
    return value


def _reference_names(written: dict, params: dict) -> dict:
    """
    A shared value too long for the label, like a map, shows by its name.
    Shorter ones are written out, so the report shows the real arguments.
    """
    args = written.get("args")
    if not isinstance(args, list):
        return {}
    return {
        str(position): arg["$value"]
        for position, arg in enumerate(args)
        if _is_reference(arg)
        and not checks.fits_in_label(checks.decode(params["args"][position]))
    }


def _build_test(item: Any, where: str, has_solution: bool,
                values: dict) -> dict:
    _check_keys(item, TEST_KEYS, where)
    name = _require(item, "name", where)
    if name not in checks.available():
        raise ValueError(f"{where}: unknown check '{name}' "
                         f"(checks: {', '.join(checks.available())})")
    written = item.get("params", {})
    _check_type(written, dict, "params", where)
    params = _resolve(written, values, where)
    _check_params(name, params, where)
    accepted = [parameter.name for parameter in checks.parameters(name)]
    names = _reference_names(written, params)
    if names and "names" in accepted:
        params["names"] = {**names, **params.get("names", {})}
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


def _build_criterion(item: Any, number: int, has_solution: bool,
                     values: dict) -> dict:
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
        _build_test(test, f"{where}, test {index}", has_solution, values)
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
    values = data.get("values", {})
    _check_type(values, dict, "values", "rules.json")
    criteria_data = _require(data, "criteria", "rules.json")
    _check_type(criteria_data, list, "criteria", "rules.json")
    criteria = [
        _build_criterion(item, number, has_solution, values)
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
