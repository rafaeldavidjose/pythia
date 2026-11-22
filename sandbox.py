"""
Runs code from a submission inside the runner process: answers to input(),
captured output with a size limit, and short error messages that point at
the line in the student's file.
"""

import builtins
import io
import sys
from dataclasses import dataclass, field
from types import CodeType
from typing import Any, Callable

OUTPUT_LIMIT = 200000


class OutOfInputs(BaseException):
    """The program asked for more inputs than the test provides."""


class TooMuchOutput(BaseException):
    """The program printed too much text, probably in an infinite loop."""


class _LimitedOutput(io.StringIO):
    def write(self, text: str) -> int:
        if self.tell() + len(text) > OUTPUT_LIMIT:
            raise TooMuchOutput()
        return super().write(text)


@dataclass
class Submission:
    """A loaded Python file. path is None when there is no file."""

    path: str | None
    namespace: dict
    code: CodeType | None = None
    error: BaseException | None = None


@dataclass
class Outcome:
    """What happened when a piece of code ran."""

    returned: Any
    output: str
    error: BaseException | None
    asked_more: bool
    answers: list = field(default_factory=list)

    def transcript(self) -> str:
        """The output with each answer to input() written after its prompt,
        as it looks in a terminal."""
        text, start = [], 0
        for position, answer in self.answers:
            text += [self.output[start:position], answer]
            start = position
        text.append(self.output[start:])
        return "".join(text)


def run(func: Callable[[], Any], inputs: list | tuple) -> Outcome:
    """Run func() with input() reading from inputs and stdout captured."""
    queue = [str(answer) for answer in inputs]
    output = _LimitedOutput()
    asked_more = False
    answers: list = []

    def fake_input(prompt: object = "") -> str:
        nonlocal asked_more
        output.write(str(prompt))
        if not queue:
            asked_more = True
            raise OutOfInputs()
        answers.append((output.tell(), queue[0]))
        output.write("\n")
        return queue.pop(0)

    real_input, real_stdout = builtins.input, sys.stdout
    builtins.input, sys.stdout = fake_input, output
    returned = None
    error = None
    try:
        returned = func()
    except OutOfInputs:
        pass
    except SystemExit as caught:
        # exit() or exit(0) is a normal way to end a program
        if caught.code not in (None, 0):
            error = caught
    except KeyboardInterrupt:
        raise
    except BaseException as caught:  # student code may raise anything
        error = caught
    finally:
        builtins.input, sys.stdout = real_input, real_stdout
    return Outcome(returned, output.getvalue(), error, asked_more, answers)


def new_namespace(path: str | None) -> dict:
    return {"__name__": "__main__", "__file__": path,
            "__builtins__": builtins}


def empty_submission() -> Submission:
    """Stands in for solution.py when the exercise has none."""
    return Submission(None, new_namespace(None))


def load(path: str, inputs: list | tuple) -> Submission:
    """Execute the file with these answers to input() and keep its names."""
    with open(path, "rb") as file:
        raw = file.read()
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        source = raw.decode("latin-1")
    namespace = new_namespace(path)
    try:
        code = compile(source, path, "exec")
    except SyntaxError as error:
        return Submission(path, namespace, None, error)
    except ValueError as error:  # null bytes, before Python 3.12
        return Submission(path, namespace, None, SyntaxError(str(error)))
    outcome = run(lambda: exec(code, namespace), inputs)
    return Submission(path, namespace, code, outcome.error)


def describe_error(error: BaseException, path: str | None) -> str:
    """Short error message with the line in the student's file, if any."""
    line = None
    trace = error.__traceback__
    while trace is not None:
        if path and trace.tb_frame.f_code.co_filename == path:
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
