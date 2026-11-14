"""
Runs a student's file in a separate process and applies the tests to it.
Called by the engine: python -I runner.py job.json result.json

The job lists the tests as {"name": check, "params": {...}}. Each one is
handed to the matching function in checks.py.
"""

import json
import os
import sys

# Isolated mode (-I) leaves this folder out of the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402
import sandbox  # noqa: E402


def run_test(test: dict, student: sandbox.Submission,
             solution: sandbox.Submission) -> dict:
    check = checks.available()[test["name"]]
    params = checks.decode(test["params"])
    try:
        failures = check(student, solution, **params)
    except (checks.Failed, checks.RulesError) as problem:
        failures = [{"message": str(problem)}]
    except KeyboardInterrupt:
        raise
    except BaseException as error:
        message = f"erro {sandbox.describe_error(error, student.path)}"
        failures = [{"message": message}]
    return {"ok": not failures, "failures": failures}


def main() -> None:
    job_file, result_file = sys.argv[1], sys.argv[2]
    with open(job_file, encoding="utf-8") as file:
        job = json.load(file)
    sys.setrecursionlimit(3000)

    if job["solution"]:
        solution = sandbox.load(job["solution"], job["load_inputs"])
    else:
        solution = sandbox.empty_submission()
    student = sandbox.load(job["student"], job["load_inputs"])

    load_info = {"ok": student.error is None, "error": None}
    if student.error is not None:
        load_info["error"] = sandbox.describe_error(student.error,
                                                    student.path)
    results = [run_test(test, student, solution) for test in job["tests"]]

    with open(result_file, "w", encoding="utf-8") as file:
        json.dump({"load": load_info, "results": results}, file,
                  ensure_ascii=False)


if __name__ == "__main__":
    main()
