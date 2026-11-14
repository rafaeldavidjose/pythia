# Pythia

Grades student submissions with automatic tests. Each student's code is run
and compared against a reference solution, and every criterion gets a grade
and a list of the tests that failed. No language model is involved. You
review and adjust everything before exporting.

The interface and code are in English. The reports students receive are in
Portuguese.

Requires Python 3.10 or newer. Nothing else to install.

## Start

- Windows: double-click `start.bat`
- macOS: double-click `start.command`
- Otherwise: `python grader.py`

Before the first run, copy `students.example.csv` to `students.csv` and put
your own roster in it (`number;name;class`). `students.csv` and `data/` are
git-ignored, so student data never ends up in the repository.

The browser opens at http://127.0.0.1:8765. The grader runs while the
terminal window stays open. Everything is saved in the `data` folder.

## Grading a submission

1. Download all submissions from Moodle and unzip them into
   `submissions/entregaN`.
2. Pick the exercise at the top. The folder field suggests `entregaN` from the
   exercise number (Exercise_1 suggests `entrega1`). Click
   **Import folder**. **Choose folders**, **Import zip** and drag and drop
   also work.
3. Click **Grade new**.
4. Open each student. Every criterion shows the tests that passed, the
   automatic grade and the failed tests. You can change the grade and add an
   optional comment, which appears in the report.
5. Click **Save** and tick **Finalized** once reviewed.
6. **Copy report for Moodle** copies the plain-text report.
7. **Export reports** writes one `.md` and/or `.pdf` per student plus a
   `_notas.csv` with all grades. They are downloaded as a zip and also saved
   in `data/<exercise>/reports`.

Each Moodle folder (`Full Name_123456_assignsubmission_file`) is one student.
The full name is matched against the short name in `students.csv` (first and
last name, ignoring "de", "da", "dos"...), so it does not depend on the number
the student typed in the file name. If that number belongs to someone else,
the student page shows a warning. "unknown" means no match was found; fix the
name or number on the student page.

**review** in the list means the file did not run to the end or a test timed
out (probably an infinite loop).

**Regrade** runs the tests again for every student not finalized and resets
their grades and comments. Finalized students are never touched.

## Adding an exercise

Each exercise is a folder in `exercises/` with two files:

- `solution.py`: the reference solution. Tests compare what the student's code
  does with what this file does.
- `criteria.py`: what to test and how much each criterion is worth.

Add one in the **Exercises** tab (enter the name, for example
`Exercise_2`, and choose both files) or copy the folder into `exercises/`.
Saving with an existing name replaces its files.

No exercises are included, you write your own. The structure of `criteria.py`:

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

Test types:

- `call(func, *args)` calls the student's function and the solution's with the
  same arguments. By default it compares the returned values. Useful options:
  `output="equal"` to compare what is printed, `output_contains=[...]`,
  `output_excludes=[...]`, `mutates=[0]` to compare a list argument after the
  call, `inputs=[...]` if the function calls input().
- `program(inputs, contains=[...])` runs the whole file with those answers to
  input() and looks for the phrases in the output. By default the program must
  finish without asking for more input.

Each criterion's grade is proportional to the tests that pass, rounded to
0.25. Tuples and lists compare as equal, and phrases ignore case, accents and
extra spaces, so valid alternative solutions are not penalised. `hint`,
`label` and `description` are shown to students, so write them in Portuguese.
`named(value, "mapa")` makes a value appear as `mapa` in the report messages.

`AI_TRAP` lists words from a hidden instruction in the assignment. If a
student's code contains one, the list shows "possible AI" and the student page
shows the lines. The grade and the report are not affected.

## Safety

Student code runs in a separate process, in a temporary folder, with a time
limit. It is still third-party code running on your computer.
