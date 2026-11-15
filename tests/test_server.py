"""Tests for server.py: the JSON API behind the web interface."""

import base64
import io
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from typing import Any

import server
from tests.helpers import DOUBLE_RULES, DOUBLE_SOLUTION, ProjectTestCase

# Talk to the test server directly, even if a proxy is configured
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServerTestCase(ProjectTestCase):
    def setUp(self) -> None:
        super().setUp()
        server._jobs.clear()
        self.httpd = server.make_server(0)
        thread = threading.Thread(target=self.httpd.serve_forever,
                                  daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, thread)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def stop_server(self, thread: threading.Thread) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        thread.join(5)

    def request(self, path: str,
                body: Any = None) -> tuple[int, bytes, dict]:
        data = body
        if body is not None and not isinstance(body, bytes):
            data = json.dumps(body).encode()
        request = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"})
        try:
            with OPENER.open(request, timeout=60) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def get_json(self, path: str) -> Any:
        status, data, _ = self.request(path)
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def post_json(self, path: str, body: Any) -> Any:
        status, data, _ = self.request(path, body)
        self.assertEqual(status, 200, data)
        return json.loads(data)

    def wait_for_grading(self, ex_id: str) -> dict:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            progress = self.get_json(f"/api/students?ex={ex_id}")["progress"]
            if not progress["running"]:
                return progress
            time.sleep(0.1)
        self.fail("grading did not finish")


class PageTest(ServerTestCase):
    def test_serves_the_page(self) -> None:
        status, data, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"<title>Pythia</title>", data)

    def test_unknown_paths(self) -> None:
        self.assertEqual(self.request("/nada")[0], 404)
        self.assertEqual(self.request("/api/nada", {})[0], 404)


class ExercisesApiTest(ServerTestCase):
    def test_save_show_and_check_an_exercise(self) -> None:
        info = self.post_json("/api/exercises", {
            "id": "Dobro", "solution": DOUBLE_SOLUTION,
            "rules": json.dumps(DOUBLE_RULES)})
        self.assertEqual((info["id"], info["total"], info["error"]),
                         ("Dobro", 20, None))
        self.assertEqual([item["id"]
                          for item in self.get_json("/api/exercises")],
                         ["Dobro"])
        solution = self.get_json("/api/exercise_file?ex=Dobro&which=solution")
        self.assertEqual(solution["text"], DOUBLE_SOLUTION)
        rules = self.get_json("/api/exercise_file?ex=Dobro&which=rules")
        self.assertEqual(json.loads(rules["text"]), DOUBLE_RULES)
        self.assertTrue(self.get_json("/api/validate?ex=Dobro")["ok"])

    def test_broken_rules_are_reported_when_saved(self) -> None:
        info = self.post_json("/api/exercises", {"id": "Mau", "rules": "{"})
        self.assertIn("not valid JSON", info["error"])

    def test_bad_requests(self) -> None:
        status, data, _ = self.request(
            "/api/exercise_file?ex=Nada&which=rules")
        self.assertEqual(status, 400)
        self.assertIn("Exercise 'Nada' not found", json.loads(data)["error"])
        self.assertEqual(self.request("/api/student?ex=Dobro")[0], 400)
        self.assertEqual(self.request("/api/save", b"{nope")[0], 400)


class GradingApiTest(ServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_double_exercise()
        self.folder = self.moodle_folder("Ana Silva", "20000001",
                                         DOUBLE_SOLUTION)
        self.moodle_folder("Bruno Costa", "20000002",
                           "def dobro(x):\n    return x\n", "100002")

    def test_import_grade_review_and_export(self) -> None:
        result = self.post_json("/api/import_folder",
                                {"ex": "Dobro", "folder": self.folder})
        self.assertEqual(result["added"], 2)
        students = self.get_json("/api/students?ex=Dobro")["students"]
        self.assertEqual([student["name"] for student in students],
                         ["Ana Silva", "Bruno Costa"])
        self.assertFalse(any(student["evaluated"] for student in students))

        self.assertEqual(self.post_json("/api/evaluate",
                                        {"ex": "Dobro"})["total"], 2)
        progress = self.wait_for_grading("Dobro")
        self.assertEqual((progress["done"], progress["failed"]), (2, 0))

        details = self.get_json("/api/student?ex=Dobro&id=20000002")
        self.assertEqual(details["summary"]["grade"], 0)
        self.assertIn("def dobro", details["code"])
        self.assertEqual(len(details["evaluation"]["criteria"]), 2)

        summary = self.post_json("/api/save", {
            "ex": "Dobro", "id": "20000002", "grades": {"dobro": 2.5},
            "comments": {"dobro": "Revisto."}, "notes": "Visto.",
            "finalized": True, "name": " Bruno Costa "})
        self.assertEqual((summary["grade"], summary["finalized"],
                          summary["name"]), (2.5, True, "Bruno Costa"))
        report = self.get_json("/api/report?ex=Dobro&id=20000002")
        self.assertIn("Comentário: Revisto.", report["md"])
        self.assertNotIn("**", report["text"])

        self.assertEqual(self.post_json("/api/evaluate",
                                        {"ex": "Dobro"})["total"], 0)
        self.wait_for_grading("Dobro")
        self.assertEqual(self.post_json("/api/evaluate",
                                        {"ex": "Dobro", "all": True})["total"],
                         1)
        self.wait_for_grading("Dobro")
        details = self.get_json("/api/student?ex=Dobro&id=20000002")
        self.assertEqual(details["summary"]["grade"], 2.5)

        status, data, headers = self.request(
            "/api/export?ex=Dobro")
        self.assertEqual((status, headers["X-Count"]), (200, "2"))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(len(archive.namelist()), 3)
            self.assertIn("Dobro_notas.csv", archive.namelist())

    def test_upload_files(self) -> None:
        content = base64.b64encode(DOUBLE_SOLUTION.encode()).decode()
        path = "Ana Silva_1_assignsubmission_file/Dobro_20000001.py"
        result = self.post_json("/api/import_files", {
            "ex": "Dobro", "files": [{"path": path, "data": content}]})
        self.assertEqual(result["added"], 1)

    def test_choose_another_file(self) -> None:
        self.write("entrega/Ana Silva_100001_assignsubmission_file/extra.py",
                   "x = 1\n")
        self.post_json("/api/import_folder",
                       {"ex": "Dobro", "folder": self.folder})
        summary = self.post_json("/api/save", {"ex": "Dobro",
                                               "id": "20000001",
                                               "file": "extra.py"})
        self.assertEqual(summary["file"], "extra.py")
        summary = self.post_json("/api/save", {"ex": "Dobro",
                                               "id": "20000001",
                                               "file": "../fora.py"})
        self.assertEqual(summary["file"], "extra.py")

    def test_one_evaluation_at_a_time(self) -> None:
        server._jobs["Dobro"] = {"running": True}
        status, data, _ = self.request("/api/evaluate", {"ex": "Dobro"})
        self.assertEqual(status, 400)
        self.assertIn("already running", json.loads(data)["error"])


if __name__ == "__main__":
    unittest.main()
