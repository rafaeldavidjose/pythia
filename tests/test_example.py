"""
The example in the repository: Exercise_1, the example roster and the five
submissions in examples/entrega1. Each submission shows one case: a copy of
the solution, a valid alternative, typical mistakes, a syntax error and an
infinite loop.
"""

import json
import os
import unittest

import checks
import engine
from tests.helpers import EXAMPLE_EXERCISE, EXAMPLE_SUBMISSIONS, ProjectTestCase

# Final grade and whether the teacher should look at it, by student number
EXPECTED = {
    "20000001": (20, False),
    "20000002": (20, False),
    "20000003": (9.25, True),
    "20000004": (0, True),
    "20000005": (16.25, True),
}


class ExampleTest(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.copy_example()

    def test_rules_use_every_check(self) -> None:
        path = os.path.join(EXAMPLE_EXERCISE, "rules.json")
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        used = {test["name"] for criterion in data["criteria"]
                for test in criterion["tests"]}
        self.assertEqual(used, set(checks.available()))

    def test_solution_passes_its_own_rules(self) -> None:
        result = engine.validate_exercise("Exercise_1")
        self.assertTrue(result["ok"], result["messages"])

    def test_grades_of_the_sample_submissions(self) -> None:
        files = engine.read_folder(EXAMPLE_SUBMISSIONS)
        result = engine.import_submissions("Exercise_1", files)
        self.assertEqual(result["unrecognized"], [])
        engine.grade_students("Exercise_1",
                              engine.select_students("Exercise_1"))
        students = engine.load_state("Exercise_1")["students"]
        grades = {
            student_id: (engine.final_grade(record),
                         engine.needs_review(record))
            for student_id, record in students.items()
        }
        self.assertEqual(grades, EXPECTED)

        syntax_error = students["20000004"]["evaluation"]
        self.assertTrue(syntax_error["load"]["error"].startswith(
            "SyntaxError"))
        self.assertFalse(any(test["ran"]
                             for criterion in syntax_error["criteria"]
                             for test in criterion["tests"]))

        loop = students["20000005"]["evaluation"]["criteria"]
        counting = next(criterion for criterion in loop
                        if criterion["name"] == "contar_aprovados")
        timed_out = [any(failure.get("timeout")
                         for failure in test["failures"])
                     for test in counting["tests"]]
        self.assertEqual(timed_out, [False, True, False, True])


if __name__ == "__main__":
    unittest.main()
