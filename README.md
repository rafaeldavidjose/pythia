# Pythia

Local web app to grade Python submissions with tests. It runs each student's file, compares it with a reference solution and gives a grade and a report. I review and adjust everything in the browser before exporting. No language model is involved.

The interface and the code are in English. The reports students get are in Portuguese.

You need Python 3.10 or newer. There is nothing to install.

## Start

- Windows: double-click `start.bat`
- macOS: double-click `start.command`
- Anywhere else: `python grader.py`

Copy `students.example.csv` to `students.csv` and put your roster in it (`number;name;class`). `students.csv` and `data/` are git-ignored.

The browser opens at http://127.0.0.1:8765. Keep the terminal open while you use it. Everything is saved in `data/`.

## Try the example

The repo comes with a small exercise, `Exercise_1`, and five fake submissions in `examples/entrega1`. Copy `students.example.csv` to `students.csv`, start the app, pick `Exercise_1`, type `examples/entrega1` in the folder field and click **Import folder**, then **Grade new**.

You get one of each case: a copy of the solution (20), a valid alternative implementation (20), a file with typical mistakes, a syntax error and an infinite loop. Delete `exercises/Exercise_1` and `examples/` when you start with your own.

## Grading

1. Download the submissions from Moodle and unzip them into `submissions/entregaN`.
2. Pick the exercise. The folder field suggests `entregaN` from the number at the end of the exercise name (`Exercise_1` gives `entrega1`). Click **Import folder**. **Choose folders**, **Import zip** and drag and drop also work.
3. Click **Grade new**.
4. Open each student. You see every test of each criterion, numbered, with passed or failed, and the details of the failures. You can change the grade and add a comment, which goes in the report.
5. Click **Save** and tick **Finalized** when you are done with that student.
6. **Copy report for Moodle** copies the plain-text report.
7. **Export reports** writes a `.md` and/or `.pdf` per student (each report lists every test with passou, falhou or não executado) and a `_notas.csv` with all the grades. You get a zip, and the files are also kept in `data/<exercise>/reports`.

Each Moodle folder (`Full Name_123456_assignsubmission_file`) is one student. The full name is matched against the roster by first and last name, ignoring "de", "da", "dos" and so on. The number in the file name does not matter. If it belongs to someone else, the student page shows a warning. "unknown" means no match, so fix the name or number on that page.

**review** in the list means the file crashed or a test timed out, usually an infinite loop.

**Regrade** reruns the tests for everyone who is not finalized and resets their grades and comments. Finalized students are never touched.

## Adding an exercise

An exercise is a folder in `exercises/` with a rules file and, usually, the reference solution:

- `rules.json` lists what to test and how much each criterion is worth.
- `solution.py` is the reference solution. A test without an `expected` value is compared with what the solution returns. It is optional when every test has an `expected`.

Create it in the **Exercises** tab or copy the folder into `exercises/`. Saving with an existing name replaces the files. `exercises/Exercise_1` is a complete example to copy from.

```json
{
  "title": "Mini-projeto de avaliação",
  "load_inputs": ["sair"],
  "ai_trap": ["palavra_rara"],
  "criteria": [
    {
      "name": "soma",
      "points": 3,
      "description": "Devolve a soma de dois números.",
      "tests": [
        {"check": "call", "function": "soma", "args": [2, 3]},
        {"check": "call", "function": "soma", "args": [-1, 1],
         "expected": 0, "hint": "Os números podem ser negativos."}
      ]
    },
    {
      "name": "Ciclo do programa",
      "points": 4,
      "tests": [
        {"check": "program", "inputs": ["2", "3", "sair"],
         "contains": ["5"], "label": "programa: somar e sair"}
      ]
    }
  ]
}
```

Top level:

| Key | Meaning |
|---|---|
| `title` | Name shown in the report. |
| `load_inputs` | Answers given to `input()` when the file is loaded to collect its functions. |
| `ai_trap` | Optional words from a hidden instruction in the assignment, see below. |
| `criteria` | List of criteria. The points should add up to the maximum grade. |

Each criterion has `name`, `points` and `tests`, plus the optional `description`, `hint` (used when a test fails and has no hint of its own) and `review` (true flags it for manual checking).

A test has a `check` and its parameters. Every test also takes `weight` (default 1), `hint` and `label` (the text shown in the report, which has a default).

`"check": "call"` calls the student's function and the solution's with the same arguments:

| Parameter | Meaning |
|---|---|
| `function` | Name of the function. Required. |
| `args` | List of arguments. |
| `expected` | Value the function must return. Without it, the return value is compared with the solution's. |
| `check_return` | `false` to ignore the return value. |
| `output` | `"equal"` compares what is printed with the solution's output. |
| `output_contains` | Phrases that must appear in what is printed. |
| `output_excludes` | Phrases that must not appear. |
| `mutates` | Argument positions (`[0]`) that must end up equal to the solution's after the call. |
| `inputs` | Answers given to `input()` during the call. |
| `names` | Names for list arguments in the report, like `{"0": "mapa"}`. |

`"check": "program"` runs the whole file with fixed answers to `input()`:

| Parameter | Meaning |
|---|---|
| `inputs` | Answers given to `input()`, in order. Required. |
| `contains` | Phrases that must appear in the output. |
| `excludes` | Phrases that must not appear. |
| `must_finish` | `true` by default. The program cannot ask for more input than given. |

JSON has no tuples, so a tuple argument is written as a list. Tuples and lists count as equal when comparing, and phrases ignore case, accents and extra spaces, so a valid alternative solution is not penalised. A criterion's grade is the share of passing tests (by weight), rounded to 0.25.

`hint`, `label` and `description` are shown to students, so write them in Portuguese.

A wrong file is reported in the Exercises tab with the criterion and test that has the problem, for example an unknown key or a missing `expected`.

`ai_trap` lists words from a hidden instruction in the assignment. If the code contains one, the list shows "possible AI" and the student page shows the lines. It never changes the grade or the report.

### When JSON is not enough

An exercise can use a `criteria.py` instead of `rules.json`, written with the helpers in `checks.py` (`criterion`, `call`, `program`, `named`). It takes the same parameters as keyword arguments and lets you share values or build tests in a loop. It needs a `solution.py`. If both files exist, `rules.json` wins.

```python
from checks import call, criterion

TITLE = "Mini-projeto de avaliação"
LOAD_INPUTS = ["sair"]

CRITERIA = [
    criterion("soma", 3, [
        call("soma", 2, 3),
        call("soma", -1, 1, expected=0),
    ]),
]
```

## Safety

Student code runs in a separate process, in a temporary folder, with a time limit. It is still someone else's code running on your machine.
