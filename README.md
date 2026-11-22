# Pythia

Grades Python exercises with tests. Each student's file runs in its own process and goes through the tests in the exercise's `rules.json`. Every test passes or fails, and each criterion's grade follows the tests that pass. No language model is involved. I review and adjust everything in the browser before exporting.

The interface and the code are in English. The reports students get are in Portuguese.

You need Python 3.10 or newer. There is nothing to install.

## How to use

- `python pythia.py` or `python pythia.py serve` opens the web interface at http://127.0.0.1:8765 (`--port`, `--no-browser`). On Windows you can double-click `start.bat`, on macOS `start.command`.
- `python pythia.py checks` lists the checks a `rules.json` can use, with their params.
- `python pythia.py validate EXERCISE` checks `rules.json` and grades `solution.py` with it. The solution has to pass every test.
- `python pythia.py import EXERCISE FOLDER` imports a folder of submissions.
- `python pythia.py assess EXERCISE` grades the submissions not graded yet. `--regrade` grades again everyone not finalized, `--ids` picks students.
- `python pythia.py report EXERCISE` prints the grades. `--export` writes a `.md` report per student and `_notas.csv` to `data/<exercise>/reports`.

The web interface and the command line share the same `data/` folder, so you can import and grade in the terminal and review in the browser.

Copy `students.example.csv` to `students.csv` and put your roster in it (`number;name`). Students are listed in alphabetical order. `students.csv`, `data/` and `submissions/` are git-ignored.

## Try the example

The repo comes with an exercise, `Exercise_1`, and five fake submissions in `examples/entrega1`. Copy `students.example.csv` to `students.csv` and run:

```text
python pythia.py validate Exercise_1
python pythia.py import Exercise_1 examples/entrega1
python pythia.py assess Exercise_1
python pythia.py report Exercise_1
```

You get one of each case: a copy of the solution (20), a valid alternative implementation (20), a file with typical mistakes (9,25), a syntax error (0) and an infinite loop (16,25). The last three are marked for review. Delete `exercises/Exercise_1` and `examples/` when you start with your own.

## Grading in the browser

1. Download the submissions from Moodle and unzip them into `submissions/entregaN`.
2. Pick the exercise. The folder field suggests `entregaN` from the number at the end of the exercise name (`Exercise_1` gives `entrega1`). Click **Import folder**. **Choose folders**, **Import zip** and drag and drop also work.
3. Click **Grade new**.
4. Open each student. Every criterion lists its tests, numbered, with passed, failed or not run, and under each failed test what went wrong. You can change the grade and add a comment, which goes in the report.
5. Click **Save** and tick **Finalized** when you are done with that student.
6. **Copy report for Moodle** copies the plain-text report.
7. **Export reports** writes a `.md` report per student and a `_notas.csv` with all the grades. You get a zip, and the files are also kept in `data/<exercise>/reports`.

Each Moodle folder (`Full Name_123456_assignsubmission_file`) is one student. A folder with no `.py` file, for example a file saved without the extension, still shows in the list: the student gets 0, every test shows as not run, and the student page lists the files that were handed in. The full name is matched against the roster by first and last name, ignoring "de", "da", "dos" and so on. The number in the file name does not matter. If it belongs to someone else, the student page shows a warning. "unknown" means no match, so fix the name or number on that page.

**review** in the list means the file crashed or a test timed out, usually an infinite loop.

**Regrade** reruns the tests for everyone who is not finalized and resets their grades and comments. Finalized students are never touched.

## Rules

An exercise is a folder in `exercises/` with `rules.json` and, usually, `solution.py`. Create it in the **Exercises** tab or copy the folder in. **Check rules** in that tab does the same as `validate`.

Like an egrader rules file, every test names a check, gives it a weight and passes it params:

```json
{
  "title": "Gestão de notas",
  "load_inputs": ["fim"],
  "criteria": [
    {
      "criterion": "media",
      "points": 4,
      "description": "Devolve a média das notas, ou 0 se a lista é vazia.",
      "tests": [
        {"name": "returns",
         "params": {"function": "media", "args": [[10, 12, 14]]}},
        {"name": "returns", "weight": 2,
         "params": {"function": "media", "args": [[]], "expected": 0},
         "hint": "Uma lista vazia tem média 0."}
      ]
    },
    {
      "criterion": "Programa",
      "points": 4,
      "tests": [
        {"name": "program",
         "params": {"inputs": ["12", "8", "fim"], "contains": ["Média: 10.0"]},
         "label": "programa: notas 12 e 8"}
      ]
    }
  ]
}
```

| Key | Where | Meaning |
|---|---|---|
| `title` | top | Name shown in the report. |
| `load_inputs` | top | Answers given to `input()` when the file is loaded to collect its functions. |
| `ai_trap` | top | Optional words from a hidden instruction in the assignment, see below. |
| `values` | top | Values used by many tests, like a map. A param written as `{"$value": "mapa"}` gets a copy of `values.mapa`. The report writes the value out, or calls it `mapa` when it is too long, like a 5x5 grid. |
| `criteria` | top | List of criteria. The points should add up to the maximum grade. |
| `criterion` | criterion | Name of the criterion. |
| `points` | criterion | What the criterion is worth. |
| `description` | criterion | What was asked, shown in the Exercises tab. |
| `hint` | criterion | Shown when a test fails and no test hint was shown. |
| `review` | criterion | `true` flags the criterion for manual checking. A criterion with no tests is graded by hand. |
| `tests` | criterion | List of tests. |
| `name` | test | The check to run. |
| `weight` | test | How much the test counts inside its criterion. 1 by default. |
| `params` | test | The check's params. |
| `hint` | test | Shown under the test when it fails. The same hint is shown once per criterion. |
| `label` | test | Text for the test in the report. By default it is the call, like `media([10, 12, 14])`, followed by `: output` for `prints` and `: notas depois da chamada` for `mutates`, since one call can have several tests. |

A criterion's grade is its points times the weight of the passing tests over the total weight, rounded to 0.25.

`hint`, `label` and `description` are shown to students, so write them in Portuguese.

A mistake in `rules.json` is reported with its place, for example `criterion 2 (media), test 3: check 'returns' has no param 'arg'`.

## Checks

| Check | What it does | Params |
|---|---|---|
| `returns` | Calls a function and compares the value it returns. | `function`, `args`, `expected`, `inputs`, `names` |
| `prints` | Calls a function and checks what it prints. | `function`, `args`, `expected`, `contains`, `excludes`, `inputs`, `names` |
| `mutates` | Calls a function and compares one of its arguments after the call. | `function`, `args`, `position`, `expected`, `inputs`, `names` |
| `call` | Calls a function and checks its value, output and arguments at once. The test passes only if all of them are right. | `function`, `args`, `expected`, `check_return`, `same_output`, `contains`, `excludes`, `mutates`, `inputs`, `names` |
| `program` | Runs the whole file with answers to `input()` and checks the output. | `inputs`, `contains`, `excludes`, `must_finish` |
| `defines` | Checks that the file defines a function with this name. | `function` |

| Param | Meaning |
|---|---|
| `function` | Name of the function. Required where it appears. |
| `args` | List of arguments. JSON has no tuples or sets, so write them as `{"$tuple": [0, 0]}` and `{"$set": ["vila", "floresta"]}`. |
| `expected` | The right answer. Without it, the check runs `solution.py` with the same arguments and uses its answer. For `prints` it is the whole output. |
| `inputs` | Answers given to `input()`, in order. |
| `names` | Names for list arguments in the report, like `{"0": "mapa"}`, so a big grid shows as `mapa`. An argument from `values` that is too long to write out already gets its name. |
| `contains` | Phrases that must appear in the output. With only `contains` or `excludes`, `prints` does not compare the whole output. |
| `excludes` | Phrases that must not appear. |
| `position` | Which argument `mutates` compares, counting from 0. |
| `check_return` | `call` only. `false` ignores the value returned. `true` by default. |
| `same_output` | `call` only. `true` compares what is printed with the solution's output. |
| `mutates` | `call` only. Argument positions, like `[0]`, that must end up equal to the solution's after the call. |
| `must_finish` | `program` only. The file cannot ask for more input than given. `true` by default. |

Tuples and lists count as equal, numbers are compared to 6 decimal places, and output ignores case and accents, so a valid alternative solution is not penalised. When the output is compared with the solution's, each line of the expected output has to be in the student's output, in the same order, and extra text or extra lines around it are fine. A line of text is looked for ignoring spaces and the marks `. , ; : ! ?`. A line with fewer than 3 letters, like a row of a map, has to be a whole line, ignoring only spaces, since its dots matter. A phrase in `contains` or `excludes` is looked for on each line of the output, and it also ignores spaces and the marks `. , ; : ! ?`, so `flecha:2` and `Flecha : 2.` both count as `flecha: 2`. `exit()` at the end of a program is fine.

Sets are compared as sets, so the order does not matter, but a list does not count as a set. Reports write sets in sorted order.

Without `solution.py` every `returns` and `mutates` test needs an `expected`, and so does `prints` unless it only looks for phrases.

### Adding a check

Checks work like egrader plugins. Each one is a function in `checks.py` named `check_<name>`:

```python
def check_returns(student, solution, function, args=(), expected=NOT_GIVEN,
                  inputs=(), names=None):
    """Call a function and compare the value it returns."""
```

It gets the student's and the solution's file already loaded, plus the params as keyword arguments, and returns the problems it found, in Portuguese. An empty list means the test passed. The first line of the docstring is what `python pythia.py checks` shows, and the params are checked against the function's signature, so a new check needs no other change. Add it to the table above too; a test makes sure every check and param is documented here.

## Reports

Reports follow the shape of an egrader report: nested lists of `key: value`, with the name of each test in code. The header has the exercise, the student and the grade. Each criterion has its grade, how many tests passed and every test with its result, and what went wrong goes under the tests that failed:

```text
## classificar

- Nota: 1,5 / 4
- Testes OK: 2 / 5
- Testes:
  - `classificar(15)`: OK
  - `classificar(10)`: FALHOU
    - esperado 'Aprovado', obtido 'Reprovado'
    - Explicação: 10 já é aprovado (>= 10).
  - `classificar(9.5)`: OK
  - `classificar(-1)`: FALHOU
    - esperado 'Inválida', obtido 'Reprovado'
    - Explicação: Fora de [0, 20] é inválida.
  - `classificar(21)`: FALHOU
    - esperado 'Inválida', obtido 'Aprovado'
```

When a `program` test fails, the report also lists the inputs it gave and shows what the student's program printed, with each answer to `input()` after its prompt, as in a terminal. A long output keeps its first 10 and last 30 lines.

A test that never ran, for example after a syntax error, shows as `NÃO CORREU`. A test with a weight other than 1 shows it next to the result. The plain-text version for Moodle has the same lines without the Markdown marks.

`ai_trap` lists words from a hidden instruction in the assignment. If the code contains one, the list shows "possible AI" and the student page shows the lines. It never changes the grade or the report.

## Tests

```text
python -m unittest
```

The tests use only the standard library. They cover every check, the rules file, importing, grading in a separate process (syntax errors, infinite loops, crashes), the reports, the command line and the web API, and the example above. They also check the repo itself: no line of Python over 80 characters, no long dash anywhere, and every check, param and command documented in this README.

## Safety

Student code runs in a separate process, in a temporary folder, with a time limit. It is still someone else's code running on your machine.
