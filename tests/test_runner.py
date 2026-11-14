"""Tests for runner.py: the process that applies the tests to a file."""

import json
import os
import subprocess
import sys
import unittest

import runner
from tests.helpers import REPO, TempDirTestCase


class RunTestTest(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.solution = self.load("def dobro(x):\n    return 2 * x\n",
                                  name="solucao.py")

    def run_one(self, source: str, name: str, params: dict) -> dict:
        student = self.load(source)
        return runner.run_test({"name": name, "params": params}, student,
                               self.solution)

    def test_passing_test(self) -> None:
        result = self.run_one("def dobro(x):\n    return x + x\n", "returns",
                              {"function": "dobro", "args": [3]})
        self.assertEqual(result, {"ok": True, "failures": []})

    def test_failed_check_becomes_a_message(self) -> None:
        result = self.run_one("x = 1\n", "returns",
                              {"function": "dobro", "args": [3]})
        self.assertEqual(result, {"ok": False, "failures": [
            {"message": "função dobro não encontrada"}]})

    def test_rules_error_becomes_a_message(self) -> None:
        result = self.run_one("def triplo(x):\n    return 3 * x\n",
                              "returns", {"function": "triplo", "args": [1]})
        self.assertIn("erro na solução de referência",
                      result["failures"][0]["message"])

    def test_unexpected_error_names_the_student_line(self) -> None:
        source = ("class Mau:\n"
                  "    def __repr__(self):\n"
                  "        raise RuntimeError('repr')\n"
                  "\n"
                  "\n"
                  "def dobro(x):\n"
                  "    return Mau()\n")
        result = self.run_one(source, "returns",
                              {"function": "dobro", "args": [1]})
        self.assertEqual(result["failures"],
                         [{"message": "erro RuntimeError: repr (linha 3)"}])

    def test_tuple_params_are_decoded(self) -> None:
        source = "def dobro(x):\n    return isinstance(x, tuple)\n"
        result = self.run_one(source, "returns",
                              {"function": "dobro",
                               "args": [{"$tuple": [1]}], "expected": True})
        self.assertTrue(result["ok"])


class MainTest(TempDirTestCase):
    def run_job(self, job: dict) -> dict:
        job_file = self.write("job.json", json.dumps(job))
        result_file = os.path.join(self.root, "result.json")
        command = [sys.executable, "-I", os.path.join(REPO, "runner.py"),
                   job_file, result_file]
        subprocess.run(command, check=True, timeout=60, cwd=self.root)
        with open(result_file, encoding="utf-8") as file:
            return json.load(file)

    def test_writes_the_results(self) -> None:
        student = self.write("aluno.py", "def dobro(x):\n    return 2 * x\n"
                                         "\nnome = input()\n")
        solution = self.write("solucao.py", "def dobro(x):\n    return x * 2\n")
        result = self.run_job({
            "student": student, "solution": solution, "load_inputs": ["Ana"],
            "tests": [
                {"name": "returns", "params": {"function": "dobro",
                                               "args": [2]}},
                {"name": "defines", "params": {"function": "metade"}},
            ]})
        self.assertEqual(result["load"], {"ok": True, "error": None})
        self.assertEqual([item["ok"] for item in result["results"]],
                         [True, False])

    def test_without_solution_and_with_a_load_error(self) -> None:
        student = self.write("aluno.py", "def dobro(x):\n    return 2 * x\n"
                                         "\n\nx = 1 / 0\n")
        result = self.run_job({
            "student": student, "solution": None, "load_inputs": [],
            "tests": [{"name": "returns",
                       "params": {"function": "dobro", "args": [2],
                                  "expected": 4}}]})
        self.assertEqual(result["load"], {
            "ok": False,
            "error": "ZeroDivisionError: division by zero (linha 5)"})
        self.assertTrue(result["results"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
