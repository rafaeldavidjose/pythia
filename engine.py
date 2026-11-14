"""
Grader engine: exercises, importing submissions, evaluation, reports and export.
No language model is involved: grades come only from the tests defined in
exercises/<id>/rules.json (or criteria.py), compared against solution.py.

Everything a student reads (reports, test messages) is in Portuguese.
"""

import csv
import importlib.util
import io
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from typing import Any

import rules
import simple_pdf

BASE = os.path.dirname(os.path.abspath(__file__))
EXERCISES_DIR = os.path.join(BASE, "exercises")
DATA_DIR = os.path.join(BASE, "data")
RUNNER = os.path.join(BASE, "runner.py")
STUDENTS_FILE = os.path.join(BASE, "students.csv")

STUDENT_TIMEOUT = 10  # seconds for all of a student's tests
TEST_TIMEOUT = 5  # seconds per test, used to isolate an infinite loop

if BASE not in sys.path:
    sys.path.insert(0, BASE)


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", strip_accents(text))
    return text.strip("_") or "student"


def read_text(path: str) -> str:
    with open(path, "rb") as file:
        raw = file.read()
    for encoding in ("utf-8", "cp1252", "latin-1"):
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


# Student list (students.csv: number;name;class)
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
        class_name = row[2].strip() if len(row) > 2 else ""
        students.append(
            {"number": number, "name": row[1].strip(), "class": class_name}
        )
    return students


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
def _load_criteria_py(folder: str, ex_id: str) -> dict:
    spec = importlib.util.spec_from_file_location(
        "criteria_" + slug(ex_id), os.path.join(folder, "criteria.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "title": getattr(module, "TITLE", ex_id),
        "load_inputs": list(getattr(module, "LOAD_INPUTS", [])),
        "ai_trap": [str(word) for word in getattr(module, "AI_TRAP", [])],
        "criteria": module.CRITERIA,
    }


def load_exercise(ex_id: str) -> dict:
    """Load rules.json if the exercise has one, otherwise criteria.py."""
    folder = os.path.join(EXERCISES_DIR, ex_id)
    solution = os.path.join(folder, "solution.py")
    has_solution = os.path.exists(solution)
    rules_file = os.path.join(folder, "rules.json")
    if os.path.exists(rules_file):
        definition = rules.load_rules(rules_file, has_solution)
    else:
        definition = _load_criteria_py(folder, ex_id)
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
        has_rules = os.path.exists(os.path.join(folder, "rules.json"))
        has_criteria = os.path.exists(os.path.join(folder, "criteria.py"))
        has_solution = os.path.exists(os.path.join(folder, "solution.py"))
        if not has_rules and not has_criteria:
            info["error"] = "rules.json or criteria.py is missing"
        elif not has_rules and not has_solution:
            info["error"] = "solution.py is missing"
        else:
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
                info["error"] = type(error).__name__ + ": " + str(error)
        result.append(info)
    return result


def save_exercise(
    ex_id: str, solution: str | None, criteria: str | None
) -> str:
    ex_id = slug(ex_id)
    folder = os.path.join(EXERCISES_DIR, ex_id)
    os.makedirs(folder, exist_ok=True)
    files = {"solution.py": solution}
    if criteria is not None:
        # JSON starts with "{", anything else is the Python criteria file
        is_rules = criteria.lstrip().startswith("{")
        files["rules.json" if is_rules else "criteria.py"] = criteria
        other = "criteria.py" if is_rules else "rules.json"
        if os.path.exists(os.path.join(folder, other)):
            os.remove(os.path.join(folder, other))
    for filename, content in files.items():
        if content is None:
            continue
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as file:
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
    files count as one student each.
    """
    files = [(path.replace("\\", "/").strip("/"), data)
             for path, data in files]
    py_files = [
        (path, data) for path, data in _expand_zips(files)
        if path.lower().endswith(".py")
        and "__MACOSX" not in path
        and not os.path.basename(path).startswith(".")
    ]

    # The common root is the folder that was chosen for import
    folders = [path.split("/")[:-1] for path, _ in py_files]
    root = []
    for parts in zip(*folders):
        if len(set(parts)) != 1:
            break
        root.append(parts[0])
    all_at_root = all(len(path.split("/")) == len(root) + 1
                      for path, _ in py_files)
    root_is_student = bool(root) and bool(
        MOODLE_FOLDER.match(root[-1]) or STUDENT_NUMBER.search(root[-1]))

    groups = {}
    for path, data in py_files:
        parts = path.split("/")
        if len(parts) - len(root) > 1:
            key = "/".join(parts[:len(root) + 1])
            folder = parts[len(root)]
        elif all_at_root and root_is_student:
            key = "/".join(root)
            folder = root[-1]
        else:
            key = path
            folder = ""
        group = groups.setdefault(key, {"folder": folder, "files": []})
        group["files"].append((os.path.basename(path), data))
    return groups


def identify(group: dict, students: list[dict]) -> dict:
    folder = group["folder"]
    filenames = [name for name, _ in group["files"]]
    number = None
    for text in filenames + [folder]:
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
        "class": match["class"] if match else "",
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
            if not name.lower().endswith((".py", ".zip")):
                continue
            full_path = os.path.join(folder, name)
            relative = os.path.relpath(full_path, path).replace(os.sep, "/")
            with open(full_path, "rb") as file:
                files.append((root + "/" + relative, file.read()))
    if not files:
        raise ValueError("No .py or .zip files in " + path)
    return files


def import_submissions(ex_id: str, files: list[tuple[str, bytes]]) -> dict:
    students = load_students()
    state = load_state(ex_id)
    added, updated = [], []
    for key, group in group_submissions(files).items():
        ident = identify(group, students)
        student_id = ident["number"] or slug(ident["name"] + "_" + key)[:60]
        folder = os.path.join(data_dir(ex_id), "submissions", student_id)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        os.makedirs(folder)
        names = []
        for name, data in group["files"]:
            safe = re.sub(r"[^\w.\- ]", "_", name)
            while safe in names:
                safe = "_" + safe
            with open(os.path.join(folder, safe), "wb") as file:
                file.write(data)
            names.append(safe)
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


# Evaluation
def find_ai_trap(ex: dict, source: str) -> list[dict]:
    """Lines containing an AI_TRAP word. Only a warning for the teacher."""
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
        job_file = os.path.join(temp_dir, "_job.pkl")
        result_file = os.path.join(temp_dir, "_result.json")
        job = {
            "student": student_copy,
            "solution": ex["solution"],
            "load_inputs": ex["load_inputs"],
            "tests": tests,
        }
        with open(job_file, "wb") as file:
            pickle.dump(job, file)
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


def _score_criterion(criterion: dict, results: list[dict]) -> dict:
    """Combine the results of a criterion's tests into its automatic grade."""
    tests = criterion["tests"]
    total_weight = sum(test["weight"] for test in tests) or 1
    passed_weight = 0
    passed = 0
    failures = []
    hints_used = set()
    for test, result in zip(tests, results):
        if result["ok"]:
            passed_weight += test["weight"]
            passed += 1
            continue
        hint = test.get("hint") or ""
        for item in result["failures"]:
            if any(known["message"] == item["message"] for known in failures):
                continue
            item = dict(item)
            if hint and hint not in hints_used:
                item["hint"] = hint
                hints_used.add(hint)
            failures.append(item)
    if failures and criterion.get("hint") and not hints_used:
        failures.append({"message": "", "hint": criterion["hint"]})
    raw_grade = criterion["points"] * passed_weight / total_weight
    test_results = [
        {"label": test["label"], "ok": result["ok"],
         "ran": result["ok"] or bool(result["failures"])}
        for test, result in zip(tests, results)
    ]
    return {
        "name": criterion["name"],
        "points": criterion["points"],
        "auto": round(raw_grade * 4) / 4,
        "passed": passed,
        "total": len(tests),
        "failures": failures,
        "results": test_results,
        "review": criterion["review"],
    }


def evaluate_student(ex: dict, record: dict) -> dict:
    folder = os.path.join(DATA_DIR, ex["id"], "submissions", record["id"])
    student_file = None
    if record.get("file"):
        student_file = os.path.join(folder, record["file"])
    now = time.strftime("%Y-%m-%d %H:%M")
    no_results = {"ok": False, "failures": []}

    if not student_file or not os.path.exists(student_file):
        criteria = [
            _score_criterion(criterion, [no_results] * len(criterion["tests"]))
            for criterion in ex["criteria"]
        ]
        load_info = {"ok": False, "error": "nenhum ficheiro .py entregue"}
        return {"load": load_info, "criteria": criteria, "ai_trap": [],
                "date": now}

    tests = [test for criterion in ex["criteria"] for test in criterion["tests"]]
    batch = _run_tests(student_file, ex, tests, STUDENT_TIMEOUT)
    if batch is not None:
        load_info = batch["load"]
        results = batch["results"]
    else:
        # Something never finishes: run the tests one by one to find it
        load_info = {"ok": True, "error": None}
        results = []
        for test in tests:
            single = _run_tests(student_file, ex, [test], TEST_TIMEOUT)
            if single is None:
                message = (f"{test['label']}: não terminou em "
                           f"{TEST_TIMEOUT} s (possível ciclo infinito)")
                results.append({"ok": False, "failures": [
                    {"message": message, "timeout": True}]})
            else:
                load_info = single["load"]
                results.append(single["results"][0])

    if (load_info.get("error") or "").startswith("SyntaxError"):
        results = [no_results] * len(tests)

    criteria = []
    start = 0
    for criterion in ex["criteria"]:
        end = start + len(criterion["tests"])
        criteria.append(_score_criterion(criterion, results[start:end]))
        start = end
    source = read_text(student_file)
    return {"load": load_info, "criteria": criteria,
            "ai_trap": find_ai_trap(ex, source), "date": now}


def apply_evaluation(record: dict, evaluation: dict) -> None:
    """Store a fresh automatic evaluation, resetting grades and comments."""
    record["evaluation"] = evaluation
    record["grades"] = {
        criterion["name"]: criterion["auto"]
        for criterion in evaluation["criteria"]
    }
    record["comments"] = {}
    record["finalized"] = False


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
               for failure in criterion["failures"])


# Reports (Portuguese, for students)
def _fraction(value: float | None, total: float) -> str:
    return f"{grade_text(value)} / {grade_text(total)}"


def _failure_lines(failure: dict) -> list[str]:
    lines = []
    if failure.get("message"):
        lines.append("- " + failure["message"])
        if "expected_output" in failure:
            lines += ["", "  Esperado:", "", "```",
                      *failure["expected_output"].splitlines(), "```", "",
                      "  Obtido:", "", "```",
                      *failure["actual_output"].splitlines(), "```", ""]
    if failure.get("hint"):
        indent = "  " if failure.get("message") else ""
        lines.append(f"{indent}Sugestão: {failure['hint']}")
    return lines


def _test_lines(criterion: dict) -> list[str]:
    lines = []
    for number, test in enumerate(criterion.get("results", []), 1):
        if test["ok"]:
            status = "passou"
        elif test["ran"]:
            status = "falhou"
        else:
            status = "não executado"
        lines.append(f"- [{status}] Teste {number}: {test['label']}")
    return lines


def report_md(ex: dict, record: dict) -> str:
    evaluation = record["evaluation"]
    criteria = evaluation["criteria"]
    total = sum(criterion["points"] for criterion in criteria)
    student = record["name"]
    if record["number"]:
        student += f" ({record['number']})"

    lines = [
        "# Relatório de avaliação automática",
        "",
        f"**Exercício:** {ex['id']} · {ex['title']}",
        f"**Aluno:** {student}",
    ]
    if record.get("file"):
        lines.append(f"**Ficheiro:** {record['file']}")
    passed = sum(criterion["passed"] for criterion in criteria)
    tests = sum(criterion["total"] for criterion in criteria)
    lines += [f"**Nota:** {_fraction(final_grade(record), total)}",
              f"**Testes certos:** {passed}/{tests}", ""]

    error = evaluation["load"].get("error")
    syntax_error = bool(error) and error.startswith("SyntaxError")
    if syntax_error:
        lines += [f"O ficheiro não corre: {error}. "
                  "Nenhum teste pôde ser executado.", ""]
    elif error:
        lines += [f"Erro ao executar o ficheiro: {error}.", ""]

    lines += ["| Critério | Testes | Nota |", "|---|---|---|"]
    for criterion in criteria:
        grade = _fraction(
            criterion_grade(record, criterion), criterion["points"])
        tests = f"{criterion['passed']}/{criterion['total']}"
        lines.append(f"| {criterion['name']} | {tests} | {grade} |")
    lines += ["", "## Resultados por critério", ""]

    for criterion in criteria:
        grade = _fraction(
            criterion_grade(record, criterion), criterion["points"])
        lines += [f"### {criterion['name']} · {grade}", ""]
        lines += [f"Testes certos: {criterion['passed']}/"
                  f"{criterion['total']}.", ""]
        lines += _test_lines(criterion)
        if criterion["failures"]:
            lines += ["", "Detalhe das falhas:", ""]
            for failure in criterion["failures"]:
                lines += _failure_lines(failure)
        comments = record.get("comments", {})
        comment = (comments.get(criterion["name"]) or "").strip()
        if comment:
            lines += ["", f"Comentário: {comment}"]
        lines.append("")

    notes = (record.get("notes") or "").strip()
    if notes:
        lines += ["## Observações", "", notes, ""]
    lines += [
        "---",
        "",
        "Avaliação gerada automaticamente com testes ao código entregue, "
        "comparando-o com a resolução de referência. A nota de cada "
        "critério é proporcional aos testes certos.",
    ]
    return "\n".join(lines)


def report_text(ex: dict, record: dict) -> str:
    """Plain-text version of the report, to paste into Moodle."""
    text = report_md(ex, record)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = text.replace("**", "").replace("```", "")
    text = re.sub(r"^\|---.*\n", "", text, flags=re.M)
    text = re.sub(r"^\| (.*) \|$",
                  lambda match: match.group(1).replace(" | ", "  "),
                  text, flags=re.M)
    text = re.sub(r"^---$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text)


def report_name(ex_id: str, record: dict) -> str:
    name = f"{ex_id}_{record['number']}_{slug(record['name'])}"
    return re.sub(r"_+", "_", name).strip("_")


def _grades_csv(state: dict, ids: list[str]) -> str:
    rows = ["Número;Nome;Turma;Nota;Finalizado"]
    records = sorted(state["students"].values(),
                     key=lambda record: record["name"])
    for record in records:
        if record["id"] not in ids:
            continue
        finalized = "sim" if record.get("finalized") else "não"
        rows.append(";".join([record["number"], record["name"],
                              record.get("class", ""),
                              grade_text(final_grade(record)), finalized]))
    return "\n".join(rows) + "\n"


def export_reports(
    ex_id: str, ids: list[str], formats: list[str]
) -> tuple[bytes, str, int]:
    """Write reports to data/<exercise>/reports and return them as a zip."""
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
        name = report_name(ex_id, record)
        md = report_md(ex, record)
        if "md" in formats:
            outputs[name + ".md"] = md.encode("utf-8")
        if "pdf" in formats:
            outputs[name + ".pdf"] = simple_pdf.markdown_to_pdf(md)
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
