"""Tests for sandbox.py: running student code inside the runner."""

import builtins
import sys
import unittest

import sandbox
from tests.helpers import TempDirTestCase


class RunTest(unittest.TestCase):
    def test_captures_output_and_return_value(self) -> None:
        def program() -> int:
            print("olá")
            return 42

        outcome = sandbox.run(program, [])
        self.assertEqual(outcome.returned, 42)
        self.assertEqual(outcome.output, "olá\n")
        self.assertIsNone(outcome.error)
        self.assertFalse(outcome.asked_more)

    def test_answers_input_and_keeps_the_prompt(self) -> None:
        outcome = sandbox.run(lambda: input("Nome: ") + input(), ["Ana", 7])
        self.assertEqual(outcome.returned, "Ana7")
        self.assertEqual(outcome.output, "Nome: \n\n")

    def test_running_out_of_inputs_stops_quietly(self) -> None:
        outcome = sandbox.run(lambda: input("a? ") + input("b? "), ["x"])
        self.assertTrue(outcome.asked_more)
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.output, "a? \nb? ")

    def test_exception_is_captured(self) -> None:
        outcome = sandbox.run(lambda: 1 / 0, [])
        self.assertIsInstance(outcome.error, ZeroDivisionError)

    def test_exit_without_code_or_zero_is_not_an_error(self) -> None:
        self.assertIsNone(sandbox.run(lambda: sys.exit(), []).error)
        self.assertIsNone(sandbox.run(lambda: sys.exit(0), []).error)

    def test_exit_with_another_code_is_an_error(self) -> None:
        outcome = sandbox.run(lambda: sys.exit(2), [])
        self.assertIsInstance(outcome.error, SystemExit)

    def test_too_much_output_stops_the_code(self) -> None:
        def endless() -> None:
            while True:
                print("x" * 1000)

        outcome = sandbox.run(endless, [])
        self.assertIsInstance(outcome.error, sandbox.TooMuchOutput)
        self.assertLessEqual(len(outcome.output), sandbox.OUTPUT_LIMIT)

    def test_input_and_stdout_are_restored(self) -> None:
        real_input, real_stdout = builtins.input, sys.stdout
        sandbox.run(lambda: 1 / 0, [])
        self.assertIs(builtins.input, real_input)
        self.assertIs(sys.stdout, real_stdout)


class LoadTest(TempDirTestCase):
    def test_keeps_the_functions_of_the_file(self) -> None:
        submission = self.load("def dobro(x):\n    return 2 * x\n")
        self.assertIsNone(submission.error)
        self.assertIsNotNone(submission.code)
        self.assertEqual(submission.namespace["dobro"](4), 8)

    def test_answers_input_while_loading(self) -> None:
        submission = self.load("nome = input()\n", ["Ana"])
        self.assertEqual(submission.namespace["nome"], "Ana")

    def test_runs_as_main(self) -> None:
        source = "if __name__ == '__main__':\n    corrido = True\n"
        self.assertTrue(self.load(source).namespace["corrido"])

    def test_syntax_error_has_no_code(self) -> None:
        submission = self.load("x = 1\ndef f(:\n    pass\n")
        self.assertIsNone(submission.code)
        self.assertIsInstance(submission.error, SyntaxError)
        message = sandbox.describe_error(submission.error, submission.path)
        self.assertTrue(message.startswith("SyntaxError: "))
        self.assertTrue(message.endswith("(linha 2)"))

    def test_runtime_error_keeps_what_was_defined_before(self) -> None:
        submission = self.load("def f():\n    return 1\n\n\nx = 1 / 0\n")
        self.assertIsInstance(submission.error, ZeroDivisionError)
        self.assertIn("f", submission.namespace)
        self.assertEqual(
            sandbox.describe_error(submission.error, submission.path),
            "ZeroDivisionError: division by zero (linha 5)")

    def test_utf8_with_bom_loads(self) -> None:
        path = self.write("bom.py", "﻿nome = 'João'\n".encode("utf-8"))
        submission = sandbox.load(path, [])
        self.assertIsNone(submission.error)
        self.assertEqual(submission.namespace["nome"], "João")

    def test_latin1_file_loads(self) -> None:
        path = self.write("latin.py", "nome = 'João'\n".encode("latin-1"))
        self.assertEqual(sandbox.load(path, []).namespace["nome"], "João")

    def test_null_bytes_count_as_a_syntax_error(self) -> None:
        submission = sandbox.load(self.write("nulo.py", b"x = 1\x00\n"), [])
        self.assertIsNone(submission.code)
        self.assertIsInstance(submission.error, SyntaxError)

    def test_empty_submission_has_no_file(self) -> None:
        submission = sandbox.empty_submission()
        self.assertIsNone(submission.path)
        self.assertIsNone(submission.code)
        self.assertNotIn("dobro", submission.namespace)


class DescribeErrorTest(unittest.TestCase):
    def test_error_without_a_line(self) -> None:
        self.assertEqual(sandbox.describe_error(ValueError("x"), "a.py"),
                         "ValueError: x")

    def test_too_much_output(self) -> None:
        self.assertEqual(
            sandbox.describe_error(sandbox.TooMuchOutput(), None),
            "saída demasiado longa (possível ciclo infinito)")


if __name__ == "__main__":
    unittest.main()
