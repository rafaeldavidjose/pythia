"""Tests for the reports in engine.py: Markdown, plain text and export."""

import io
import os
import unittest
import zipfile

import engine
from tests.helpers import ProjectTestCase

EXERCISE = {"id": "Exercise_1", "title": "Gestão de notas"}


def sample_record() -> dict:
    criteria = [
        {"name": "mostrar", "points": 2, "auto": 0, "passed": 0, "total": 1,
         "hint": "Siga o formato do enunciado.", "review": False,
         "tests": [
             {"label": "mostrar('Ana', 15)", "ok": False, "ran": True,
              "failures": [{"message": "saída diferente da esperada",
                            "expected_output": "Ana: 15",
                            "actual_output": "Ana 15"}]},
         ]},
        {"name": "media", "points": 4, "auto": 2.75, "passed": 1, "total": 2,
         "hint": "", "review": False,
         "tests": [
             {"label": "media([10])", "ok": True, "ran": True,
              "failures": []},
             {"label": "media([])", "ok": False, "ran": True,
              "failures": [{"message": "erro ZeroDivisionError: "
                                       "division by zero (linha 2)"}],
              "hint": "Uma lista vazia tem média 0."},
         ]},
    ]
    evaluation = {"load": {"ok": True, "error": None}, "criteria": criteria,
                  "ai_trap": [], "date": "2026-11-14 10:00"}
    return {"id": "20000001", "number": "20000001", "name": "Ana Silva",
            "file": "Exercise_1_20000001.py",
            "evaluation": evaluation, "grades": {"mostrar": 0, "media": 2.75},
            "comments": {"media": "Falta o caso da lista vazia."},
            "notes": "Entregue fora do prazo.", "finalized": False}


class GradeTextTest(unittest.TestCase):
    def test_portuguese_notation(self) -> None:
        self.assertEqual(engine.grade_text(14.5), "14,5")
        self.assertEqual(engine.grade_text(20), "20")
        self.assertEqual(engine.grade_text(9.25), "9,25")
        self.assertEqual(engine.grade_text(1 / 3), "0,33")
        self.assertEqual(engine.grade_text(None), "-")

    def test_report_name(self) -> None:
        record = {"number": "20000001", "name": "João  Sá"}
        self.assertEqual(engine.report_name("Exercise_1", record),
                         "Exercise_1_20000001_Joao_Sa")


class ReportMarkdownTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record = sample_record()

    def report(self) -> str:
        return engine.report_md(EXERCISE, self.record)

    def lines(self) -> list[str]:
        return self.report().splitlines()

    def test_header_has_only_exercise_student_and_grade(self) -> None:
        self.assertEqual(self.lines()[:6], [
            "# Relatório de avaliação", "",
            "- Exercício: Exercise_1",
            "- Aluno: Ana Silva (20000001)",
            "- Nota: 2,75 / 6",
            "",
        ])

    def test_criterion_fields(self) -> None:
        lines = self.lines()
        self.assertIn("## media", lines)
        self.assertIn("- Nota: 2,75 / 4", lines)
        self.assertIn("- Testes OK: 1 / 2", lines)

    def test_every_test_is_listed_with_its_result(self) -> None:
        lines = self.lines()
        self.assertIn("  - `mostrar('Ana', 15)`: FALHOU", lines)
        self.assertIn("  - `media([10])`: OK", lines)
        self.assertIn("  - `media([])`: FALHOU", lines)

    def test_failure_details_go_under_the_test(self) -> None:
        report = self.report()
        self.assertIn("  - `media([])`: FALHOU\n"
                      "    - erro ZeroDivisionError: division by zero "
                      "(linha 2)\n"
                      "    - Explicação: Uma lista vazia tem média 0.\n",
                      report)

    def test_expected_and_obtained_output(self) -> None:
        report = self.report()
        self.assertIn("    - Esperado:\n      ```\n      Ana: 15\n      ```",
                      report)
        self.assertIn("    - Obtido:\n      ```\n      Ana 15\n      ```",
                      report)

    def test_hint_comment_and_notes(self) -> None:
        lines = self.lines()
        self.assertIn("- Explicação: Siga o formato do enunciado.", lines)
        self.assertIn("- Comentário: Falta o caso da lista vazia.", lines)
        self.assertIn("## Observações", lines)
        self.assertIn("Entregue fora do prazo.", lines)

    def test_teacher_grade_replaces_the_automatic_one(self) -> None:
        self.record["grades"]["media"] = 4
        lines = self.lines()
        self.assertIn("- Nota: 4 / 4", lines)
        self.assertIn("- Nota: 4 / 6", lines)

    def test_load_error_and_tests_not_run(self) -> None:
        self.record["evaluation"]["load"] = {
            "ok": False, "error": "SyntaxError: invalid syntax (linha 3)"}
        test = self.record["evaluation"]["criteria"][1]["tests"][0]
        test.update(ok=False, ran=False)
        lines = self.lines()
        self.assertIn("- Erro: SyntaxError: invalid syntax (linha 3)", lines)
        self.assertIn("  - `media([10])`: NÃO CORREU", lines)

    def test_weight_is_shown_when_it_is_not_one(self) -> None:
        test = self.record["evaluation"]["criteria"][1]["tests"][0]
        test["weight"] = 0.5
        self.assertIn("  - `media([10])`: OK (peso 0,5)", self.lines())

    def test_student_without_number(self) -> None:
        self.record["number"] = ""
        self.assertIn("- Aluno: Ana Silva", self.lines())

    def test_no_date_tables_or_prose(self) -> None:
        report = self.report()
        for text in ("Data:", "Ficheiro:", "|", "automaticamente", "**",
                     chr(0xB7), chr(0x2014)):
            self.assertNotIn(text, report)


class ReportTextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = engine.report_text(EXERCISE, sample_record())

    def test_no_markdown(self) -> None:
        for markup in ("```", "`", "# "):
            self.assertNotIn(markup, self.text)
        self.assertTrue(self.text.startswith("Relatório de avaliação\n"))

    def test_same_lines_without_marks(self) -> None:
        lines = self.text.splitlines()
        self.assertIn("  - media([]): FALHOU", lines)
        self.assertIn("media", lines)

    def test_output_blocks_keep_their_lines(self) -> None:
        self.assertIn("    - Obtido:\n      Ana 15\n", self.text)


class ExportTest(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.copy_example()
        graded = sample_record()
        waiting = {**sample_record(), "id": "20000002",
                   "number": "20000002", "name": "Bruno Costa",
                   "evaluation": None}
        engine.save_state("Exercise_1", {"students": {
            "20000001": graded, "20000002": waiting}})

    def test_writes_markdown_reports_grades_and_a_zip(self) -> None:
        data, folder, count = engine.export_reports(
            "Exercise_1", ["20000001", "20000002"])
        self.assertEqual(count, 1)
        names = ["Exercise_1_20000001_Ana_Silva.md", "Exercise_1_notas.csv"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(sorted(archive.namelist()), names)
            report = archive.read(names[0]).decode("utf-8")
            grades = archive.read(names[1]).decode("utf-8-sig")
        self.assertEqual(sorted(os.listdir(folder)), names)
        self.assertTrue(report.startswith("# Relatório de avaliação"))
        self.assertEqual(grades.splitlines(),
                         ["Número;Nome;Nota;Finalizado",
                          "20000001;Ana Silva;2,75;não"])


if __name__ == "__main__":
    unittest.main()
