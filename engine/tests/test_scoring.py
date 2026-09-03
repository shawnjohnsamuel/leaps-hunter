"""engine.scoring — §11's sum + sub-gate + threshold aggregator."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.scoring import ScoreSheet, aggregate_score

CFG = load_config(TEMPLATE_PATH)

STRONG = ScoreSheet(
    thesis_fit=18, mispricing=18, fundamental_confirm=13, valuation_survival=13,
    option_implementation=13, positioning=4, catalyst_path=4, invalidation_clarity=5,
)  # totals 88


class AggregateScoreTests(unittest.TestCase):
    def test_totals_all_eight_dimensions(self):
        r = aggregate_score(CFG, STRONG, effective_threshold=75)
        self.assertEqual(r.total, 88)

    def test_clears_when_total_and_all_minimums_pass(self):
        r = aggregate_score(CFG, STRONG, effective_threshold=75)
        self.assertTrue(r.clears)

    def test_the_spec_own_example_88_total_11_thesis_fit_is_rejected(self):
        # S11: "A candidate that totals 88 but scores 11 on Thesis Fit is
        # REJECTED, not deployed" -- min for thesis_fit is 12.
        sheet = ScoreSheet(
            thesis_fit=11, mispricing=20, fundamental_confirm=15, valuation_survival=15,
            option_implementation=15, positioning=5, catalyst_path=4, invalidation_clarity=3,
        )  # totals 88, but invalidation_clarity=3 < min 5 too -- two failing sub-gates
        r = aggregate_score(CFG, sheet, effective_threshold=75)
        self.assertEqual(r.total, 88)
        self.assertFalse(r.passes_sub_gates)
        self.assertFalse(r.clears)
        failing = {g.dimension for g in r.sub_gates if not g.passed}
        self.assertEqual(failing, {"thesis_fit", "invalidation_clarity"})

    def test_restricted_regime_threshold_is_stricter(self):
        # A total of 78 clears the normal threshold (75) but not restricted (80).
        sheet = ScoreSheet(
            thesis_fit=15, mispricing=15, fundamental_confirm=13, valuation_survival=13,
            option_implementation=12, positioning=4, catalyst_path=3, invalidation_clarity=3,
        )  # totals 78
        normal = aggregate_score(CFG, sheet, effective_threshold=75)
        restricted = aggregate_score(CFG, sheet, effective_threshold=80)
        self.assertTrue(normal.passes_threshold)
        self.assertFalse(restricted.passes_threshold)

    def test_zero_minimum_dimensions_never_fail_their_sub_gate(self):
        sheet = ScoreSheet(
            thesis_fit=15, mispricing=15, fundamental_confirm=0, valuation_survival=0,
            option_implementation=12, positioning=0, catalyst_path=3, invalidation_clarity=5,
        )
        r = aggregate_score(CFG, sheet, effective_threshold=75)
        zero_min_dims = {"fundamental_confirm", "valuation_survival", "positioning"}
        for g in r.sub_gates:
            if g.dimension in zero_min_dims:
                self.assertTrue(g.passed)


if __name__ == "__main__":
    unittest.main()
