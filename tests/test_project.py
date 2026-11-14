"""Checks on the repository itself: style rules, docs and launchers."""

import argparse
import ast
import json
import os
import subprocess
import unittest

import checks
import pythia
from tests.helpers import REPO

SKIP_FOLDERS = {".git", "data", "submissions", "__pycache__"}
TEXT_FILES = (".py", ".html", ".md", ".json", ".csv", ".bat", ".command",
              ".yml", ".txt")


def _all_files() -> list[str]:
    """The files in the repository, leaving out local and ignored ones."""
    try:
        command = ["git", "ls-files", "--cached", "--others",
                   "--exclude-standard"]
        listed = subprocess.run(command, cwd=REPO, check=True,
                                capture_output=True, text=True).stdout
        return [os.path.join(REPO, *line.split("/"))
                for line in listed.splitlines()]
    except (OSError, subprocess.CalledProcessError):
        found = []
        for folder, folders, names in os.walk(REPO):
            folders[:] = [name for name in folders
                          if name not in SKIP_FOLDERS]
            found += [os.path.join(folder, name) for name in names]
        return found


def repo_files(*extensions: str) -> list[str]:
    return sorted(path for path in _all_files()
                  if path.endswith(extensions) and os.path.exists(path))


def read(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        return file.read()


class StyleTest(unittest.TestCase):
    def test_no_long_dash_anywhere(self) -> None:
        with_dash = [os.path.relpath(path, REPO)
                     for path in repo_files(*TEXT_FILES)
                     if "\u2014" in read(path)]
        self.assertEqual(with_dash, [])

    def test_python_lines_fit_in_80_characters(self) -> None:
        long_lines = [
            f"{os.path.relpath(path, REPO)}:{number}"
            for path in repo_files(".py")
            for number, line in enumerate(read(path).splitlines(), 1)
            if len(line) > 80
        ]
        self.assertEqual(long_lines, [])

    def test_every_module_has_a_docstring(self) -> None:
        for path in repo_files(".py"):
            if os.sep + "examples" + os.sep in path:
                continue
            if os.sep + "exercises" + os.sep in path:
                continue
            with self.subTest(path=os.path.relpath(path, REPO)):
                self.assertTrue(ast.get_docstring(ast.parse(read(path))))

    def test_json_files_are_valid(self) -> None:
        for path in repo_files(".json"):
            with self.subTest(path=os.path.relpath(path, REPO)):
                json.loads(read(path))


class DocsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = read(os.path.join(REPO, "README.md"))

    def test_readme_documents_every_check_and_param(self) -> None:
        for name in checks.available():
            self.assertIn(f"`{name}`", self.readme)
            for parameter in checks.parameters(name):
                self.assertIn(f"`{parameter.name}`", self.readme, name)

    def test_readme_shows_every_command(self) -> None:
        parser = pythia.build_parser()
        commands = next(action for action in parser._actions
                        if isinstance(action, argparse._SubParsersAction))
        for name in commands.choices:
            self.assertIn(f"python pythia.py {name}", self.readme)

    def test_launchers_start_pythia(self) -> None:
        for name in ("start.bat", "start.command"):
            self.assertIn("pythia.py", read(os.path.join(REPO, name)))


if __name__ == "__main__":
    unittest.main()
