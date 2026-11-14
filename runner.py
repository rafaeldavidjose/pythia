"""
Runs a student's file in a separate process and applies the tests to it.
Called by the engine:  python runner.py job.pkl result.json

Messages produced here end up in the student reports, so they are written in
Portuguese and kept short and factual.
"""

import builtins
import copy
import io
import json
import pickle
import sys
import unicodedata
from types import CodeType
from typing import Any, Callable

OUTPUT_LIMIT = 200000


class OutOfInputs(BaseException):
    """The program asked for more inputs than the test provides."""


class TooMuchOutput(BaseException):
    """The program printed too much text, probably in an infinite loop."""


class LimitedOutput(io.StringIO):
    def write(self, text: str) -> int:
        if self.tell() + len(text) > OUTPUT_LIMIT:
            raise TooMuchOutput()
        return super().write(text)


def normalize(text: Any) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def normalized_lines(text: str) -> list[str]:
    """Output lines ignoring case, accents and all whitespace."""
    lines = ["".join(normalize(line).split()) for line in text.splitlines()]
    return [line for line in lines if line]


def normalized_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [normalized_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized_value(item) for key, item in value.items()}
    if isinstance(value, float):
        return round(value, 6)
    return value


def same(left: Any, right: Any) -> bool:
    """Compare values, treating tuples and lists as equivalent."""
    if isinstance(left, bool) or isinstance(right, bool):
        both_bool = isinstance(left, bool) and isinstance(right, bool)
        return both_bool and left == right
    try:
        return normalized_value(left) == normalized_value(right)
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


def describe_error(error: BaseException, filename: str) -> str:
    """Short error message with the line in the student's file, if any."""
    line = None
    trace = error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == filename:
            line = trace.tb_lineno
        trace = trace.tb_next
    if isinstance(error, SyntaxError):
        line = error.lineno or line
        text = f"SyntaxError: {error.msg}"
    elif isinstance(error, TooMuchOutput):
        text = "saída demasiado longa (possível ciclo infinito)"
    else:
        text = f"{type(error).__name__}: {error}"
    return f"{text} (linha {line})" if line else text


def run(
    func: Callable[[], Any], inputs: list[str]
) -> tuple[Any, str, BaseException | None, bool]:
    """Run func() with input() reading from `inputs` and stdout captured."""
    queue = list(inputs)
    output = LimitedOutput()
    asked_more = False

    def fake_input(prompt: object = "") -> str:
        nonlocal asked_more
        output.write(str(prompt))
        if not queue:
            asked_more = True
            raise OutOfInputs()
        output.write("\n")
        return queue.pop(0)

    real_input, real_stdout = builtins.input, sys.stdout
    builtins.input, sys.stdout = fake_input, output
    result = None
    error = None
    try:
        result = func()
    except OutOfInputs:
        pass
    except KeyboardInterrupt:
        raise
    except BaseException as caught:  # student code may raise anything
        error = caught
    finally:
        builtins.input, sys.stdout = real_input, real_stdout
    return result, output.getvalue(), error, asked_more


def _new_namespace(filename: str) -> dict:
    return {"__name__": "__main__", "__file__": filename,
            "__builtins__": builtins}


def load(
    filename: str, inputs: list[str]
) -> tuple[dict, CodeType | None, BaseException | None]:
    """Execute the file and return its namespace and compiled code."""
    with open(filename, "rb") as file:
        raw = file.read()
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        source = raw.decode("latin-1")
    namespace = _new_namespace(filename)
    try:
        code = compile(source, filename, "exec")
    except SyntaxError as error:
        return namespace, None, error
    _, _, error, _ = run(lambda: exec(code, namespace), inputs)
    return namespace, code, error


def failure(
    message: str,
    expected_output: str | None = None,
    actual_output: str | None = None,
) -> dict:
    item = {"message": message}
    if expected_output is not None:
        item["expected_output"] = expected_output
        item["actual_output"] = actual_output
    return item


def _result(failures: list[dict]) -> dict:
    return {"ok": not failures, "failures": failures}


def _phrase_failures(label: str, output: str, contains: list[str],
                     excludes: list[str]) -> list[dict]:
    failures = []
    for phrase in contains:
        if normalize(phrase) not in normalize(output):
            failures.append(
                failure(f'{label}: a saída não contém "{phrase}"'))
    for phrase in excludes:
        if normalize(phrase) in normalize(output):
            failures.append(
                failure(f'{label}: a saída contém "{phrase}" (não devia)'))
    return failures


def test_call(
    test: dict, student_ns: dict, solution_ns: dict, student_file: str
) -> dict:
    label = test["label"]
    student_func = student_ns.get(test["func"])
    if not callable(student_func):
        return _result([failure(f"função {test['func']} não encontrada")])

    student_args = copy.deepcopy(test["args"])
    returned, output, error, _ = run(
        lambda: student_func(*student_args), test["inputs"])
    if error is not None:
        message = f"{label}: erro {describe_error(error, student_file)}"
        return _result([failure(message)])

    solution_func = solution_ns.get(test["func"])
    expected_return, expected_output, solution_args = None, "", None
    if callable(solution_func):
        solution_args = copy.deepcopy(test["args"])
        expected_return, expected_output, _, _ = run(
            lambda: solution_func(*solution_args), test["inputs"])

    failures = []
    if test["check_return"]:
        expected = test["expected"] if test["has_expected"] else expected_return
        if not same(returned, expected):
            failures.append(failure(
                f"{label}: esperado {show(expected)}, obtido {show(returned)}"))
    if (test["output"] == "equal"
            and normalized_lines(output) != normalized_lines(expected_output)):
        failures.append(failure(f"{label}: saída diferente da esperada",
                                expected_output.rstrip(),
                                output.rstrip() or "(sem saída)"))
    failures += _phrase_failures(label, output, test["output_contains"],
                                 test["output_excludes"])
    for index in test["mutates"]:
        if solution_args is None:
            continue
        if not same(student_args[index], solution_args[index]):
            change = differences(student_args[index], solution_args[index],
                                 test["arg_names"][index])
            failures.append(failure(f"{label}: depois da chamada, {change}"))
    return _result(failures)


def test_program(
    test: dict, code: CodeType | None, student_file: str
) -> dict:
    label = test["label"]
    if code is None:
        return _result([failure(f"{label}: o ficheiro não corre")])
    namespace = _new_namespace(student_file)
    _, output, error, asked_more = run(
        lambda: exec(code, namespace), test["inputs"])
    failures = []
    if error is not None:
        message = f"{label}: erro {describe_error(error, student_file)}"
        failures.append(failure(message))
    if test["must_finish"] and asked_more:
        failures.append(failure(
            f"{label}: o programa não terminou (pediu mais entradas)"))
    failures += _phrase_failures(label, output, test["contains"],
                                 test["excludes"])
    return _result(failures)


def main() -> None:
    job_file, result_file = sys.argv[1], sys.argv[2]
    with open(job_file, "rb") as file:
        job = pickle.load(file)
    sys.setrecursionlimit(3000)
    student_file = job["student"]
    solution_ns, _, _ = load(job["solution"], job["load_inputs"])
    student_ns, code, load_error = load(student_file, job["load_inputs"])

    load_info = {"ok": load_error is None and code is not None, "error": None}
    if load_error is not None:
        load_info["error"] = describe_error(load_error, student_file)

    results = []
    for test in job["tests"]:
        try:
            if test["kind"] == "call":
                result = test_call(test, student_ns, solution_ns,
                                   student_file)
            else:
                result = test_program(test, code, student_file)
        except KeyboardInterrupt:
            raise
        except BaseException as error:
            message = (f"{test.get('label', 'teste')}: erro "
                       f"{describe_error(error, student_file)}")
            result = _result([failure(message)])
        results.append(result)

    with open(result_file, "w", encoding="utf-8") as file:
        json.dump({"load": load_info, "results": results}, file,
                  ensure_ascii=False)


if __name__ == "__main__":
    main()
