"""Pin engine.yaml_lite's parsing semantics against a synthetic snippet,
independent of the real §20 content (see test_config.py for that)."""
import unittest

from engine import yaml_lite

SNIPPET = """\
version: 7.0
supersedes: [v4.0, v5.0, v8.0-draft]

portfolio:
  nav: null                # comment, stripped
  currency: USD
  note: 'quoted, with a comma, inside'

restricted_regime:
  trigger_R: 3
  minimum_deployment_floor: none
  kelly_multiplier_restricted: 0.125

scoring:
  thesis_fit: {points: 20, min: 12}
  positioning: {points: 5, min: null}

delta_policy:
  restricted: [0.70, 0.85]
  below_0_55: prohibited_unless_validated_template

flags:
  a: true
  b: false
  c: -5
"""


class YamlLiteTests(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml_lite.load(SNIPPET)

    def test_top_level_scalar_and_list(self):
        self.assertEqual(self.cfg["version"], 7.0)
        self.assertEqual(self.cfg["supersedes"], ["v4.0", "v5.0", "v8.0-draft"])

    def test_null_bool_string_and_comment_stripped(self):
        p = self.cfg["portfolio"]
        self.assertIsNone(p["nav"])
        self.assertEqual(p["currency"], "USD")

    def test_quoted_string_preserves_comma(self):
        self.assertEqual(self.cfg["portfolio"]["note"], "quoted, with a comma, inside")

    def test_bare_none_is_the_string_none_not_null(self):
        # Real YAML only treats null/Null/NULL/~/empty as null; a bare lowercase
        # "none" is a plain string. §20 relies on this (e.g. hard_gate_active: none).
        self.assertEqual(self.cfg["restricted_regime"]["minimum_deployment_floor"], "none")

    def test_nested_ints_and_floats(self):
        rr = self.cfg["restricted_regime"]
        self.assertEqual(rr["trigger_R"], 3)
        self.assertIsInstance(rr["trigger_R"], int)
        self.assertEqual(rr["kelly_multiplier_restricted"], 0.125)

    def test_flow_map(self):
        s = self.cfg["scoring"]
        self.assertEqual(s["thesis_fit"], {"points": 20, "min": 12})
        self.assertEqual(s["positioning"], {"points": 5, "min": None})

    def test_flow_list_of_floats(self):
        self.assertEqual(self.cfg["delta_policy"]["restricted"], [0.70, 0.85])
        self.assertEqual(
            self.cfg["delta_policy"]["below_0_55"], "prohibited_unless_validated_template"
        )

    def test_booleans_and_negative_int(self):
        f = self.cfg["flags"]
        self.assertIs(f["a"], True)
        self.assertIs(f["b"], False)
        self.assertEqual(f["c"], -5)
        self.assertIsInstance(f["c"], int)


if __name__ == "__main__":
    unittest.main()
