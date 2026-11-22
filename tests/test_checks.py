"""Tests for checks.py: every check, the comparisons and the check info."""

import unittest

import checks
from tests.helpers import TempDirTestCase

SOLUTION = """
def dobro(x):
    return 2 * x


def ponto():
    return (1, 2)


def media(notas):
    return sum(notas) / len(notas) if notas else 0


def saudar(nome):
    print(f"Olá, {nome}!")


def subir(notas, bonus):
    for i in range(len(notas)):
        notas[i] = min(notas[i] + bonus, 20)


def perguntar():
    return input("Idade? ")


def limpar(mapa):
    mapa[0][0] = "."


def andar(mapa, passos):
    print("A andar")
    if mapa:
        mapa[0][0] = "P"
    return passos * 2


nome = input("Nome: ")
print(f"Bem-vindo, {nome}")
"""


class CheckTestCase(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.solution = self.load(SOLUTION, ["Ana"], "solucao.py")

    def check(self, name: str, source: str, **params: object) -> list[dict]:
        student = self.load(source, ["Ana"])
        return checks.available()[name](student, self.solution, **params)

    def messages(self, name: str, source: str, **params: object) -> list[str]:
        return [failure["message"]
                for failure in self.check(name, source, **params)]


class ReturnsTest(CheckTestCase):
    def test_passes_when_equal_to_the_solution(self) -> None:
        self.assertEqual(self.check("returns", SOLUTION,
                                    function="dobro", args=[3]), [])

    def test_reports_expected_and_obtained(self) -> None:
        source = "def dobro(x):\n    return x + 2\n"
        self.assertEqual(self.messages("returns", source,
                                       function="dobro", args=[3]),
                         ["esperado 6, obtido 5"])

    def test_expected_param_replaces_the_solution(self) -> None:
        self.assertEqual(
            self.messages("returns", SOLUTION, function="dobro", args=[3],
                          expected=7),
            ["esperado 7, obtido 6"])

    def test_expected_can_be_none(self) -> None:
        self.assertEqual(self.check("returns", SOLUTION, function="subir",
                                    args=[[1], 1], expected=None), [])

    def test_tuples_and_lists_are_equal(self) -> None:
        source = "def ponto():\n    return [1, 2]\n"
        self.assertEqual(self.check("returns", source, function="ponto"), [])

    def test_missing_function(self) -> None:
        with self.assertRaisesRegex(checks.Failed,
                                    "função dobro não encontrada"):
            self.check("returns", "x = 1\n", function="dobro", args=[1])

    def test_error_in_the_function_names_the_line(self) -> None:
        source = "def dobro(x):\n    return x / 0\n"
        with self.assertRaises(checks.Failed) as caught:
            self.check("returns", source, function="dobro", args=[1])
        self.assertEqual(str(caught.exception),
                         "erro ZeroDivisionError: division by zero (linha 2)")

    def test_each_side_gets_its_own_copy_of_the_args(self) -> None:
        source = ("def media(notas):\n"
                  "    notas.append(0)\n"
                  "    return sum(notas) / len(notas)\n")
        args = [[10, 20]]
        self.assertEqual(self.messages("returns", source, function="media",
                                       args=args),
                         ["esperado 15.0, obtido 10.0"])
        self.assertEqual(args, [[10, 20]])

    def test_inputs_answer_input(self) -> None:
        self.assertEqual(self.check("returns", SOLUTION, function="perguntar",
                                    inputs=["20"]), [])

    def test_asking_for_more_input_fails(self) -> None:
        source = "def perguntar():\n    return input() + input()\n"
        with self.assertRaisesRegex(checks.Failed, "pediu mais entradas"):
            self.check("returns", source, function="perguntar",
                       inputs=["20"])

    def test_solution_without_the_function_is_a_rules_error(self) -> None:
        source = "def triplo(x):\n    return 3 * x\n"
        with self.assertRaisesRegex(checks.RulesError,
                                    "solução de referência"):
            self.check("returns", source, function="triplo", args=[1])


class PrintsTest(CheckTestCase):
    def test_ignores_case_accents_and_spaces(self) -> None:
        source = "def saudar(nome):\n    print('OLA,  ' + nome + ' !')\n"
        self.assertEqual(self.check("prints", source, function="saudar",
                                    args=["Ana"]), [])

    def test_different_output_shows_both(self) -> None:
        source = "def saudar(nome):\n    print('Oi', nome)\n"
        failures = self.check("prints", source, function="saudar",
                              args=["Ana"])
        self.assertEqual(failures, [{
            "message": "saída diferente da esperada",
            "expected_output": "Olá, Ana!",
            "actual_output": "Oi Ana",
        }])

    def test_no_output_is_named(self) -> None:
        source = "def saudar(nome):\n    pass\n"
        failures = self.check("prints", source, function="saudar",
                              args=["Ana"])
        self.assertEqual(failures[0]["actual_output"], "(sem saída)")

    def test_expected_text(self) -> None:
        self.assertEqual(self.check("prints", SOLUTION, function="saudar",
                                    args=["Rui"], expected="Olá, Rui!"), [])

    def test_contains_alone_only_looks_for_the_phrases(self) -> None:
        source = "def saudar(nome):\n    print('Bom dia', nome)\n"
        self.assertEqual(self.check("prints", source, function="saudar",
                                    args=["Ana"], contains=["ana"]), [])

    def test_excludes(self) -> None:
        source = "def saudar(nome):\n    print('erro', nome)\n"
        self.assertEqual(
            self.messages("prints", source, function="saudar", args=["Ana"],
                          excludes=["erro"]),
            ['a saída contém "erro" (não devia)'])

    def test_contains_with_expected_checks_both(self) -> None:
        source = "def saudar(nome):\n    print('Oi', nome)\n"
        self.assertEqual(
            self.messages("prints", source, function="saudar", args=["Ana"],
                          expected="Olá, Ana!", contains=["olá"]),
            ["saída diferente da esperada", 'a saída não contém "olá"'])


class MutatesTest(CheckTestCase):
    def test_changing_the_list_in_place_passes(self) -> None:
        self.assertEqual(self.check("mutates", SOLUTION, function="subir",
                                    args=[[10, 12], 2]), [])

    def test_returning_a_new_list_fails(self) -> None:
        source = ("def subir(notas, bonus):\n"
                  "    return [nota + bonus for nota in notas]\n")
        self.assertEqual(
            self.messages("mutates", source, function="subir",
                          args=[[10, 12], 2], names={"0": "notas"}),
            ["depois da chamada, notas = [10, 12], esperado [12, 14]"])

    def test_default_argument_name(self) -> None:
        source = "def subir(notas, bonus):\n    pass\n"
        message = self.messages("mutates", source, function="subir",
                                args=[[10], 2])[0]
        self.assertIn("argumento 1 = [10]", message)

    def test_grids_show_the_cells_that_differ(self) -> None:
        source = "def limpar(mapa):\n    mapa[1][1] = '.'\n"
        message = self.messages(
            "mutates", source, function="limpar",
            args=[[["#", "#"], ["#", "#"]]], names={"0": "mapa"})[0]
        self.assertIn("mapa[0][0] = '#', esperado '.'", message)
        self.assertIn("mapa[1][1] = '.', esperado '#'", message)

    def test_expected_param(self) -> None:
        self.assertEqual(self.check("mutates", SOLUTION, function="subir",
                                    args=[[18, 20], 5], expected=[20, 20]),
                         [])

    def test_position_outside_the_args(self) -> None:
        with self.assertRaises(checks.RulesError):
            self.check("mutates", SOLUTION, function="subir",
                       args=[[1], 1], position=2)


class CallTest(CheckTestCase):
    def test_passes_when_everything_matches(self) -> None:
        self.assertEqual(self.check("call", SOLUTION, function="andar",
                                    args=[[["."]], 3], same_output=True,
                                    mutates=[0]), [])

    def test_lists_every_problem_in_one_test(self) -> None:
        source = ("def andar(mapa, passos):\n"
                  "    print('Parado')\n"
                  "    return passos\n")
        self.assertEqual(
            self.messages("call", source, function="andar",
                          args=[[["."]], 3], same_output=True,
                          contains=["a andar"], mutates=[0],
                          names={"0": "mapa"}),
            ["esperado 6, obtido 3", "saída diferente da esperada",
             'a saída não contém "a andar"',
             "depois da chamada, mapa[0][0] = '.', esperado 'P'"])

    def test_one_wrong_part_fails_the_test(self) -> None:
        source = ("def andar(mapa, passos):\n"
                  "    print('A andar')\n"
                  "    return passos * 2\n")
        self.assertEqual(self.messages("call", source, function="andar",
                                       args=[[["."]], 3], mutates=[0]),
                         ["depois da chamada, argumento 1[0][0] = '.', "
                          "esperado 'P'"])

    def test_return_value_can_be_ignored_or_given(self) -> None:
        source = "def andar(mapa, passos):\n    return 0\n"
        self.assertEqual(self.check("call", source, function="andar",
                                    args=[[], 1], check_return=False), [])
        self.assertEqual(self.check("call", source, function="andar",
                                    args=[[], 1], expected=0), [])

    def test_solution_is_only_used_when_needed(self) -> None:
        source = "def extra():\n    print('olá')\n"
        self.assertEqual(self.check("call", source, function="extra",
                                    check_return=False, contains=["ola"]),
                         [])


class ProgramTest(CheckTestCase):
    def test_finds_the_phrases(self) -> None:
        self.assertEqual(self.check("program", SOLUTION, inputs=["Rui"],
                                    contains=["bem-vindo, rui"]), [])

    def test_missing_phrase(self) -> None:
        self.assertEqual(self.messages("program", SOLUTION, inputs=["Rui"],
                                       contains=["adeus"]),
                         ['a saída não contém "adeus"'])

    def test_excluded_phrase(self) -> None:
        self.assertEqual(self.messages("program", SOLUTION, inputs=["Rui"],
                                       excludes=["bem-vindo"]),
                         ['a saída contém "bem-vindo" (não devia)'])

    def test_failure_shows_both_outputs(self) -> None:
        failures = self.check("program", "nome = input('Nome: ')\n"
                              "print('Ola', nome)\n", inputs=["Rui"],
                              contains=["bem-vindo"])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["actual_output"], "Nome: Rui\nOla Rui")
        self.assertEqual(failures[0]["expected_output"],
                         "Nome: Rui\nBem-vindo, Rui")

    def test_passing_program_has_no_output(self) -> None:
        self.assertEqual(self.check("program", SOLUTION, inputs=["Rui"],
                                    contains=["rui"]), [])

    def test_long_output_is_clipped(self) -> None:
        text = checks._clip("\n".join(str(n) for n in range(100)))
        lines = text.splitlines()
        self.assertEqual(lines[:2], ["0", "1"])
        self.assertEqual(lines[10], "... (60 linhas) ...")
        self.assertEqual(lines[-1], "99")

    def test_must_finish(self) -> None:
        self.assertEqual(self.messages("program", SOLUTION),
                         ["o programa não terminou (pediu mais entradas)"])
        self.assertEqual(self.check("program", SOLUTION, must_finish=False),
                         [])

    def test_error_while_running(self) -> None:
        messages = self.messages("program", "x = int(input())\n",
                                 inputs=["abc"])
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].startswith("erro ValueError"))
        self.assertTrue(messages[0].endswith("(linha 1)"))

    def test_file_with_syntax_error(self) -> None:
        with self.assertRaisesRegex(checks.Failed, "o ficheiro não corre"):
            self.check("program", "def (:\n", inputs=["x"])


class DefinesTest(CheckTestCase):
    def test_defined_function(self) -> None:
        self.assertEqual(self.check("defines", SOLUTION, function="dobro"),
                         [])

    def test_missing_or_not_a_function(self) -> None:
        self.assertEqual(self.messages("defines", "dobro = 2\n",
                                       function="dobro"),
                         ["função dobro não encontrada"])


class ComparisonTest(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(checks.normalize("  Olá   MUNDO\n"), "ola mundo")

    def test_normalized_lines_skip_blank_lines_and_spaces(self) -> None:
        self.assertEqual(checks.normalized_lines("A b\n\n  C  \n"),
                         ["ab", "c"])

    def test_same(self) -> None:
        self.assertTrue(checks.same((1, [2, 3]), [1, (2, 3)]))
        self.assertTrue(checks.same(0.1 + 0.2, 0.3))
        self.assertTrue(checks.same(1, 1.0))
        self.assertTrue(checks.same({"a": (1,)}, {"a": [1]}))
        self.assertFalse(checks.same(True, 1))
        self.assertFalse(checks.same([1, 2], [2, 1]))
        self.assertTrue(checks.same(None, None))

    def test_same_never_raises(self) -> None:
        class Broken:
            def __eq__(self, other: object) -> bool:
                raise RuntimeError()

        self.assertFalse(checks.same(Broken(), 1))

    def test_show_shortens_long_values(self) -> None:
        text = checks.show(list(range(100)))
        self.assertEqual(len(text), 120)
        self.assertTrue(text.endswith("..."))

    def test_differences(self) -> None:
        self.assertEqual(checks.differences(1, 2, "x"), "x = 1, esperado 2")
        self.assertEqual(checks.differences([[1]], [[1, 2]], "m"),
                         "m[0] tem um tamanho diferente do esperado")
        many = checks.differences([[0] * 5], [[1] * 5], "m")
        self.assertTrue(many.endswith("; ..."))
        self.assertEqual(many.count("esperado"), 3)

    def test_decode_turns_markers_into_tuples(self) -> None:
        self.assertEqual(checks.decode([{"$tuple": [1, {"$tuple": [2]}]}]),
                         [(1, (2,))])
        mixed = {"$tuple": [1], "x": 2}
        self.assertEqual(checks.decode(mixed), mixed)

    def test_decode_turns_markers_into_sets(self) -> None:
        self.assertEqual(checks.decode({"v": {"$set": ["a", "b", "a"]}}),
                         {"v": {"a", "b"}})

    def test_sets_are_shown_sorted(self) -> None:
        self.assertEqual(checks.show({"b", "a"}), "{'a', 'b'}")
        self.assertEqual(checks.show(set()), "set()")
        self.assertEqual(checks.show({"x": {2, 1}}), "{'x': {1, 2}}")


class CheckInfoTest(unittest.TestCase):
    def test_available_checks(self) -> None:
        self.assertEqual(list(checks.available()),
                         ["returns", "prints", "mutates", "call", "program",
                          "defines"])

    def test_every_check_has_a_summary(self) -> None:
        for name in checks.available():
            self.assertTrue(checks.summary(name).endswith("."), name)

    def test_parameters_leave_out_student_and_solution(self) -> None:
        names = [parameter.name for parameter in checks.parameters("defines")]
        self.assertEqual(names, ["function"])

    def test_describe_parameters(self) -> None:
        returns = checks.describe_parameters("returns")
        self.assertIn("function", returns)
        self.assertIn("args=[]", returns)
        self.assertIn("expected=(from solution.py)", returns)
        self.assertIn("names=(none)", returns)
        self.assertIn("must_finish=true",
                      checks.describe_parameters("program"))

    def test_needs_solution(self) -> None:
        self.assertTrue(checks.needs_solution("returns", {}))
        self.assertFalse(checks.needs_solution("returns", {"expected": 1}))
        self.assertTrue(checks.needs_solution("mutates", {}))
        self.assertTrue(checks.needs_solution("prints", {}))
        self.assertFalse(checks.needs_solution("prints", {"contains": ["a"]}))
        self.assertFalse(checks.needs_solution("program", {}))
        self.assertTrue(checks.needs_solution("call", {}))
        self.assertFalse(checks.needs_solution("call", {"expected": 1}))
        self.assertTrue(checks.needs_solution(
            "call", {"expected": 1, "mutates": [0]}))
        self.assertTrue(checks.needs_solution(
            "call", {"check_return": False, "same_output": True}))
        self.assertFalse(checks.needs_solution(
            "call", {"check_return": False, "contains": ["x"]}))
        self.assertFalse(checks.needs_solution("defines", {}))

    def test_default_labels(self) -> None:
        label = checks.default_label
        self.assertEqual(label("returns", {"function": "media",
                                           "args": [[10, 12]]}),
                         "media([10, 12])")
        self.assertEqual(label("returns", {"function": "f",
                                           "args": [list(range(30))]}),
                         "f([...])")
        self.assertEqual(label("mutates", {"function": "f", "args": [[1], 2],
                                           "names": {"0": "mapa"}}),
                         "f(mapa, 2): mapa depois da chamada")
        self.assertEqual(label("mutates", {"function": "f", "args": [1, []],
                                           "position": 1}),
                         "f(1, []): argumento 2 depois da chamada")
        self.assertEqual(label("prints", {"function": "f", "args": ["Ana"]}),
                         "f('Ana'): saída")
        self.assertEqual(label("returns", {"function": "f",
                                           "args": [(1, 2)]}),
                         "f((1, 2))")
        self.assertEqual(label("program", {"inputs": ["1", 2]}),
                         "programa com as entradas 1, 2")
        self.assertEqual(label("program", {}), "programa sem entradas")
        self.assertEqual(label("defines", {"function": "f"}),
                         "função f definida")


if __name__ == "__main__":
    unittest.main()
