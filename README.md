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
4. Open each student. You see the tests that passed and failed for every criterion. You can change the grade and add a comment, which goes in the report.
5. Click **Save** and tick **Finalized** when you are done with that student.
6. **Copy report for Moodle** copies the plain-text report.
7. **Export reports** writes a `.md` and/or `.pdf` per student and a `_notas.csv` with all the grades. You get a zip, and the files are also kept in `data/<exercise>/reports`.

Each Moodle folder (`Full Name_123456_assignsubmission_file`) is one student. The full name is matched against the roster by first and last name, ignoring "de", "da", "dos" and so on. The number in the file name does not matter. If it belongs to someone else, the student page shows a warning. "unknown" means no match, so fix the name or number on that page.

**review** in the list means the file crashed or a test timed out, usually an infinite loop.

**Regrade** reruns the tests for everyone who is not finalized and resets their grades and comments. Finalized students are never touched.

## Adding an exercise

An exercise is a folder in `exercises/` with two files:

- `solution.py` is the reference solution. The tests compare the student's code with it.
- `criteria.py` says what to test and how much each criterion is worth.

Create it in the **Exercises** tab or copy the folder into `exercises/`. Saving with an existing name replaces the files. `exercises/Exercise_1` is a complete example to copy from.

```python
from checks import call, criterion, named, program

TITLE = "Mini-projeto de avaliação"
LOAD_INPUTS = ["sair"]      # answers to input() when the file is loaded
AI_TRAP = ["palavra_rara"]  # optional, see below

CRITERIA = [
    criterion("soma", 3, [
        call("soma", 2, 3),
        call("soma", -1, 1,
             hint="Os números podem ser negativos."),
    ], description="Devolve a soma de dois números."),

    criterion("Ciclo do programa", 4, [
        program(["2", "3", "sair"], contains=["5"],
                label="programa: somar e sair"),
    ]),
]
```

There are two kinds of test:

- `call(func, *args)` calls the student's function and the solution's with the same arguments and compares the return values. Options: `output="equal"` compares what is printed, `output_contains` and `output_excludes` check the output, `mutates=[0]` compares a list argument after the call, `inputs` feeds `input()`.
- `program(inputs, contains=[...])` runs the whole file with those answers to `input()` and looks for the phrases in the output. The program has to finish without asking for more input.

A criterion's grade is the share of passing tests, weighted and rounded to 0.25. Tuples and lists count as equal, and phrases ignore case, accents and extra spaces, so a valid alternative solution is not penalised.

`hint`, `label` and `description` are shown to students, so write them in Portuguese. `named(value, "mapa")` makes a value show up as `mapa` in the report messages.

`AI_TRAP` is a list of words from a hidden instruction in the assignment. If the code contains one, the list shows "possible AI" and the student page shows the lines. It never changes the grade or the report.

## Safety

Student code runs in a separate process, in a temporary folder, with a time limit. It is still someone else's code running on your machine.
