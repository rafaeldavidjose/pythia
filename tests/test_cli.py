"""Tests for pythia.py, the command line."""

import contextlib
import io
import os
import unittest
from unittest import mock

import checks
import pythia
from tests.helpers import DOUBLE_SOLUTION, ProjectTestCase


class CliTestCase(ProjectTestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pythia.main(list(args))
        return code, out.getvalue(), err.getvalue()


class ChecksCommandTest(CliTestCase):
    def test_lists_every_check_with_its_params(self) -> None:
        code, out, _ = self.run_cli("checks")
        self.assertEqual(code, 0)
        for name in checks.available():
            self.assertIn(f"{name}\n    {checks.summary(name)}\n", out)
        self.assertIn("params: function, args=[], "
                      "expected=(from solution.py)", out)


class ValidateCommandTest(CliTestCase):
    def test_valid_exercise(self) -> None:
        self.add_double_exercise()
        code, out, _ = self.run_cli("validate", "Dobro")
        self.assertEqual(code, 0)
        self.assertIn("solution.py passes 3 of 3 tests.", out)

    def test_broken_rules(self) -> None:
        self.add_exercise("Partido", '{"criteria": 1}', DOUBLE_SOLUTION)
        code, out, _ = self.run_cli("validate", "Partido")
        self.assertEqual(code, 1)
        self.assertIn("'criteria' must be a list", out)

    def test_unknown_exercise(self) -> None:
        code, out, _ = self.run_cli("validate", "Nada")
        self.assertEqual(code, 1)
        self.assertIn("Exercise 'Nada' not found", out)


class GradingCommandsTest(CliTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_double_exercise()
        self.folder = self.moodle_folder("Ana Silva", "20000001",
                                         DOUBLE_SOLUTION)
        self.moodle_folder("Bruno Costa", "20000002",
                           "def dobro(x):\n    return x\n", "100002")

    def test_import_assess_and_report(self) -> None:
        self.assertEqual(self.run_cli("import", "Dobro", self.folder),
                         (0, "2 added, 0 updated.\n", ""))

        code, out, _ = self.run_cli("assess", "Dobro")
        self.assertEqual(code, 0)
        self.assertEqual(out.count(" graded\n"), 2)
        self.assertIn("[2/2] ", out)
        self.assertEqual(self.run_cli("assess", "Dobro")[1],
                         "No students to grade.\n")
        out = self.run_cli("assess", "Dobro", "--regrade",
                           "--ids", "20000002")[1]
        self.assertEqual(out, "[1/1] 20000002 graded\n")

        lines = self.run_cli("report", "Dobro")[1].splitlines()
        self.assertEqual([line.split() for line in lines], [
            ["Number", "Name", "Grade", "Tests", "Status"],
            ["20000001", "Ana", "Silva", "20", "3/3", "graded"],
            ["20000002", "Bruno", "Costa", "0", "0/3", "graded"],
        ])

        out = self.run_cli("report", "Dobro", "--export", "md,txt")[1]
        self.assertIn("2 reports written to ", out)
        reports = os.listdir(os.path.join(self.data_dir, "Dobro", "reports"))
        self.assertIn("Dobro_20000001_Ana_Silva.txt", reports)
        self.assertNotIn("Dobro_20000001_Ana_Silva.pdf", reports)

    def test_report_before_grading(self) -> None:
        self.run_cli("import", "Dobro", self.folder)
        lines = self.run_cli("report", "Dobro")[1].splitlines()
        self.assertEqual(lines[1].split(),
                         ["20000001", "Ana", "Silva", "-", "-", "not",
                          "graded"])

    def test_unknown_student_is_listed_on_import(self) -> None:
        self.moodle_folder("Zé Ninguém", "", "x = 1\n", "100009")
        out = self.run_cli("import", "Dobro", self.folder)[1]
        self.assertIn("Not found in students.csv: Zé Ninguém_100009_", out)

    def test_errors(self) -> None:
        code, _, err = self.run_cli("import", "Nada", self.folder)
        self.assertEqual(code, 1)
        self.assertIn("error: Exercise 'Nada' not found", err)
        err = self.run_cli("import", "Dobro",
                           os.path.join(self.root, "nada"))[2]
        self.assertIn("error: Folder not found", err)
        self.assertEqual(self.run_cli("assess", "Nada")[0], 1)
        self.assertEqual(self.run_cli("report", "Nada")[0], 1)


class ParserTest(unittest.TestCase):
    def test_no_command_starts_the_web_interface(self) -> None:
        args = pythia.build_parser().parse_args([])
        self.assertIs(args.func, pythia.command_serve)
        self.assertFalse(args.no_browser)

    def test_serve_options(self) -> None:
        with mock.patch("server.serve") as serve:
            code = pythia.main(["serve", "--port", "9001", "--no-browser"])
        self.assertEqual(code, 0)
        serve.assert_called_once_with(9001, False)


if __name__ == "__main__":
    unittest.main()
