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
            "class": "1", "file": "Exercise_1_20000001.py",
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

    def test_header(self) -> None:
        lines = self.report().splitlines()
        self.assertEqual(lines[0], "# Relatório de avaliação automática")
        self.assertIn("**Exercício:** Exercise_1 · Gestão de notas", lines)
        self.assertIn("**Aluno:** Ana Silva (20000001)", lines)
        self.assertIn("**Ficheiro:** Exercise_1_20000001.py", lines)
        self.assertIn("**Nota:** 2,75 / 6", lines)
        self.assertIn("**Testes certos:** 1/3", lines)
        self.assertIn("| media | 1/2 | 2,75 / 4 |", lines)

    def test_every_test_is_listed_with_its_result(self) -> None:
        lines = self.report().splitlines()
        self.assertIn("- [falhou] Teste 1: mostrar('Ana', 15)", lines)
        self.assertIn("- [passou] Teste 1: media([10])", lines)
        self.assertIn("- [falhou] Teste 2: media([])", lines)
        self.assertIn("  - erro ZeroDivisionError: division by zero "
                      "(linha 2)", lines)
        self.assertIn("  - Sugestão: Uma lista vazia tem média 0.", lines)
        self.assertIn("Testes certos: 1/2.", lines)

    def test_expected_and_obtained_output(self) -> None:
        report = self.report()
        self.assertIn("    Esperado:\n    ```\n    Ana: 15\n    ```", report)
        self.assertIn("    Obtido:\n    ```\n    Ana 15\n    ```", report)

    def test_hint_comment_and_notes(self) -> None:
        lines = self.report().splitlines()
        self.assertIn("Sugestão: Siga o formato do enunciado.", lines)
        self.assertIn("Comentário: Falta o caso da lista vazia.", lines)
        self.assertIn("## Observações", lines)
        self.assertIn("Entregue fora do prazo.", lines)

    def test_teacher_grade_replaces_the_automatic_one(self) -> None:
        self.record["grades"]["media"] = 4
        report = self.report()
        self.assertIn("### media · 4 / 4", report)
        self.assertIn("**Nota:** 4 / 6", report)

    def test_syntax_error_and_tests_not_run(self) -> None:
        self.record["evaluation"]["load"] = {
            "ok": False, "error": "SyntaxError: invalid syntax (linha 3)"}
        test = self.record["evaluation"]["criteria"][1]["tests"][0]
        test.update(ok=False, ran=False)
        report = self.report()
        self.assertIn("O ficheiro não corre: SyntaxError: invalid syntax "
                      "(linha 3). Nenhum teste pôde ser executado.", report)
        self.assertIn("- [não executado] Teste 1: media([10])", report)

    def test_runtime_error(self) -> None:
        self.record["evaluation"]["load"] = {
            "ok": False, "error": "NameError: x (linha 9)"}
        self.assertIn("Erro ao executar o ficheiro: NameError: x (linha 9).",
                      self.report())

    def test_no_long_dash(self) -> None:
        self.assertNotIn("\u2014", self.report())


class ReportTextTest(unittest.TestCase):
    def test_plain_text_for_moodle(self) -> None:
        text = engine.report_text(EXERCISE, sample_record())
        for markup in ("**", "```", "|---", "# "):
            self.assertNotIn(markup, text)
        self.assertIn("media  1/2  2,75 / 4", text)
        self.assertTrue(text.startswith("Relatório de avaliação automática"))

    def test_blank_line_before_the_next_criterion(self) -> None:
        text = engine.report_text(EXERCISE, sample_record())
        self.assertIn("    Ana 15\n\nSugestão: Siga o formato", text)
        self.assertIn("\n\nmedia · 2,75 / 4\n", text)


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

    def test_writes_every_format_and_a_zip(self) -> None:
        data, folder, count = engine.export_reports(
            "Exercise_1", ["20000001", "20000002"], ["md", "pdf", "txt"])
        self.assertEqual(count, 1)
        base = "Exercise_1_20000001_Ana_Silva"
        names = [base + ".md", base + ".pdf", base + ".txt",
                 "Exercise_1_notas.csv"]
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(sorted(archive.namelist()), sorted(names))
            grades = archive.read("Exercise_1_notas.csv").decode("utf-8-sig")
        self.assertEqual(sorted(os.listdir(folder)), sorted(names))
        self.assertEqual(grades.splitlines(),
                         ["Número;Nome;Turma;Nota;Finalizado",
                          "20000001;Ana Silva;1;2,75;não"])

    def test_only_the_chosen_formats(self) -> None:
        data, _, _ = engine.export_reports("Exercise_1", ["20000001"], ["md"])
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(sorted(archive.namelist()),
                             ["Exercise_1_20000001_Ana_Silva.md",
                              "Exercise_1_notas.csv"])


if __name__ == "__main__":
    unittest.main()
