"""
Grader engine: exercises, importing submissions, evaluation, reports and export.
No language model is involved: grades come only from the tests in
exercises/<id>/rules.json, run by the checks in checks.py.

Everything a student reads (reports, test messages) is in Portuguese.
"""

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import rules

BASE = os.path.dirname(os.path.abspath(__file__))
EXERCISES_DIR = os.path.join(BASE, "exercises")
DATA_DIR = os.path.join(BASE, "data")
RUNNER = os.path.join(BASE, "runner.py")
STUDENTS_FILE = os.path.join(BASE, "students.csv")

STUDENT_TIMEOUT = 10  # seconds for all of a student's tests
TEST_TIMEOUT = 5  # seconds per test, used to isolate an infinite loop
WORKERS = 4  # students graded at the same time

STATE_LOCK = threading.Lock()  # state.json is read and written as a whole
NOT_RUN = {"ok": False, "failures": []}


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", strip_accents(text))
    return text.strip("_") or "student"


def read_text(path: str) -> str:
    with open(path, "rb") as file:
        raw = file.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def write_json(path: str, data: Any) -> None:
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=1)
    os.replace(temp_path, path)


def grade_text(value: float | None) -> str:
    """Grade in Portuguese notation: 14,5 instead of 14.5."""
    if value is None:
        return "-"
    text = ("%.2f" % round(value, 2)).rstrip("0").rstrip(".")
    return text.replace(".", ",")


# Student list (students.csv: number;name, other columns are ignored)
def load_students() -> list[dict]:
    if not os.path.exists(STUDENTS_FILE):
        return []
    text = read_text(STUDENTS_FILE)
    sep = ";" if text.count(";") >= text.count(",") else ","
    students = []
    for row in csv.reader(io.StringIO(text), delimiter=sep):
        if len(row) < 2:
            continue
        number = re.sub(r"\D", "", row[0])
        if not number:
            continue
        students.append({"number": number, "name": row[1].strip()})
    return students


def name_order(record: dict) -> str:
    """Sort key: the name in alphabetical order, ignoring accents."""
    return strip_accents(record["name"]).lower()


NAME_PARTICLES = {"de", "da", "do", "das", "dos", "e"}


def _name_parts(name: str) -> list[str]:
    """Lower-case name parts without accents or particles (de, da, dos...)."""
    words = strip_accents(name).lower().replace("-", " ").split()
    return [word for word in words if word not in NAME_PARTICLES]


def find_student(
    students: list[dict], number: str | None = None, name: str | None = None
) -> dict | None:
    """
    Look up by student number first. Otherwise compare the full name from the
    Moodle folder with the short name in students.csv (first and last name).
    Only a single unambiguous match is accepted.
    """
    if number:
        for student in students:
            if student["number"] == number:
                return student
    target = _name_parts(name or "")
    if not target:
        return None

    def same_names(parts: list[str]) -> bool:
        return set(parts) == set(target)

    def same_first_and_last(parts: list[str]) -> bool:
        return parts[0] == target[0] and parts[-1] == target[-1]

    def same_first_and_contained(parts: list[str]) -> bool:
        return parts[0] == target[0] and set(parts) <= set(target)

    for rule in (same_names, same_first_and_last, same_first_and_contained):
        matches = [
            student for student in students
            if _name_parts(student["name"])
            and rule(_name_parts(student["name"]))
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


# Exercises
def exercise_folder(ex_id: str) -> str:
    folder = os.path.join(EXERCISES_DIR, ex_id)
    if not ex_id or not os.path.isdir(folder):
        raise ValueError(f"Exercise '{ex_id}' not found in {EXERCISES_DIR}")
    return folder


def load_exercise(ex_id: str) -> dict:
    folder = exercise_folder(ex_id)
    solution = os.path.join(folder, "solution.py")
    has_solution = os.path.exists(solution)
    rules_file = os.path.join(folder, "rules.json")
    if not os.path.exists(rules_file):
        raise ValueError(f"{ex_id}: rules.json is missing")
    definition = rules.load_rules(rules_file, has_solution)
    return {
        "id": ex_id,
        "title": definition["title"] or ex_id,
        "load_inputs": definition["load_inputs"],
        "ai_trap": definition["ai_trap"],
        "criteria": definition["criteria"],
        "solution": solution if has_solution else None,
    }


def list_exercises() -> list[dict]:
    result = []
    if not os.path.isdir(EXERCISES_DIR):
        return result
    for ex_id in sorted(os.listdir(EXERCISES_DIR)):
        folder = os.path.join(EXERCISES_DIR, ex_id)
        if not os.path.isdir(folder) or ex_id.startswith((".", "_")):
            continue
        info = {
            "id": ex_id,
            "title": ex_id,
            "error": None,
            "criteria": [],
            "total": 0,
            "ai_trap": [],
            "students": len(load_state(ex_id)["students"]),
        }
        try:
            ex = load_exercise(ex_id)
            info["title"] = ex["title"]
            info["criteria"] = [
                {
                    "name": criterion["name"],
                    "points": criterion["points"],
                    "tests": len(criterion["tests"]),
                    "description": criterion["description"],
                    "review": criterion["review"],
                }
                for criterion in ex["criteria"]
            ]
            info["total"] = sum(
                criterion["points"] for criterion in ex["criteria"])
            info["ai_trap"] = ex["ai_trap"]
        except Exception as error:
            info["error"] = str(error)
        result.append(info)
    return result


def save_exercise(
    ex_id: str, solution: str | None, rules_text: str | None
) -> str:
    """Write the files that were given; the others stay as they were."""
    ex_id = slug(ex_id)
    folder = os.path.join(EXERCISES_DIR, ex_id)
    os.makedirs(folder, exist_ok=True)
    files = {"solution.py": solution, "rules.json": rules_text}
    for filename, content in files.items():
        if content is None:
            continue
        path = os.path.join(folder, filename)
        # Keep the line endings of the uploaded file as they are
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(content)
    return ex_id


# Evaluation state (data/<exercise>/state.json)
def data_dir(ex_id: str) -> str:
    path = os.path.join(DATA_DIR, ex_id)
    os.makedirs(path, exist_ok=True)
    return path


def load_state(ex_id: str) -> dict:
    path = os.path.join(DATA_DIR, ex_id, "state.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    return {"students": {}}


def save_state(ex_id: str, state: dict) -> None:
    write_json(os.path.join(data_dir(ex_id), "state.json"), state)


# Importing submissions
STUDENT_NUMBER = re.compile(r"(?<!\d)a?(\d{8})(?!\d)", re.I)
MOODLE_FOLDER = re.compile(r"^(.+?)_(\d+)_assign", re.I)


def _name_from_folder(folder: str) -> str:
    match = MOODLE_FOLDER.match(folder)
    if match:
        return match.group(1).strip()
    name = STUDENT_NUMBER.sub(" ", folder)
    name = re.sub(r"[_\-]+", " ", name)
    course_words = r"\b(FP|IC|aula|P|avaliacao|exercicios?|projeto)\b"
    name = re.sub(course_words, " ", name, flags=re.I)
    name = re.sub(r"\b\d+\b", " ", name)
    return " ".join(name.split())


def _expand_zips(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Open zips (the Moodle download or zips inside a student's folder)."""
    result = []
    for path, data in files:
        if path.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    inner = [
                        (path[:-4] + "/" + name, archive.read(name))
                        for name in archive.namelist()
                        if not name.endswith("/")
                    ]
                result.extend(_expand_zips(inner))
            except zipfile.BadZipFile:
                pass
        else:
            result.append((path, data))
    return result


def group_submissions(files: list[tuple[str, bytes]]) -> dict[str, dict]:
    """
    Group (path, bytes) pairs by student. Each student is a folder; loose
    files count as one student each. A Moodle folder with no .py file is
    still a student, with the names of what was handed in under "other".
    """
    files = [(path.replace("\\", "/").strip("/"), data)
             for path, data in files]
    handed_in = [
        (path, data) for path, data in _expand_zips(files)
        if "__MACOSX" not in path
        and not os.path.basename(path).startswith(".")
    ]
    py_files = [(path, data) for path, data in handed_in
                if path.lower().endswith(".py")]

    # The common root is the folder that was chosen for import
    folders = [path.split("/")[:-1] for path, _ in py_files]
    root = []
    for parts in zip(*folders):
        if len(set(parts)) != 1:
            break
        root.append(parts[0])
    # When the chosen folder is one student's folder, everything is theirs
    student_root = None
    for index in range(len(root)):
        if MOODLE_FOLDER.match(root[index]):
            student_root = index
            break
    if student_root is None and root and STUDENT_NUMBER.search(root[-1]):
        student_root = len(root) - 1

    groups = {}
    for path, data in py_files:
        parts = path.split("/")
        if student_root is not None:
            key = "/".join(root[:student_root + 1])
            folder = root[student_root]
        elif len(parts) - len(root) > 1:
            key = "/".join(parts[:len(root) + 1])
            folder = parts[len(root)]
        else:
            key = path
            folder = ""
        group = groups.setdefault(key, {"folder": folder, "files": [],
                                        "other": []})
        group["files"].append((os.path.basename(path), data))

    for path, _ in handed_in:
        if path.lower().endswith(".py"):
            continue
        parts = path.split("/")
        for index, part in enumerate(parts[:-1]):
            if MOODLE_FOLDER.match(part):
                key = "/".join(parts[:index + 1])
                group = groups.setdefault(key, {"folder": part, "files": [],
                                                "other": []})
                group["other"].append(os.path.basename(path))
                break
    return groups


def identify(group: dict, students: list[dict]) -> dict:
    folder = group["folder"]
    filenames = [name for name, _ in group["files"]]
    number = None
    for text in filenames + group.get("other", []) + [folder]:
        match = STUDENT_NUMBER.search(text)
        if match:
            number = match.group(1)
            break
    name = _name_from_folder(folder) if folder else ""
    if not name and filenames:
        name = _name_from_folder(os.path.splitext(filenames[0])[0])
    warning = ""
    match = None
    if folder and MOODLE_FOLDER.match(folder):
        # The Moodle folder name comes from the student's account, so it wins
        match = find_student(students, None, name)
        if match and number and number != match["number"]:
            warning = (f"The number in the file name ({number}) belongs to "
                       f"someone else. This student's number is "
                       f"{match['number']}.")
    if match is None:
        match = find_student(students, number, name)
    if match:
        number, name = match["number"], match["name"]
    return {
        "number": number or "",
        "name": name or "(no name)",
        "recognized": match is not None,
        "warning": warning,
    }


def pick_file(names: list[str], ex_id: str, number: str) -> str | None:
    """Prefer files named after the exercise and the student number."""
    if not names:
        return None

    def score(name: str) -> int:
        points = 0
        if ex_id.lower() in name.lower():
            points += 2
        if number and number in name:
            points += 1
        return points

    return sorted(names, key=lambda name: (-score(name), name))[0]


def read_folder(path: str) -> list[tuple[str, bytes]]:
    """Read a folder on disk (e.g. submissions/entrega1) as (path, bytes)."""
    path = os.path.expanduser(path.strip().strip('"'))
    if not os.path.isdir(path):
        raise ValueError("Folder not found: " + path)
    root = os.path.basename(os.path.normpath(path))
    files = []
    for folder, _, names in os.walk(path):
        for name in names:
            full_path = os.path.join(folder, name)
            relative = os.path.relpath(full_path, path).replace(os.sep, "/")
            # Other files are only listed, to see who handed in the wrong file
            data = b""
            if name.lower().endswith((".py", ".zip")):
                with open(full_path, "rb") as file:
                    data = file.read()
            files.append((root + "/" + relative, data))
    if not files:
        raise ValueError("No files in " + path)
    return files


def import_submissions(ex_id: str, files: list[tuple[str, bytes]]) -> dict:
    students = load_students()
    added, updated = [], []
    with STATE_LOCK:
        state = load_state(ex_id)
        for key, group in group_submissions(files).items():
            ident = identify(group, students)
            if not group["files"]:
                other = ", ".join(group.get("other", [])) or "none"
                missing = f"No .py file was handed in. Files: {other}."
                ident["warning"] = " ".join(
                    text for text in (ident["warning"], missing) if text)
            student_id = ident["number"] or slug(
                ident["name"] + "_" + key)[:60]
            names = _store_files(ex_id, student_id, group["files"])
            if student_id in state["students"]:
                updated.append(student_id)
            else:
                added.append(student_id)
            state["students"][student_id] = {
                "id": student_id,
                **ident,
                "source": group["folder"] or key,
                "files": sorted(names),
                "file": pick_file(names, ex_id, ident["number"]),
                "evaluation": None,
                "grades": {},
                "comments": {},
                "notes": "",
                "finalized": False,
            }
        save_state(ex_id, state)
    return {
        "added": len(added),
        "updated": len(updated),
        "unrecognized": [
            state["students"][student_id]["source"]
            for student_id in added + updated
            if not state["students"][student_id]["recognized"]
        ],
    }


def _store_files(ex_id: str, student_id: str,
                 files: list[tuple[str, bytes]]) -> list[str]:
    folder = os.path.join(data_dir(ex_id), "submissions", student_id)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    names = []
    for name, data in files:
        safe = re.sub(r"[^\w.\- ]", "_", name)
        while safe in names:
            safe = "_" + safe
        with open(os.path.join(folder, safe), "wb") as file:
            file.write(data)
        names.append(safe)
    return names


# Evaluation
def find_ai_trap(ex: dict, source: str) -> list[dict]:
    """Lines containing an ai_trap word. Only a warning for the teacher."""
    hits = []
    for word in ex.get("ai_trap", []):
        for number, line in enumerate(source.splitlines(), 1):
            if word.lower() in line.lower():
                text = line.strip()[:120]
                hits.append({"word": word, "line": number, "text": text})
    return hits


def _run_tests(
    student_file: str, ex: dict, tests: list[dict], timeout: float
) -> dict | None:
    """Run tests in a separate process. Returns None on timeout."""
    with tempfile.TemporaryDirectory() as temp_dir:
        student_copy = os.path.join(
            temp_dir, os.path.basename(student_file))
        shutil.copy(student_file, student_copy)
        job_file = os.path.join(temp_dir, "_job.json")
        result_file = os.path.join(temp_dir, "_result.json")
        job = {
            "student": student_copy,
            "solution": ex["solution"],
            "load_inputs": ex["load_inputs"],
            "tests": tests,
        }
        with open(job_file, "w", encoding="utf-8") as file:
            json.dump(job, file)
        command = [sys.executable, "-I", RUNNER, job_file, result_file]
        try:
            subprocess.run(command, cwd=temp_dir, timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return None
        if not os.path.exists(result_file):
            crashed = {"ok": False,
                       "failures": [{"message": "não foi possível correr"}]}
            return {"load": {"ok": False,
                             "error": "o programa terminou de forma "
                                      "inesperada"},
                    "results": [crashed] * len(tests)}
        with open(result_file, encoding="utf-8") as file:
            return json.load(file)


def _run_all(student_file: str, ex: dict,
             tests: list[dict]) -> tuple[dict, list[dict]]:
    batch = _run_tests(student_file, ex, tests, STUDENT_TIMEOUT)
    if batch is not None:
        return batch["load"], batch["results"]

    if _run_tests(student_file, ex, [], TEST_TIMEOUT) is None:
        error = ("o programa não terminou ao ser carregado "
                 "(possível ciclo infinito)")
        return {"ok": False, "error": error}, [NOT_RUN] * len(tests)

    # Something never finishes: run the tests one by one to find it
    load_info = {"ok": True, "error": None}
    results = []
    for test in tests:
        single = _run_tests(student_file, ex, [test], TEST_TIMEOUT)
        if single is None:
            message = (f"não terminou em {TEST_TIMEOUT} s "
                       "(possível ciclo infinito)")
            results.append({"ok": False, "failures": [
                {"message": message, "timeout": True}]})
        else:
            load_info = single["load"]
            results.append(single["results"][0])
    return load_info, results


def _score_criterion(criterion: dict, results: list[dict]) -> dict:
    """Combine the results of a criterion's tests into its automatic grade."""
    tests = criterion["tests"]
    total_weight = sum(test["weight"] for test in tests) or 1
    passed_weight = sum(test["weight"] for test, result in zip(tests, results)
                        if result["ok"])
    hints_used = set()
    test_results = []
    for test, result in zip(tests, results):
        ran = result["ok"] or bool(result["failures"])
        item = {"label": test["label"], "ok": result["ok"], "ran": ran,
                "failures": result["failures"]}
        # The same hint is shown once, at the first test that needs it
        if ran and not result["ok"] and test["hint"]:
            if test["hint"] not in hints_used:
                item["hint"] = test["hint"]
                hints_used.add(test["hint"])
        test_results.append(item)

    failed = any(item["ran"] and not item["ok"] for item in test_results)
    raw_grade = criterion["points"] * passed_weight / total_weight
    return {
        "name": criterion["name"],
        "points": criterion["points"],
        "auto": round(raw_grade * 4) / 4,
        "passed": sum(1 for item in test_results if item["ok"]),
        "total": len(tests),
        "tests": test_results,
        "hint": criterion["hint"] if failed and not hints_used else "",
        "review": criterion["review"],
    }


def _score_all(ex: dict, results: list[dict]) -> list[dict]:
    criteria = []
    start = 0
    for criterion in ex["criteria"]:
        end = start + len(criterion["tests"])
        criteria.append(_score_criterion(criterion, results[start:end]))
        start = end
    return criteria


def evaluate_file(ex: dict, student_file: str | None) -> dict:
    """Run every test of the exercise on one file and score the criteria."""
    now = time.strftime("%Y-%m-%d %H:%M")
    tests = [{"name": test["name"], "params": test["params"]}
             for criterion in ex["criteria"] for test in criterion["tests"]]
    if not student_file or not os.path.exists(student_file):
        load_info = {"ok": False, "error": "nenhum ficheiro .py entregue"}
        return {"load": load_info,
                "criteria": _score_all(ex, [NOT_RUN] * len(tests)),
                "ai_trap": [], "date": now}

    load_info, results = _run_all(student_file, ex, tests)
    if (load_info.get("error") or "").startswith("SyntaxError"):
        results = [NOT_RUN] * len(tests)
    source = read_text(student_file)
    return {"load": load_info, "criteria": _score_all(ex, results),
            "ai_trap": find_ai_trap(ex, source), "date": now}


def evaluate_student(ex: dict, record: dict) -> dict:
    student_file = None
    if record.get("file"):
        student_file = os.path.join(DATA_DIR, ex["id"], "submissions",
                                    record["id"], record["file"])
    return evaluate_file(ex, student_file)


def apply_evaluation(record: dict, evaluation: dict) -> None:
    """Store a fresh automatic evaluation, resetting grades and comments."""
    record["evaluation"] = evaluation
    record["grades"] = {
        criterion["name"]: criterion["auto"]
        for criterion in evaluation["criteria"]
    }
    record["comments"] = {}
    record["finalized"] = False


def select_students(ex_id: str, ids: list[str] | None = None,
                    regrade: bool = False) -> list[str]:
    """
    Students to grade: the given ids, or the ones never graded (every one
    with regrade). Finalized students are never graded again.
    """
    students = load_state(ex_id)["students"]
    if not ids:
        ids = [student_id for student_id, record in students.items()
               if regrade or not record.get("evaluation")]
    return [student_id for student_id in ids
            if student_id in students
            and not students[student_id].get("finalized")]


def grade_students(
    ex_id: str, ids: list[str],
    on_progress: Callable[[str, bool], None] | None = None,
) -> None:
    """Grade these students, a few at a time, saving each result."""
    ex = load_exercise(ex_id)

    def grade_one(student_id: str) -> None:
        record = load_state(ex_id)["students"][student_id]
        evaluation = evaluate_student(ex, record)
        with STATE_LOCK:
            state = load_state(ex_id)
            apply_evaluation(state["students"][student_id], evaluation)
            save_state(ex_id, state)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(grade_one, student_id): student_id
                   for student_id in ids}
        for future in as_completed(futures):
            error = future.exception()
            if error is not None:
                traceback.print_exception(type(error), error,
                                          error.__traceback__)
            if on_progress:
                on_progress(futures[future], error is None)


def validate_exercise(ex_id: str) -> dict:
    """
    Check rules.json and grade solution.py with it. The solution has to pass
    every test, otherwise a test or an expected value is wrong.
    """
    try:
        ex = load_exercise(ex_id)
    except Exception as error:
        return {"ok": False, "messages": [str(error)]}
    tests = sum(len(criterion["tests"]) for criterion in ex["criteria"])
    points = sum(criterion["points"] for criterion in ex["criteria"])
    messages = [f"rules.json is valid: {len(ex['criteria'])} criteria, "
                f"{tests} tests, {grade_text(points)} points."]
    if not ex["solution"]:
        messages.append("There is no solution.py, so only the rules "
                        "were checked.")
        return {"ok": True, "messages": messages}

    evaluation = evaluate_file(ex, ex["solution"])
    if evaluation["load"]["error"]:
        messages.append(f"solution.py: {evaluation['load']['error']}")
    passed = 0
    for criterion in evaluation["criteria"]:
        passed += criterion["passed"]
        for number, test in enumerate(criterion["tests"], 1):
            if test["ok"]:
                continue
            problems = "; ".join(failure["message"]
                                 for failure in test["failures"])
            messages.append(f"{criterion['name']}, test {number} "
                            f"({test['label']}): "
                            f"{problems or 'not run'}")
    ok = passed == tests and not evaluation["load"]["error"]
    messages.append(f"solution.py passes {passed} of {tests} tests.")
    return {"ok": ok, "messages": messages}


def criterion_grade(record: dict, criterion: dict) -> float:
    value = record.get("grades", {}).get(criterion["name"])
    return criterion["auto"] if value is None else float(value)


def final_grade(record: dict) -> float | None:
    if not record.get("evaluation"):
        return None
    criteria = record["evaluation"]["criteria"]
    grades = [criterion_grade(record, criterion) for criterion in criteria]
    return round(sum(grades), 2)


def needs_review(record: dict) -> bool:
    """The file did not run to the end or a test timed out."""
    evaluation = record.get("evaluation")
    if not evaluation:
        return False
    if not evaluation["load"]["ok"]:
        return True
    return any(failure.get("timeout")
               for criterion in evaluation["criteria"]
               for test in criterion.get("tests", [])
               for failure in test["failures"])


# Reports (Portuguese, for students), shaped like an egrader report
STATUS = {"ok": "OK", "failed": "FALHOU", "not_run": "NÃO CORREU"}


def _fraction(value: float | None, total: float) -> str:
    return f"{grade_text(value)} / {grade_text(total)}"


def _status(test: dict) -> str:
    if test["ok"]:
        return STATUS["ok"]
    return STATUS["failed"] if test["ran"] else STATUS["not_run"]


def _output_lines(title: str, text: str) -> list[str]:
    lines = [f"    - {title}:", "      ```"]
    lines += [f"      {line}" for line in text.splitlines()]
    return lines + ["      ```"]


def _test_lines(test: dict) -> list[str]:
    line = f"  - `{test['label']}`: {_status(test)}"
    if test.get("weight", 1) != 1:
        line += f" (peso {grade_text(test['weight'])})"
    lines = [line]
    for failure in test["failures"]:
        lines.append(f"    - {failure['message']}")
        if "expected_output" in failure:
            lines += _output_lines("Esperado", failure["expected_output"])
        if "actual_output" in failure:
            lines += _output_lines("Obtido", failure["actual_output"])
    if test.get("hint"):
        lines.append(f"    - Explicação: {test['hint']}")
    return lines


def _criterion_lines(record: dict, criterion: dict) -> list[str]:
    grade = criterion_grade(record, criterion)
    lines = [f"## {criterion['name']}", "",
             f"- Nota: {_fraction(grade, criterion['points'])}",
             f"- Testes OK: {criterion['passed']} / {criterion['total']}"]
    tests = criterion.get("tests", [])
    if tests:
        lines.append("- Testes:")
        for test in tests:
            lines += _test_lines(test)
    if criterion.get("hint"):
        lines.append(f"- Explicação: {criterion['hint']}")
    comment = (record.get("comments", {}).get(criterion["name"]) or "")
    if comment.strip():
        lines.append(f"- Comentário: {comment.strip()}")
    return lines + [""]


def report_md(ex: dict, record: dict) -> str:
    evaluation = record["evaluation"]
    criteria = evaluation["criteria"]
    total = sum(criterion["points"] for criterion in criteria)
    student = record["name"]
    if record["number"]:
        student += f" ({record['number']})"

    lines = ["# Relatório de avaliação", "",
             f"- Exercício: {ex['id']}",
             f"- Aluno: {student}",
             f"- Nota: {_fraction(final_grade(record), total)}"]
    if evaluation["load"].get("error"):
        lines.append(f"- Erro: {evaluation['load']['error']}")
    lines.append("")
    for criterion in criteria:
        lines += _criterion_lines(record, criterion)
    notes = (record.get("notes") or "").strip()
    if notes:
        lines += ["## Observações", "", notes, ""]
    return "\n".join(lines).rstrip() + "\n"


def report_text(ex: dict, record: dict) -> str:
    """Plain-text version of the report, to paste into Moodle."""
    lines = []
    for line in report_md(ex, record).splitlines():
        if line.strip() == "```":
            continue
        lines.append(re.sub(r"^#+ ", "", line).replace("`", ""))
    return "\n".join(lines).rstrip() + "\n"


def report_name(ex_id: str, record: dict) -> str:
    name = f"{ex_id}_{record['number']}_{slug(record['name'])}"
    return re.sub(r"_+", "_", name).strip("_")


def _grades_csv(state: dict, ids: list[str]) -> str:
    rows = ["Número;Nome;Nota;Finalizado"]
    records = sorted(state["students"].values(), key=name_order)
    for record in records:
        if record["id"] not in ids:
            continue
        finalized = "sim" if record.get("finalized") else "não"
        rows.append(";".join([record["number"], record["name"],
                              grade_text(final_grade(record)), finalized]))
    return "\n".join(rows) + "\n"


def export_reports(ex_id: str, ids: list[str]) -> tuple[bytes, str, int]:
    """
    Write a .md report per student and the grades to data/<exercise>/reports
    and return them as a zip, with the folder and the number of students.
    """
    ex = load_exercise(ex_id)
    state = load_state(ex_id)
    out_dir = os.path.join(data_dir(ex_id), "reports")
    os.makedirs(out_dir, exist_ok=True)
    outputs = {}
    exported = []
    for student_id in ids:
        record = state["students"].get(student_id)
        if not record or not record.get("evaluation"):
            continue
        name = report_name(ex_id, record) + ".md"
        outputs[name] = report_md(ex, record).encode("utf-8")
        exported.append(student_id)
    csv_name = ex_id + "_notas.csv"
    outputs[csv_name] = _grades_csv(state, exported).encode("utf-8-sig")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in outputs.items():
            archive.writestr(filename, content)
            with open(os.path.join(out_dir, filename), "wb") as file:
                file.write(content)
    return buffer.getvalue(), out_dir, len(exported)
