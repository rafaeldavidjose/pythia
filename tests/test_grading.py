"""Tests for grading in engine.py: scores, the runner process and review."""

import os
import time
import unittest
from unittest import mock

import engine
from tests.helpers import DOUBLE_SOLUTION, ProjectTestCase

PASS = {"ok": True, "failures": []}
FAIL = {"ok": False, "failures": [{"message": "esperado 1, obtido 2"}]}


def criterion(points: float, weights: list[float],
              hints: list[str] | None = None, hint: str = "") -> dict:
    hints = hints or [""] * len(weights)
    tests = [{"label": f"t{index}", "weight": weight, "hint": test_hint}
             for index, (weight, test_hint) in enumerate(zip(weights, hints))]
    return {"name": "c", "points": points, "tests": tests, "hint": hint,
            "review": False}


class ScoreCriterionTest(unittest.TestCase):
    def test_grade_follows_the_weights(self) -> None:
        heavy = criterion(4, [1, 3])
        self.assertEqual(engine._score_criterion(heavy, [PASS, FAIL])["auto"],
                         1)
        self.assertEqual(engine._score_criterion(heavy, [FAIL, PASS])["auto"],
                         3)

    def test_grade_is_rounded_to_a_quarter(self) -> None:
        three = criterion(4, [1, 1, 1])
        self.assertEqual(
            engine._score_criterion(three, [PASS, FAIL, FAIL])["auto"], 1.25)
        self.assertEqual(
            engine._score_criterion(three, [PASS, PASS, FAIL])["auto"], 2.75)

    def test_counts_and_test_list(self) -> None:
        scored = engine._score_criterion(criterion(2, [1, 1]),
                                         [PASS, engine.NOT_RUN])
        self.assertEqual((scored["passed"], scored["total"]), (1, 2))
        self.assertEqual(scored["tests"][0],
                         {"label": "t0", "ok": True, "ran": True,
                          "failures": []})
        self.assertFalse(scored["tests"][1]["ran"])

    def test_the_same_hint_is_shown_once(self) -> None:
        same = criterion(2, [1, 1, 1], ["Dica.", "Dica.", "Outra."])
        tests = engine._score_criterion(same, [FAIL, FAIL, FAIL])["tests"]
        self.assertEqual([test.get("hint") for test in tests],
                         ["Dica.", None, "Outra."])

    def test_no_hint_for_tests_that_passed_or_did_not_run(self) -> None:
        hinted = criterion(2, [1, 1], ["Dica.", "Dica."])
        tests = engine._score_criterion(hinted,
                                        [PASS, engine.NOT_RUN])["tests"]
        self.assertNotIn("hint", tests[0])
        self.assertNotIn("hint", tests[1])

    def test_criterion_hint_when_no_test_hint_was_shown(self) -> None:
        general = criterion(2, [1], hint="Rever o enunciado.")
        self.assertEqual(engine._score_criterion(general, [FAIL])["hint"],
                         "Rever o enunciado.")
        self.assertEqual(engine._score_criterion(general, [PASS])["hint"], "")
        with_test_hint = criterion(2, [1], ["Dica."], hint="Geral.")
        self.assertEqual(
            engine._score_criterion(with_test_hint, [FAIL])["hint"], "")

    def test_zero_weight_does_not_divide_by_zero(self) -> None:
        self.assertEqual(
            engine._score_criterion(criterion(2, [0]), [PASS])["auto"], 0)


class EvaluateFileTest(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_double_exercise()
        self.exercise = engine.load_exercise("Dobro")

    def evaluate(self, source: str | None) -> dict:
        path = self.write("aluno.py", source) if source is not None else None
        return engine.evaluate_file(self.exercise, path)

    def statuses(self, evaluation: dict) -> list[tuple[bool, bool]]:
        return [(test["ok"], test["ran"])
                for criterion in evaluation["criteria"]
                for test in criterion["tests"]]

    def test_correct_file(self) -> None:
        evaluation = self.evaluate(DOUBLE_SOLUTION)
        self.assertEqual(evaluation["load"], {"ok": True, "error": None})
        self.assertEqual([criterion["auto"]
                          for criterion in evaluation["criteria"]], [10, 10])

    def test_wrong_answer(self) -> None:
        evaluation = self.evaluate(
            "def dobro(x):\n    return abs(2 * x)\n\nprint(8)\n")
        tests = evaluation["criteria"][0]["tests"]
        self.assertTrue(tests[0]["ok"])
        self.assertEqual(tests[1]["failures"],
                         [{"message": "esperado -6, obtido 6"}])
        self.assertEqual(tests[1]["hint"], "Os negativos também contam.")
        self.assertEqual(evaluation["criteria"][0]["auto"], 5)

    def test_missing_file(self) -> None:
        evaluation = self.evaluate(None)
        self.assertEqual(evaluation["load"]["error"],
                         "nenhum ficheiro .py entregue")
        self.assertEqual(self.statuses(evaluation), [(False, False)] * 3)

    def test_syntax_error_runs_no_test(self) -> None:
        evaluation = self.evaluate("def dobro(x)\n    return 2 * x\n")
        self.assertTrue(evaluation["load"]["error"].startswith("SyntaxError"))
        self.assertEqual(self.statuses(evaluation), [(False, False)] * 3)

    def test_endless_function_only_fails_its_test(self) -> None:
        source = ("def dobro(x):\n"
                  "    while x < 0:\n"
                  "        pass\n"
                  "    return 2 * x\n"
                  "\n"
                  "print(dobro(int(input())))\n")
        evaluation = self.evaluate(source)
        tests = [test for criterion in evaluation["criteria"]
                 for test in criterion["tests"]]
        self.assertEqual([test["ok"] for test in tests], [True, False, True])
        self.assertTrue(tests[1]["failures"][0]["timeout"])
        self.assertIn("possível ciclo infinito",
                      tests[1]["failures"][0]["message"])
        record = {"evaluation": evaluation}
        self.assertTrue(engine.needs_review(record))

    def test_endless_load_is_reported_once(self) -> None:
        start = time.monotonic()
        evaluation = self.evaluate("while True:\n    pass\n")
        elapsed = time.monotonic() - start
        self.assertIn("não terminou ao ser carregado",
                      evaluation["load"]["error"])
        self.assertEqual(self.statuses(evaluation), [(False, False)] * 3)
        limit = engine.STUDENT_TIMEOUT + engine.TEST_TIMEOUT + 5
        self.assertLess(elapsed, limit)

    def test_process_that_dies(self) -> None:
        evaluation = self.evaluate("import os\nos._exit(3)\n")
        self.assertEqual(evaluation["load"]["error"],
                         "o programa terminou de forma inesperada")
        self.assertFalse(any(ok for ok, _ in self.statuses(evaluation)))

    def test_ai_trap_is_only_a_warning(self) -> None:
        self.exercise["ai_trap"] = ["palavra_secreta"]
        source = DOUBLE_SOLUTION + "# palavra_secreta\n"
        evaluation = self.evaluate(source)
        self.assertEqual(evaluation["ai_trap"],
                         [{"word": "palavra_secreta", "line": 6,
                           "text": "# palavra_secreta"}])
        self.assertEqual([criterion["auto"]
                          for criterion in evaluation["criteria"]], [10, 10])


class WithoutSolutionTest(ProjectTestCase):
    def test_expected_values_and_tuples(self) -> None:
        rules = {"criteria": [{"criterion": "tuplos", "points": 2, "tests": [
            {"name": "returns",
             "params": {"function": "e_tuplo", "args": [{"$tuple": [1, 2]}],
                        "expected": True}},
            {"name": "returns",
             "params": {"function": "e_tuplo", "args": [[1, 2]],
                        "expected": False}},
        ]}]}
        self.add_exercise("Tuplos", rules)
        exercise = engine.load_exercise("Tuplos")
        self.assertIsNone(exercise["solution"])
        path = self.write("aluno.py",
                          "def e_tuplo(x):\n    return isinstance(x, tuple)\n")
        evaluation = engine.evaluate_file(exercise, path)
        self.assertEqual(evaluation["criteria"][0]["auto"], 2)


class RecordTest(unittest.TestCase):
    def record(self) -> dict:
        evaluation = {"load": {"ok": True, "error": None}, "criteria": [
            {"name": "a", "points": 4, "auto": 3, "tests": []},
            {"name": "b", "points": 6, "auto": 1.5, "tests": []},
        ]}
        return {"evaluation": evaluation, "grades": {"a": 1},
                "comments": {"a": "x"}, "finalized": True}

    def test_apply_evaluation_resets_the_review(self) -> None:
        record = self.record()
        engine.apply_evaluation(record, record["evaluation"])
        self.assertEqual(record["grades"], {"a": 3, "b": 1.5})
        self.assertEqual(record["comments"], {})
        self.assertFalse(record["finalized"])

    def test_final_grade_uses_the_teacher_grade(self) -> None:
        record = self.record()
        self.assertEqual(engine.final_grade(record), 2.5)
        self.assertEqual(engine.criterion_grade(
            record, record["evaluation"]["criteria"][1]), 1.5)
        self.assertIsNone(engine.final_grade({"evaluation": None}))

    def test_needs_review(self) -> None:
        record = self.record()
        self.assertFalse(engine.needs_review(record))
        self.assertFalse(engine.needs_review({}))
        record["evaluation"]["load"]["ok"] = False
        self.assertTrue(engine.needs_review(record))


class GradeStudentsTest(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_double_exercise()
        folder = self.moodle_folder("Ana Silva", "20000001", DOUBLE_SOLUTION)
        self.moodle_folder("Bruno Costa", "20000002", "x = 1\n", "100002")
        engine.import_submissions("Dobro", engine.read_folder(folder))

    def test_select_students(self) -> None:
        self.assertEqual(sorted(engine.select_students("Dobro")),
                         ["20000001", "20000002"])
        state = engine.load_state("Dobro")
        state["students"]["20000001"]["evaluation"] = {"criteria": []}
        state["students"]["20000002"]["finalized"] = True
        engine.save_state("Dobro", state)
        self.assertEqual(engine.select_students("Dobro"), [])
        self.assertEqual(engine.select_students("Dobro", regrade=True),
                         ["20000001"])
        self.assertEqual(engine.select_students(
            "Dobro", ["20000002", "20000001", "nobody"]), ["20000001"])

    def test_grade_students_saves_each_result(self) -> None:
        progress = []
        engine.grade_students("Dobro", ["20000001", "20000002"],
                              lambda student, ok: progress.append(ok))
        self.assertEqual(progress, [True, True])
        students = engine.load_state("Dobro")["students"]
        self.assertEqual(engine.final_grade(students["20000001"]), 20)
        self.assertEqual(engine.final_grade(students["20000002"]), 0)

    def test_a_failure_is_reported_and_the_rest_go_on(self) -> None:
        progress = []
        with mock.patch.object(engine, "evaluate_student",
                               side_effect=RuntimeError("boom")), \
                mock.patch("traceback.print_exception"):
            engine.grade_students("Dobro", ["20000001"],
                                  lambda student, ok: progress.append(ok))
        self.assertEqual(progress, [False])


class ExercisesTest(ProjectTestCase):
    def test_list_exercises(self) -> None:
        self.add_double_exercise()
        self.add_exercise("Partido", '{"criteria": [}')
        os.makedirs(os.path.join(self.exercises_dir, "Vazio"))
        os.makedirs(os.path.join(self.exercises_dir, "_rascunho"))
        listed = {item["id"]: item for item in engine.list_exercises()}
        self.assertEqual(sorted(listed), ["Dobro", "Partido", "Vazio"])
        self.assertIsNone(listed["Dobro"]["error"])
        self.assertEqual(listed["Dobro"]["total"], 20)
        self.assertEqual(listed["Dobro"]["criteria"][0]["tests"], 2)
        self.assertIn("not valid JSON", listed["Partido"]["error"])
        self.assertIn("rules.json is missing", listed["Vazio"]["error"])

    def test_missing_exercise(self) -> None:
        with self.assertRaisesRegex(ValueError, "Exercise 'Nada' not found"):
            engine.load_exercise("Nada")

    def test_save_exercise(self) -> None:
        ex_id = engine.save_exercise("Exercício 2", "x = 1\n", "{}")
        self.assertEqual(ex_id, "Exercicio_2")
        folder = os.path.join(self.exercises_dir, ex_id)
        self.assertEqual(sorted(os.listdir(folder)),
                         ["rules.json", "solution.py"])
        engine.save_exercise("Exercício 2", None, '{"criteria": []}')
        with open(os.path.join(folder, "solution.py"),
                  encoding="utf-8") as file:
            self.assertEqual(file.read(), "x = 1\n")

    def test_validate_good_and_bad_rules(self) -> None:
        self.add_double_exercise()
        result = engine.validate_exercise("Dobro")
        self.assertTrue(result["ok"], result["messages"])
        self.assertIn("solution.py passes 3 of 3 tests.", result["messages"])

        wrong = {"criteria": [{"criterion": "dobro", "points": 20, "tests": [
            {"name": "returns",
             "params": {"function": "dobro", "args": [2], "expected": 5}},
        ]}]}
        self.add_exercise("Errado", wrong, DOUBLE_SOLUTION)
        result = engine.validate_exercise("Errado")
        self.assertFalse(result["ok"])
        self.assertIn("dobro, test 1 (dobro(2)): esperado 5, obtido 4",
                      result["messages"])

    def test_validate_without_solution_or_rules(self) -> None:
        rules = {"criteria": [{"criterion": "c", "points": 1, "tests": [
            {"name": "program", "params": {"contains": ["x"]}}]}]}
        self.add_exercise("SoRegras", rules)
        result = engine.validate_exercise("SoRegras")
        self.assertTrue(result["ok"])
        self.assertIn("only the rules", result["messages"][-1])
        self.assertFalse(engine.validate_exercise("Nada")["ok"])


if __name__ == "__main__":
    unittest.main()
