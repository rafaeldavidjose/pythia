"""Shared setup: temporary folders, a temporary project and small exercises."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import engine
import sandbox

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_EXERCISE = os.path.join(REPO, "exercises", "Exercise_1")
EXAMPLE_SUBMISSIONS = os.path.join(REPO, "examples", "entrega1")
EXAMPLE_ROSTER = os.path.join(REPO, "students.example.csv")

DOUBLE_SOLUTION = (
    "def dobro(x):\n"
    "    return 2 * x\n"
    "\n"
    "\n"
    "print(dobro(int(input('Número: '))))\n"
)

DOUBLE_RULES = {
    "title": "Dobro",
    "criteria": [
        {"criterion": "dobro", "points": 10, "tests": [
            {"name": "returns", "params": {"function": "dobro", "args": [2]}},
            {"name": "returns", "params": {"function": "dobro", "args": [-3]},
             "hint": "Os negativos também contam."},
        ]},
        {"criterion": "programa", "points": 10, "tests": [
            {"name": "program",
             "params": {"inputs": ["4"], "contains": ["8"]}},
        ]},
    ],
}


class TempDirTestCase(unittest.TestCase):
    """Gives each test an empty temporary folder in self.root."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.root = temp.name
        self.addCleanup(temp.cleanup)

    def write(self, relative: str, content: str | bytes) -> str:
        path = os.path.join(self.root, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(content, bytes):
            with open(path, "wb") as file:
                file.write(content)
        else:
            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
        return path

    def load(self, source: str, inputs: list | tuple = (),
             name: str = "aluno.py") -> sandbox.Submission:
        return sandbox.load(self.write(name, source), inputs)


class ProjectTestCase(TempDirTestCase):
    """Points the engine at temporary exercises/, data/ and students.csv."""

    def setUp(self) -> None:
        super().setUp()
        self.exercises_dir = os.path.join(self.root, "exercises")
        self.data_dir = os.path.join(self.root, "data")
        os.makedirs(self.exercises_dir)
        self.students_file = os.path.join(self.root, "students.csv")
        shutil.copy(EXAMPLE_ROSTER, self.students_file)
        patches = {
            "EXERCISES_DIR": self.exercises_dir,
            "DATA_DIR": self.data_dir,
            "STUDENTS_FILE": self.students_file,
            "STUDENT_TIMEOUT": 6,
            "TEST_TIMEOUT": 2,
        }
        for name, value in patches.items():
            patcher = mock.patch.object(engine, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def add_exercise(self, ex_id: str, rules: dict | str,
                     solution: str | None = None) -> str:
        folder = os.path.join(self.exercises_dir, ex_id)
        os.makedirs(folder, exist_ok=True)
        text = rules if isinstance(rules, str) else json.dumps(rules)
        with open(os.path.join(folder, "rules.json"), "w",
                  encoding="utf-8") as file:
            file.write(text)
        if solution is not None:
            with open(os.path.join(folder, "solution.py"), "w",
                      encoding="utf-8") as file:
                file.write(solution)
        return folder

    def add_double_exercise(self) -> None:
        self.add_exercise("Dobro", DOUBLE_RULES, DOUBLE_SOLUTION)

    def copy_example(self) -> None:
        shutil.copytree(EXAMPLE_EXERCISE,
                        os.path.join(self.exercises_dir, "Exercise_1"))

    def moodle_folder(self, name: str, number: str, source: str,
                      moodle_id: str = "100001",
                      parent: str = "entrega") -> str:
        """Write one student's file the way Moodle downloads it."""
        folder = f"{name}_{moodle_id}_assignsubmission_file"
        self.write(os.path.join(parent, folder, f"Dobro_{number}.py"),
                   source)
        return os.path.join(self.root, parent)
