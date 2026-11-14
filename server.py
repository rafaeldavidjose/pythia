"""
Web interface: a small HTTP server with the JSON API used by web/index.html.
Started by "python pythia.py" (or "python pythia.py serve").
"""

import base64
import json
import os
import threading
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import engine

PORT = 8765
PAGE = os.path.join(engine.BASE, "web", "index.html")

_jobs: dict[str, dict] = {}  # progress of running evaluations, per exercise


def _grade_in_background(ex_id: str, ids: list[str]) -> None:
    progress = _jobs[ex_id]

    def count(student_id: str, ok: bool) -> None:
        progress["done"] += 1
        if not ok:
            progress["failed"] += 1

    try:
        engine.grade_students(ex_id, ids, count)
    except Exception as error:
        progress["error"] = f"Error in the exercise rules: {error}"
    progress["running"] = False


def start_evaluation(ex_id: str, ids: list[str] | None,
                     regrade: bool) -> dict:
    if _jobs.get(ex_id, {}).get("running"):
        raise ValueError("An evaluation is already running for this exercise.")
    ids = engine.select_students(ex_id, ids, regrade)
    _jobs[ex_id] = {"running": True, "total": len(ids), "done": 0,
                    "failed": 0, "error": None}
    thread = threading.Thread(target=_grade_in_background,
                              args=(ex_id, ids), daemon=True)
    thread.start()
    return dict(_jobs[ex_id])


def summary(record: dict) -> dict:
    evaluation = record.get("evaluation")
    return {
        "id": record["id"],
        "number": record["number"],
        "name": record["name"],
        "class": record.get("class", ""),
        "recognized": record.get("recognized", False),
        "warning": record.get("warning", ""),
        "source": record.get("source", ""),
        "file": record.get("file"),
        "files": record.get("files", []),
        "grade": engine.final_grade(record),
        "finalized": record.get("finalized", False),
        "evaluated": bool(evaluation),
        "ai_trap": bool(evaluation and evaluation.get("ai_trap")),
        "needs_review": engine.needs_review(record),
    }


def student_details(ex_id: str, student_id: str) -> dict:
    record = engine.load_state(ex_id)["students"][student_id]
    code = ""
    if record.get("file"):
        path = os.path.join(engine.DATA_DIR, ex_id, "submissions",
                            record["id"], record["file"])
        if os.path.exists(path):
            code = engine.read_text(path)
    return {
        "summary": summary(record),
        "evaluation": record.get("evaluation"),
        "grades": record.get("grades", {}),
        "comments": record.get("comments", {}),
        "notes": record.get("notes", ""),
        "code": code,
    }


def save_student(changes: dict) -> dict:
    with engine.STATE_LOCK:
        state = engine.load_state(changes["ex"])
        record = state["students"][changes["id"]]
        record.setdefault("grades", {}).update(
            {name: float(value)
             for name, value in changes.get("grades", {}).items()})
        record.setdefault("comments", {}).update(changes.get("comments", {}))
        for key in ("notes", "finalized"):
            if key in changes:
                record[key] = changes[key]
        for key in ("name", "number", "class"):
            if key in changes:
                record[key] = changes[key].strip()
        if changes.get("file") in record.get("files", []):
            record["file"] = changes["file"]
        engine.save_state(changes["ex"], state)
    return summary(record)


def exercise_file(ex_id: str, which: str) -> str:
    name = "solution.py" if which == "solution" else "rules.json"
    path = os.path.join(engine.exercise_folder(ex_id), name)
    return engine.read_text(path) if os.path.exists(path) else ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def send(self, data: Any, status: int = 200,
             content_type: str = "application/json",
             headers: dict | None = None) -> None:
        if content_type == "application/json":
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if content_type.startswith(("application/json", "text")):
            content_type += "; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def answer(self, handle: Any, *args: Any) -> None:
        try:
            handle(*args)
        except KeyError as error:
            self.send({"error": f"Not found: {error}"}, 400)
        except ValueError as error:
            self.send({"error": str(error)}, 400)
        except Exception as error:
            traceback.print_exc()
            self.send({"error": f"{type(error).__name__}: {error}"}, 500)

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        self.answer(self.handle_get, url.path, query)

    def do_POST(self) -> None:
        self.answer(lambda: self.handle_post(self.path, self.body()))

    def handle_get(self, path: str, query: dict) -> None:
        if path == "/":
            with open(PAGE, "rb") as file:
                self.send(file.read(), content_type="text/html")
        elif path == "/api/exercises":
            self.send(engine.list_exercises())
        elif path == "/api/exercise_file":
            self.send({"text": exercise_file(query["ex"], query["which"])})
        elif path == "/api/validate":
            self.send(engine.validate_exercise(query["ex"]))
        elif path == "/api/students":
            records = engine.load_state(query["ex"])["students"].values()
            rows = sorted(
                (summary(record) for record in records),
                key=lambda row: (row["class"],
                                 engine.strip_accents(row["name"]).lower()))
            self.send({"students": rows, "progress": _jobs.get(query["ex"])})
        elif path == "/api/student":
            self.send(student_details(query["ex"], query["id"]))
        elif path == "/api/report":
            ex = engine.load_exercise(query["ex"])
            record = engine.load_state(query["ex"])["students"][query["id"]]
            self.send({"md": engine.report_md(ex, record),
                       "text": engine.report_text(ex, record)})
        elif path == "/api/export":
            self.export(query)
        else:
            self.send({"error": "not found"}, 404)

    def export(self, query: dict) -> None:
        ex_id = query["ex"]
        if query.get("ids"):
            ids = query["ids"].split(",")
        else:
            ids = list(engine.load_state(ex_id)["students"])
        formats = query.get("formats", "md,pdf").split(",")
        data, folder, count = engine.export_reports(ex_id, ids, formats)
        headers = {
            "Content-Disposition":
                f'attachment; filename="{ex_id}_reports.zip"',
            "X-Folder": urllib.parse.quote(folder),
            "X-Count": str(count),
        }
        self.send(data, content_type="application/zip", headers=headers)

    def handle_post(self, path: str, body: dict) -> None:
        if path == "/api/exercises":
            ex_id = engine.save_exercise(body["id"], body.get("solution"),
                                         body.get("rules"))
            exercises = engine.list_exercises()
            self.send(next(exercise for exercise in exercises
                           if exercise["id"] == ex_id))
        elif path == "/api/import_folder":
            files = engine.read_folder(body["folder"])
            self.send(engine.import_submissions(body["ex"], files))
        elif path == "/api/import_files":
            files = [(item["path"], base64.b64decode(item["data"]))
                     for item in body["files"]]
            self.send(engine.import_submissions(body["ex"], files))
        elif path == "/api/evaluate":
            self.send(start_evaluation(body["ex"], body.get("ids"),
                                       body.get("all", False)))
        elif path == "/api/save":
            self.send(save_student(body))
        else:
            self.send({"error": "not found"}, 404)


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = PORT, open_browser: bool = True) -> None:
    server = make_server(port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Pythia running at {url}")
    print("Close this window or press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
