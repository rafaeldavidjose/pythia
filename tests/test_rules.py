"""Tests for rules.py: reading and checking rules.json."""

import json
import os
import unittest

import rules
from tests.helpers import EXAMPLE_EXERCISE


def one_test(test: dict, **criterion: object) -> str:
    """rules.json text with one criterion holding this test."""
    data = {"criteria": [{"criterion": "c", "points": 10, "tests": [test],
                          **criterion}]}
    return json.dumps(data)


def returns_test(**params: object) -> dict:
    return {"name": "returns", "params": {"function": "f", **params}}


class ExampleRulesTest(unittest.TestCase):
    def test_example_loads(self) -> None:
        path = os.path.join(EXAMPLE_EXERCISE, "rules.json")
        exercise = rules.load_rules(path, True)
        self.assertEqual(exercise["title"], "Gestão de notas")
        self.assertEqual(exercise["load_inputs"], ["fim"])
        self.assertEqual(exercise["ai_trap"], ["nota_secreta"])
        criteria = exercise["criteria"]
        self.assertEqual(len(criteria), 6)
        self.assertEqual(sum(criterion["points"] for criterion in criteria),
                         20)
        self.assertEqual(sum(len(criterion["tests"])
                             for criterion in criteria), 18)


class ParseRulesTest(unittest.TestCase):
    def parse(self, text: str, has_solution: bool = True) -> dict:
        return rules.parse_rules(text, has_solution)

    def assert_error(self, text: str, message: str,
                     has_solution: bool = True) -> None:
        with self.assertRaises(ValueError) as caught:
            self.parse(text, has_solution)
        self.assertIn(message, str(caught.exception))

    def test_defaults(self) -> None:
        exercise = self.parse(one_test(returns_test(args=[1])))
        self.assertEqual(exercise["title"], "")
        self.assertEqual(exercise["load_inputs"], [])
        criterion = exercise["criteria"][0]
        self.assertEqual(criterion["name"], "c")
        self.assertEqual(criterion["description"], "")
        self.assertFalse(criterion["review"])
        self.assertEqual(criterion["tests"][0], {
            "name": "returns", "params": {"function": "f", "args": [1]},
            "weight": 1, "hint": "", "label": "f(1)",
        })

    def test_label_hint_and_weight_are_kept(self) -> None:
        test = {**returns_test(), "label": "caso base", "hint": "Dica.",
                "weight": 2.5}
        kept = self.parse(one_test(test))["criteria"][0]["tests"][0]
        self.assertEqual((kept["label"], kept["hint"], kept["weight"]),
                         ("caso base", "Dica.", 2.5))

    def test_inputs_become_text(self) -> None:
        text = json.dumps({"load_inputs": [1, "fim"], "criteria": []})
        self.assertEqual(self.parse(text)["load_inputs"], ["1", "fim"])

    def test_criterion_without_tests_is_allowed(self) -> None:
        text = json.dumps({"criteria": [{"criterion": "Manual",
                                         "points": 2, "review": True}]})
        criterion = self.parse(text)["criteria"][0]
        self.assertEqual(criterion["tests"], [])
        self.assertTrue(criterion["review"])

    def test_invalid_json(self) -> None:
        self.assert_error('{"criteria": [}', "rules.json is not valid JSON")

    def test_top_level_must_be_an_object(self) -> None:
        self.assert_error("[]", "rules.json: expected an object")

    def test_unknown_top_level_key(self) -> None:
        self.assert_error('{"titulo": "x", "criteria": []}',
                          "unknown key 'titulo'")

    def test_missing_criteria(self) -> None:
        self.assert_error('{"title": "x"}', "missing 'criteria'")

    def test_unknown_criterion_key(self) -> None:
        text = json.dumps({"criteria": [{"name": "c", "points": 1}]})
        self.assert_error(text, "criterion 1: unknown key 'name'")

    def test_missing_criterion_name(self) -> None:
        self.assert_error('{"criteria": [{"points": 1}]}',
                          "criterion 1: missing 'criterion'")

    def test_points_must_be_a_number(self) -> None:
        for points in ('"4"', "true"):
            text = f'{{"criteria": [{{"criterion": "c", "points": {points}}}]}}'
            self.assert_error(text, "'points' must be a number")

    def test_duplicate_criteria(self) -> None:
        text = json.dumps({"criteria": [{"criterion": "c", "points": 1},
                                        {"criterion": "c", "points": 2}]})
        self.assert_error(text, "two criteria are called 'c'")

    def test_unknown_check(self) -> None:
        self.assert_error(one_test({"name": "retorna", "params": {}}),
                          "unknown check 'retorna' (checks: returns, ")

    def test_unknown_param(self) -> None:
        self.assert_error(one_test(returns_test(arg=[1])),
                          "check 'returns' has no param 'arg' "
                          "(params: function, args, ")

    def test_missing_required_param(self) -> None:
        self.assert_error(one_test({"name": "returns", "params": {}}),
                          "check 'returns' needs param 'function'")

    def test_param_types(self) -> None:
        cases = [
            (returns_test(args="x"), "'args' must be a list"),
            ({"name": "returns", "params": {"function": 3}},
             "'function' must be a string"),
            ({"name": "program", "params": {"must_finish": "sim"}},
             "'must_finish' must be true or false"),
            ({"name": "mutates",
              "params": {"function": "f", "args": [[1]], "position": "0"}},
             "'position' must be an integer"),
            ({"name": "returns", "params": []}, "'params' must be an object"),
        ]
        for test, message in cases:
            with self.subTest(message=message):
                self.assert_error(one_test(test), message)

    def test_position_must_be_one_of_the_args(self) -> None:
        test = {"name": "mutates",
                "params": {"function": "f", "args": [[1]], "position": 1}}
        self.assert_error(one_test(test), "position 1 is not one of the args")

    def test_call_positions(self) -> None:
        call = {"name": "call",
                "params": {"function": "f", "args": [[1]], "mutates": [1]}}
        self.assert_error(one_test(call), "position 1 is not one of the args")
        call["params"]["mutates"] = ["0"]
        self.assert_error(one_test(call), "'position' must be an integer")
        call["params"]["mutates"] = [0]
        self.parse(one_test(call))

    def test_weight(self) -> None:
        self.assert_error(one_test({**returns_test(), "weight": -1}),
                          "'weight' cannot be negative")
        self.assert_error(one_test({**returns_test(), "weight": "1"}),
                          "'weight' must be a number")

    def test_error_names_the_place_in_the_file(self) -> None:
        text = json.dumps({"criteria": [
            {"criterion": "a", "points": 1, "tests": []},
            {"criterion": "b", "points": 1, "tests": [
                returns_test(), returns_test(), {"name": "x"}]},
        ]})
        self.assert_error(text, "criterion 2 (b), test 3: unknown check 'x'")

    def test_without_solution_expected_is_needed(self) -> None:
        self.assert_error(one_test(returns_test(args=[1])),
                          "add 'expected' to the params", has_solution=False)
        self.parse(one_test(returns_test(args=[1], expected=2)), False)
        prints = {"name": "prints",
                  "params": {"function": "f", "contains": ["x"]}}
        self.parse(one_test(prints), False)
        self.parse(one_test({"name": "program", "params": {}}), False)

    def test_shared_values(self) -> None:
        grid = [["."] * 5 for _ in range(5)]
        small = [[".", "#"], ["T", "."]]
        text = json.dumps({"values": {"mapa": grid, "pequeno": small},
                           "criteria": [{"criterion": "c", "points": 1,
                                         "tests": [
            {"name": "mutates",
             "params": {"function": "f", "args": [{"$value": "mapa"}, 1]}},
            {"name": "returns",
             "params": {"function": "f", "args": [{"$value": "mapa"}, 2],
                        "names": {"0": "grelha"}}},
            {"name": "returns",
             "params": {"function": "f", "args": [{"$value": "pequeno"}]}},
            {"name": "program", "params": {"inputs": [], "contains": ["x"]}},
        ]}]})
        tests = self.parse(text)["criteria"][0]["tests"]
        self.assertEqual(tests[0]["params"]["args"], [grid, 1])
        self.assertEqual(tests[0]["params"]["names"], {"0": "mapa"})
        self.assertEqual(tests[0]["label"],
                         "f(mapa, 1): mapa depois da chamada")
        self.assertEqual(tests[1]["label"], "f(grelha, 2)")
        self.assertEqual(tests[2]["label"], f"f({small!r})")
        self.assertNotIn("names", tests[2]["params"])
        self.assertNotIn("names", tests[3]["params"])
        tests[0]["params"]["args"][0][0][0] = "changed"
        self.assertEqual(tests[1]["params"]["args"][0], grid)

    def test_unknown_or_invalid_values(self) -> None:
        self.assert_error(one_test(returns_test(args=[{"$value": "mapa"}])),
                          "unknown value 'mapa' (values: none)")
        self.assert_error('{"values": [], "criteria": []}',
                          "'values' must be an object")

    def test_tuple_marker_shows_in_the_label(self) -> None:
        test = returns_test(args=[{"$tuple": [0, 0]}])
        label = self.parse(one_test(test))["criteria"][0]["tests"][0]["label"]
        self.assertEqual(label, "f((0, 0))")


if __name__ == "__main__":
    unittest.main()
