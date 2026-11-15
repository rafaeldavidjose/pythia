"""Tests for the import side of engine.py: roster, names and submissions."""

import io
import os
import unittest
import zipfile

import engine
from tests.helpers import EXAMPLE_SUBMISSIONS, ProjectTestCase

STUDENTS = [
    {"number": "20000001", "name": "Ana Silva"},
    {"number": "20000002", "name": "Ana Costa"},
    {"number": "20000003", "name": "Rui Sá"},
]


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class RosterTest(ProjectTestCase):
    def test_example_roster(self) -> None:
        students = engine.load_students()
        self.assertEqual(len(students), 5)
        self.assertEqual(students[0], {"number": "20000001",
                                       "name": "Ana Silva"})

    def test_comma_separated_rows_and_missing_parts(self) -> None:
        self.write("students.csv", "number,name,class\n"
                                   "a20000009,Rui Sá\n"
                                   "sem número,Eva\n"
                                   "\n"
                                   "20000010,Ivo Reis,2\n")
        self.assertEqual(engine.load_students(), [
            {"number": "20000009", "name": "Rui Sá"},
            {"number": "20000010", "name": "Ivo Reis"},
        ])

    def test_alphabetical_order_ignores_accents_and_case(self) -> None:
        records = [{"name": "Zé Lopes"}, {"name": "bruno Reis"},
                   {"name": "Álvaro Dias"}]
        self.assertEqual([record["name"]
                          for record in sorted(records, key=engine.name_order)],
                         ["Álvaro Dias", "bruno Reis", "Zé Lopes"])

    def test_no_roster(self) -> None:
        os.remove(self.students_file)
        self.assertEqual(engine.load_students(), [])


class FindStudentTest(unittest.TestCase):
    def test_by_number(self) -> None:
        self.assertEqual(engine.find_student(STUDENTS, "20000002")["name"],
                         "Ana Costa")

    def test_full_moodle_name_matches_the_short_name(self) -> None:
        found = engine.find_student(STUDENTS, None, "Ana Maria da Silva")
        self.assertEqual(found["number"], "20000001")

    def test_accents_are_ignored(self) -> None:
        found = engine.find_student(STUDENTS, None, "rui sa")
        self.assertEqual(found["number"], "20000003")

    def test_no_match_or_ambiguous(self) -> None:
        self.assertIsNone(engine.find_student(STUDENTS, None, "Eva Rocha"))
        twins = STUDENTS + [{"number": "9", "name": "Ana Silva"}]
        self.assertIsNone(engine.find_student(twins, None, "Ana Silva"))
        self.assertIsNone(engine.find_student(STUDENTS, None, ""))


class IdentifyTest(unittest.TestCase):
    def test_moodle_folder_wins_over_the_number_in_the_file(self) -> None:
        group = {"folder": "Ana Silva_100001_assignsubmission_file",
                 "files": [("Dobro_20000002.py", b"")]}
        ident = engine.identify(group, STUDENTS)
        self.assertEqual(ident["number"], "20000001")
        self.assertTrue(ident["recognized"])
        self.assertIn("(20000002) belongs to someone else", ident["warning"])

    def test_unknown_student(self) -> None:
        group = {"folder": "Eva Rocha_100005_assignsubmission_file",
                 "files": [("Dobro_20000005.py", b"")]}
        ident = engine.identify(group, STUDENTS)
        self.assertEqual((ident["name"], ident["number"]),
                         ("Eva Rocha", "20000005"))
        self.assertFalse(ident["recognized"])

    def test_loose_file_found_by_number(self) -> None:
        group = {"folder": "", "files": [("FP_Dobro_20000003.py", b"")]}
        ident = engine.identify(group, STUDENTS)
        self.assertEqual(ident["name"], "Rui Sá")
        self.assertTrue(ident["recognized"])


class GroupSubmissionsTest(unittest.TestCase):
    def test_moodle_layout(self) -> None:
        groups = engine.group_submissions([
            ("entrega/Ana Silva_1_assignsubmission_file/a.py", b"1"),
            ("entrega/Ana Silva_1_assignsubmission_file/b.py", b"2"),
            ("entrega/Rui Sá_2_assignsubmission_file/c.py", b"3"),
        ])
        self.assertEqual(
            sorted((group["folder"], len(group["files"]))
                   for group in groups.values()),
            [("Ana Silva_1_assignsubmission_file", 2),
             ("Rui Sá_2_assignsubmission_file", 1)])

    def test_one_student_folder_imported_directly(self) -> None:
        groups = engine.group_submissions([
            ("Ana Silva_1_assignsubmission_file/a.py", b"1"),
            ("Ana Silva_1_assignsubmission_file/b.py", b"2"),
        ])
        self.assertEqual(len(groups), 1)

    def test_loose_files_are_one_student_each(self) -> None:
        groups = engine.group_submissions([("pasta/a.py", b"1"),
                                           ("pasta/b.py", b"2")])
        self.assertEqual(sorted(groups), ["pasta/a.py", "pasta/b.py"])
        self.assertTrue(all(group["folder"] == ""
                            for group in groups.values()))

    def test_zips_are_opened_at_any_depth(self) -> None:
        inner = zip_bytes({"codigo.py": "x = 1"})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Ana Silva_1_assignsubmission_file/a.py", "1")
            archive.writestr("Rui Sá_2_assignsubmission_file/projeto.zip",
                             inner)
        groups = engine.group_submissions([("moodle.zip", buffer.getvalue())])
        files = sorted(name for group in groups.values()
                       for name, _ in group["files"])
        self.assertEqual(files, ["a.py", "codigo.py"])

    def test_broken_zip_is_skipped(self) -> None:
        self.assertEqual(engine.group_submissions([("x.zip", b"nope")]), {})

    def test_other_files_are_ignored(self) -> None:
        groups = engine.group_submissions([
            ("e/A_1_assignsubmission_file/a.py", b"1"),
            ("e/A_1_assignsubmission_file/notas.txt", b"2"),
            ("e/__MACOSX/A_1_assignsubmission_file/._a.py", b"3"),
            ("e/A_1_assignsubmission_file/.oculto.py", b"4"),
        ])
        self.assertEqual([name for group in groups.values()
                          for name, _ in group["files"]], ["a.py"])

    def test_moodle_folder_without_python_file(self) -> None:
        groups = engine.group_submissions([
            ("e/A_1_assignsubmission_file/FP_Avaliacao_1_20000001", b""),
            ("e/B_2_assignsubmission_file/b.py", b"2"),
            ("e/B_2_assignsubmission_file/notas.txt", b""),
            ("e/leia-me.txt", b""),
        ])
        self.assertEqual(groups["e/A_1_assignsubmission_file"], {
            "folder": "A_1_assignsubmission_file", "files": [],
            "other": ["FP_Avaliacao_1_20000001"]})
        self.assertEqual(groups["e/B_2_assignsubmission_file"]["other"],
                         ["notas.txt"])
        self.assertEqual(len(groups), 2)

    def test_windows_paths(self) -> None:
        groups = engine.group_submissions([
            ("e\\A_1_assignsubmission_file\\a.py", b"1"),
            ("e\\B_2_assignsubmission_file\\b.py", b"2"),
        ])
        self.assertEqual(len(groups), 2)


class PickFileTest(unittest.TestCase):
    def test_prefers_the_exercise_and_the_number(self) -> None:
        names = ["rascunho.py", "Dobro_1.py", "Dobro_20000001.py"]
        self.assertEqual(engine.pick_file(names, "Dobro", "20000001"),
                         "Dobro_20000001.py")
        self.assertEqual(engine.pick_file(["b.py", "a.py"], "Dobro", ""),
                         "a.py")
        self.assertIsNone(engine.pick_file([], "Dobro", ""))


class ReadFolderTest(ProjectTestCase):
    def test_reads_py_and_zip_files_under_the_folder_name(self) -> None:
        self.write("entrega/A_1_assignsubmission_file/a.py", "x = 1")
        self.write("entrega/b.zip", zip_bytes({"b.py": "y = 2"}))
        self.write("entrega/leia-me.txt", "nada")
        files = dict(engine.read_folder(os.path.join(self.root, "entrega")))
        self.assertEqual(sorted(files),
                         ["entrega/A_1_assignsubmission_file/a.py",
                          "entrega/b.zip", "entrega/leia-me.txt"])
        self.assertEqual(files["entrega/A_1_assignsubmission_file/a.py"],
                         b"x = 1")
        self.assertEqual(files["entrega/leia-me.txt"], b"")

    def test_missing_or_empty_folder(self) -> None:
        with self.assertRaisesRegex(ValueError, "Folder not found"):
            engine.read_folder(os.path.join(self.root, "nada"))
        os.makedirs(os.path.join(self.root, "vazia"))
        with self.assertRaisesRegex(ValueError, "No files in"):
            engine.read_folder(os.path.join(self.root, "vazia"))


class ImportSubmissionsTest(ProjectTestCase):
    def test_import_the_example_twice(self) -> None:
        files = engine.read_folder(EXAMPLE_SUBMISSIONS)
        result = engine.import_submissions("Exercise_1", files)
        self.assertEqual(result, {"added": 5, "updated": 0,
                                  "unrecognized": []})
        record = engine.load_state("Exercise_1")["students"]["20000002"]
        self.assertEqual(record["name"], "Bruno Costa")
        self.assertEqual(record["file"], "Exercise_1_20000002.py")
        self.assertIsNone(record["evaluation"])
        stored = os.path.join(self.data_dir, "Exercise_1", "submissions",
                              "20000002", "Exercise_1_20000002.py")
        self.assertTrue(os.path.exists(stored))

        again = engine.import_submissions("Exercise_1", files)
        self.assertEqual((again["added"], again["updated"]), (0, 5))

    def test_unknown_student_is_reported(self) -> None:
        folder = self.moodle_folder("Zé Ninguém", "", "x = 1")
        result = engine.import_submissions("Dobro",
                                           engine.read_folder(folder))
        self.assertEqual(result["unrecognized"],
                         ["Zé Ninguém_100001_assignsubmission_file"])
        record = next(iter(
            engine.load_state("Dobro")["students"].values()))
        self.assertEqual(record["name"], "Zé Ninguém")
        self.assertTrue(record["id"].startswith("Ze_Ninguem"))

    def test_student_without_python_file_gets_zero(self) -> None:
        self.add_double_exercise()
        self.write("entrega/Ana Silva_1_assignsubmission_file/Dobro_20000001",
                   "print(1)")
        self.write("entrega/Rui Sá_2_assignsubmission_file/main.py", "x = 1")
        result = engine.import_submissions(
            "Dobro", engine.read_folder(os.path.join(self.root, "entrega")))
        self.assertEqual(result["added"], 2)
        record = engine.load_state("Dobro")["students"]["20000001"]
        self.assertIsNone(record["file"])
        self.assertEqual(record["files"], [])
        self.assertEqual(record["warning"], "No .py file was handed in. "
                                            "Files: Dobro_20000001.")
        engine.grade_students("Dobro", ["20000001"])
        record = engine.load_state("Dobro")["students"]["20000001"]
        self.assertEqual(engine.final_grade(record), 0)
        self.assertTrue(engine.needs_review(record))
        self.assertFalse(any(test["ran"]
                             for criterion in record["evaluation"]["criteria"]
                             for test in criterion["tests"]))

    def test_files_with_the_same_name_are_both_kept(self) -> None:
        student = "entrega/Ana Silva_1_assignsubmission_file"
        self.write(f"{student}/v1/main.py", "x = 1")
        self.write(f"{student}/v2/main.py", "x = 2")
        self.write("entrega/Rui Sá_2_assignsubmission_file/main.py", "y = 1")
        result = engine.import_submissions(
            "Dobro", engine.read_folder(os.path.join(self.root, "entrega")))
        self.assertEqual(result["added"], 2)
        record = engine.load_state("Dobro")["students"]["20000001"]
        self.assertEqual(record["files"], ["_main.py", "main.py"])


class StudentFolderTest(unittest.TestCase):
    def test_one_student_folder_with_subfolders(self) -> None:
        groups = engine.group_submissions([
            ("entrega/Ana Silva_1_assignsubmission_file/v1/a.py", b"1"),
            ("entrega/Ana Silva_1_assignsubmission_file/v2/a.py", b"2"),
        ])
        self.assertEqual(list(groups),
                         ["entrega/Ana Silva_1_assignsubmission_file"])
        group = groups["entrega/Ana Silva_1_assignsubmission_file"]
        self.assertEqual(group["folder"], "Ana Silva_1_assignsubmission_file")
        self.assertEqual(len(group["files"]), 2)

    def test_folder_named_after_a_student_number(self) -> None:
        groups = engine.group_submissions([("a20000001/a.py", b"1"),
                                           ("a20000001/b.py", b"2")])
        self.assertEqual(list(groups), ["a20000001"])


if __name__ == "__main__":
    unittest.main()
