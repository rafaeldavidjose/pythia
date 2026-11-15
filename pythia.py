"""
Pythia command line. Without a command it starts the web interface.

    python pythia.py                          web interface
    python pythia.py checks                   checks rules.json can use
    python pythia.py validate EXERCISE        rules against solution.py
    python pythia.py import EXERCISE FOLDER   import submissions
    python pythia.py assess EXERCISE          grade the new submissions
    python pythia.py report EXERCISE          grades, or --export files
"""

import argparse
import sys

import checks
import engine
import server


def command_serve(args: argparse.Namespace) -> int:
    server.serve(args.port, not args.no_browser)
    return 0


def command_checks(args: argparse.Namespace) -> int:
    for name in checks.available():
        print(name)
        print(f"    {checks.summary(name)}")
        print(f"    params: {', '.join(checks.describe_parameters(name))}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    result = engine.validate_exercise(args.exercise)
    for message in result["messages"]:
        print(message)
    return 0 if result["ok"] else 1


def command_import(args: argparse.Namespace) -> int:
    engine.exercise_folder(args.exercise)
    result = engine.import_submissions(args.exercise,
                                       engine.read_folder(args.folder))
    print(f"{result['added']} added, {result['updated']} updated.")
    for source in result["unrecognized"]:
        print(f"Not found in students.csv: {source}")
    return 0


def command_assess(args: argparse.Namespace) -> int:
    engine.load_exercise(args.exercise)
    ids = engine.select_students(args.exercise, args.ids, args.regrade)
    if not ids:
        print("No students to grade.")
        return 0
    done = 0

    def progress(student_id: str, ok: bool) -> None:
        nonlocal done
        done += 1
        status = "graded" if ok else "failed"
        print(f"[{done}/{len(ids)}] {student_id} {status}")

    engine.grade_students(args.exercise, ids, progress)
    return 0


def _status(record: dict) -> str:
    if not record.get("evaluation"):
        return "not graded"
    if record.get("finalized"):
        return "finalized"
    return "review" if engine.needs_review(record) else "graded"


def _tests(record: dict) -> str:
    if not record.get("evaluation"):
        return "-"
    criteria = record["evaluation"]["criteria"]
    passed = sum(criterion["passed"] for criterion in criteria)
    total = sum(criterion["total"] for criterion in criteria)
    return f"{passed}/{total}"


def command_report(args: argparse.Namespace) -> int:
    engine.exercise_folder(args.exercise)
    records = sorted(engine.load_state(args.exercise)["students"].values(),
                     key=engine.name_order)
    if args.export:
        ids = [record["id"] for record in records if record.get("evaluation")]
        _, folder, count = engine.export_reports(args.exercise, ids)
        print(f"{count} reports written to {folder}")
        return 0

    rows = [("Number", "Name", "Grade", "Tests", "Status")]
    for record in records:
        rows.append((record["number"], record["name"],
                     engine.grade_text(engine.final_grade(record)),
                     _tests(record), _status(record)))
    widths = [max(len(row[column]) for row in rows)
              for column in range(len(rows[0]))]
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row, widths)]
        print("  ".join(cells).rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pythia.py",
        description="Grade Python exercises with tests from rules.json.")
    parser.set_defaults(func=command_serve, port=server.PORT,
                        no_browser=False)
    commands = parser.add_subparsers(title="commands", dest="command")

    serve = commands.add_parser("serve", help="start the web interface")
    serve.add_argument("--port", type=int, default=server.PORT)
    serve.add_argument("--no-browser", action="store_true",
                       help="do not open the browser")
    serve.set_defaults(func=command_serve)

    listing = commands.add_parser(
        "checks", help="list the checks a rules.json can use")
    listing.set_defaults(func=command_checks)

    validate = commands.add_parser(
        "validate", help="check rules.json and grade solution.py with it")
    validate.add_argument("exercise")
    validate.set_defaults(func=command_validate)

    importing = commands.add_parser(
        "import", help="import a folder of submissions")
    importing.add_argument("exercise")
    importing.add_argument("folder")
    importing.set_defaults(func=command_import)

    assess = commands.add_parser(
        "assess", help="grade the submissions not graded yet")
    assess.add_argument("exercise")
    assess.add_argument("--regrade", action="store_true",
                        help="grade again every student not finalized")
    assess.add_argument("--ids", nargs="+", metavar="ID",
                        help="only these students")
    assess.set_defaults(func=command_assess)

    report = commands.add_parser(
        "report", help="show the grades or export the reports")
    report.add_argument("exercise")
    report.add_argument("--export", action="store_true",
                        help="write a .md report per student")
    report.set_defaults(func=command_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
