"""
The checks a test in rules.json can use, in the style of egrader plugins.

Each check is a function named check_<name>. It gets the student's and the
solution's submission and the test's params as keyword arguments, and
returns the problems it found: an empty list means the test passed. The
first line of the docstring is the description shown by "pythia.py checks".
A new check is just a new function here.

Messages go into the student reports, so they are in Portuguese.
"""

import copy
import inspect
import json
import unicodedata
from typing import Any, Callable

from sandbox import Outcome, Submission, describe_error, new_namespace, run

PREFIX = "check_"


class _NotGiven:
    def __repr__(self) -> str:
        return "(from solution.py)"


NOT_GIVEN: Any = _NotGiven()


class Failed(Exception):
    """The student's code could not be tested: missing function or error."""


class RulesError(Exception):
    """The test cannot work as written, for example the solution fails."""


# Comparing values and output
def normalize(text: Any) -> str:
    """Lower case, no accents and single spaces."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def normalized_lines(text: str) -> list[str]:
    """Output lines ignoring case, accents and all whitespace."""
    lines = ["".join(normalize(line).split()) for line in text.splitlines()]
    return [line for line in lines if line]


def _normalized_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_normalized_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalized_value(item) for key, item in value.items()}
    if isinstance(value, float):
        return round(value, 6)
    return value


def same(left: Any, right: Any) -> bool:
    """Compare values, treating tuples and lists as equivalent."""
    if isinstance(left, bool) or isinstance(right, bool):
        both_bool = isinstance(left, bool) and isinstance(right, bool)
        return both_bool and left == right
    try:
        return _normalized_value(left) == _normalized_value(right)
    except Exception:
        return False


def show(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 120 else text[:117] + "..."


def _is_grid(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(row, list) for row in value)


def differences(actual: Any, expected: Any, name: str) -> str:
    """Describe which cells of two grids (lists of lists) differ."""
    if not (_is_grid(actual) and _is_grid(expected)
            and len(actual) == len(expected)):
        return f"{name} = {show(actual)}, esperado {show(expected)}"
    cells = []
    for y, expected_row in enumerate(expected):
        if len(actual[y]) != len(expected_row):
            return f"{name}[{y}] tem um tamanho diferente do esperado"
        for x, expected_cell in enumerate(expected_row):
            if not same(actual[y][x], expected_cell):
                cells.append(f"{name}[{y}][{x}] = {show(actual[y][x])}, "
                             f"esperado {show(expected_cell)}")
    if not cells:
        return f"{name} = {show(actual)}, esperado {show(expected)}"
    return "; ".join(cells[:3]) + ("; ..." if len(cells) > 3 else "")


def decode(value: Any) -> Any:
    """Turn {"$tuple": [...]} from JSON into a real tuple, at any depth."""
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$tuple"}:
            return tuple(decode(item) for item in value["$tuple"])
        return {key: decode(item) for key, item in value.items()}
    return value


# Running the student's code
def _failure(message: str, expected_output: str | None = None,
             actual_output: str | None = None) -> dict:
    failure = {"message": message}
    if expected_output is not None:
        failure["expected_output"] = expected_output
        failure["actual_output"] = actual_output
    return failure


def _phrase_failures(output: str, contains: list | tuple,
                     excludes: list | tuple) -> list[dict]:
    failures = []
    for phrase in contains:
        if normalize(phrase) not in normalize(output):
            failures.append(_failure(f'a saída não contém "{phrase}"'))
    for phrase in excludes:
        if normalize(phrase) in normalize(output):
            failures.append(_failure(f'a saída contém "{phrase}" (não devia)'))
    return failures


def _call(submission: Submission, function: str, args: list | tuple,
          inputs: list | tuple) -> tuple[Outcome, list]:
    """Call a function of the submission with a copy of the arguments."""
    func = submission.namespace.get(function)
    if not callable(func):
        raise Failed(f"função {function} não encontrada")
    call_args = copy.deepcopy(list(args))
    outcome = run(lambda: func(*call_args), inputs)
    if outcome.error is not None:
        raise Failed(f"erro {describe_error(outcome.error, submission.path)}")
    if outcome.asked_more:
        raise Failed("pediu mais entradas (input) do que as do teste")
    return outcome, call_args


def _call_solution(solution: Submission, function: str, args: list | tuple,
                   inputs: list | tuple) -> tuple[Outcome, list]:
    try:
        return _call(solution, function, args, inputs)
    except Failed as failed:
        raise RulesError(f"erro na solução de referência: {failed}") from None


def _argument_name(names: dict | None, position: int) -> str:
    return (names or {}).get(str(position), f"argumento {position + 1}")


# Checks
def check_returns(
    student: Submission,
    solution: Submission,
    function: str,
    args: list | tuple = (),
    expected: Any = NOT_GIVEN,
    inputs: list | tuple = (),
    names: dict | None = None,
) -> list[dict]:
    """Call a function and compare the value it returns."""
    outcome, _ = _call(student, function, args, inputs)
    if expected is NOT_GIVEN:
        expected = _call_solution(solution, function, args, inputs)[0].returned
    if same(outcome.returned, expected):
        return []
    message = f"esperado {show(expected)}, obtido {show(outcome.returned)}"
    return [_failure(message)]


def check_prints(
    student: Submission,
    solution: Submission,
    function: str,
    args: list | tuple = (),
    expected: Any = NOT_GIVEN,
    contains: list | tuple = (),
    excludes: list | tuple = (),
    inputs: list | tuple = (),
    names: dict | None = None,
) -> list[dict]:
    """Call a function and check what it prints."""
    outcome, _ = _call(student, function, args, inputs)
    failures = _phrase_failures(outcome.output, contains, excludes)
    if expected is NOT_GIVEN and (contains or excludes):
        return failures
    if expected is NOT_GIVEN:
        expected = _call_solution(solution, function, args, inputs)[0].output
    expected = str(expected)
    if normalized_lines(outcome.output) != normalized_lines(expected):
        failures.insert(0, _failure("saída diferente da esperada",
                                    expected.rstrip(),
                                    outcome.output.rstrip() or "(sem saída)"))
    return failures


def check_mutates(
    student: Submission,
    solution: Submission,
    function: str,
    args: list | tuple,
    position: int = 0,
    expected: Any = NOT_GIVEN,
    inputs: list | tuple = (),
    names: dict | None = None,
) -> list[dict]:
    """Call a function and compare one of its arguments after the call."""
    if not 0 <= position < len(args):
        raise RulesError(f"position {position} não existe em args")
    _, student_args = _call(student, function, args, inputs)
    if expected is NOT_GIVEN:
        expected = _call_solution(solution, function, args, inputs)[1][position]
    actual = student_args[position]
    if same(actual, expected):
        return []
    change = differences(actual, expected, _argument_name(names, position))
    return [_failure(f"depois da chamada, {change}")]


def check_call(
    student: Submission,
    solution: Submission,
    function: str,
    args: list | tuple = (),
    expected: Any = NOT_GIVEN,
    check_return: bool = True,
    same_output: bool = False,
    contains: list | tuple = (),
    excludes: list | tuple = (),
    mutates: list | tuple = (),
    inputs: list | tuple = (),
    names: dict | None = None,
) -> list[dict]:
    """Call a function and check its value, output and arguments at once."""
    outcome, student_args = _call(student, function, args, inputs)
    reference: list = []

    def from_solution() -> tuple[Outcome, list]:
        if not reference:
            reference.append(_call_solution(solution, function, args, inputs))
        return reference[0]

    failures = []
    if check_return:
        if expected is NOT_GIVEN:
            expected = from_solution()[0].returned
        if not same(outcome.returned, expected):
            failures.append(_failure(f"esperado {show(expected)}, "
                                     f"obtido {show(outcome.returned)}"))
    if same_output:
        expected_output = from_solution()[0].output
        if (normalized_lines(outcome.output)
                != normalized_lines(expected_output)):
            failures.append(_failure(
                "saída diferente da esperada", expected_output.rstrip(),
                outcome.output.rstrip() or "(sem saída)"))
    failures += _phrase_failures(outcome.output, contains, excludes)
    for position in mutates:
        wanted = from_solution()[1][position]
        if not same(student_args[position], wanted):
            change = differences(student_args[position], wanted,
                                 _argument_name(names, position))
            failures.append(_failure(f"depois da chamada, {change}"))
    return failures


def check_program(
    student: Submission,
    solution: Submission,
    inputs: list | tuple = (),
    contains: list | tuple = (),
    excludes: list | tuple = (),
    must_finish: bool = True,
) -> list[dict]:
    """Run the whole file with answers to input() and check the output."""
    if student.code is None:
        raise Failed("o ficheiro não corre")
    namespace = new_namespace(student.path)
    outcome = run(lambda: exec(student.code, namespace), inputs)
    failures = []
    if outcome.error is not None:
        error = describe_error(outcome.error, student.path)
        failures.append(_failure(f"erro {error}"))
    if must_finish and outcome.asked_more:
        failures.append(_failure("o programa não terminou "
                                 "(pediu mais entradas)"))
    return failures + _phrase_failures(outcome.output, contains, excludes)


def check_defines(
    student: Submission, solution: Submission, function: str
) -> list[dict]:
    """Check that the file defines a function with this name."""
    if callable(student.namespace.get(function)):
        return []
    return [_failure(f"função {function} não encontrada")]


# Information about the checks, for rules.py and the command line
def available() -> dict[str, Callable[..., list[dict]]]:
    """Every check by name, in the order they are defined."""
    return {
        name[len(PREFIX):]: value for name, value in globals().items()
        if name.startswith(PREFIX) and callable(value)
    }


def parameters(name: str) -> list[inspect.Parameter]:
    """The params a check takes (without student and solution)."""
    signature = inspect.signature(available()[name])
    return list(signature.parameters.values())[2:]


def summary(name: str) -> str:
    """First line of the check's docstring."""
    return (inspect.getdoc(available()[name]) or "").split("\n")[0]


def describe_parameters(name: str) -> list[str]:
    """Params as text: required ones bare, optional ones with the default."""
    described = []
    for parameter in parameters(name):
        default = parameter.default
        if default is inspect.Parameter.empty:
            described.append(parameter.name)
        elif default is NOT_GIVEN:
            described.append(f"{parameter.name}=(from solution.py)")
        elif default is None:
            described.append(f"{parameter.name}=(none)")
        else:
            value = list(default) if isinstance(default, tuple) else default
            described.append(f"{parameter.name}={json.dumps(value)}")
    return described


def needs_solution(name: str, params: dict) -> bool:
    """True when the test compares with solution.py for lack of expected."""
    if name == "call":
        compares_return = (params.get("check_return", True)
                           and "expected" not in params)
        return bool(compares_return or params.get("same_output")
                    or params.get("mutates"))
    if "expected" in params:
        return False
    if name == "prints":
        return not (params.get("contains") or params.get("excludes"))
    return name in ("returns", "mutates")


def _show_argument(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 40 else "[...]"


def default_label(name: str, params: dict) -> str:
    """Label shown in the report when the test has none, e.g. media([10])."""
    if name == "program":
        inputs = [str(answer) for answer in params.get("inputs", [])]
        if not inputs:
            return "programa sem entradas"
        return f"programa com as entradas {', '.join(inputs)}"
    if name == "defines":
        return f"função {params['function']} definida"
    names = params.get("names") or {}
    shown = [
        names.get(str(position), _show_argument(arg))
        for position, arg in enumerate(params.get("args", []))
    ]
    call = f"{params['function']}({', '.join(shown)})"
    # One call can have several tests, so say what each one looks at
    if name == "prints":
        return f"{call}: saída"
    if name == "mutates":
        argument = _argument_name(names, params.get("position", 0))
        return f"{call}: {argument} depois da chamada"
    return call
