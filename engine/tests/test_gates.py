"""engine.gates — §7 pre-scoring gates and §12.1 liquidity vetoes. Every
check must return a definite GateCheck even on missing inputs, and it must
default to NOT PASSED, never a silent pass (ADR 0004's rule, applied here to
every gate, not only liquidity)."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.gates import (
    LiquidityVetoInputs,
    PreScoringGateInputs,
    all_passed,
    binary_event_gate,
    catalyst_duration_gate,
    dte_gate,
    evaluate_liquidity_vetoes,
    evaluate_pre_scoring_gates,
    failing,
    governance_risk_gate,
    iv_local_outlier_gate,
    marketable_limit_gate,
    open_interest_gate,
    premium_vs_fair_value_gate,
    quote_age_gate,
    single_variable_dependency_gate,
    spread_gate,
    valuation_insanity_gate,
    volume_gate,
)

CFG = load_config(TEMPLATE_PATH)


class BinaryEventGateTests(unittest.TestCase):
    def test_outside_blackout_passes(self):
        self.assertTrue(binary_event_gate(20, CFG).passed)

    def test_inside_blackout_fails(self):
        self.assertFalse(binary_event_gate(6, CFG).passed)

    def test_exactly_at_blackout_boundary_fails(self):
        # "within 14 calendar days" -- 14 itself does not clear the window.
        self.assertFalse(binary_event_gate(14, CFG).passed)

    def test_unknown_date_fails_closed(self):
        self.assertFalse(binary_event_gate(None, CFG).passed)


class ValuationInsanityGateTests(unittest.TestCase):
    def test_profitable_always_passes(self):
        self.assertTrue(valuation_insanity_gate(False, 90.0, None, CFG).passed)

    def test_unprofitable_below_ps_cap_passes(self):
        self.assertTrue(valuation_insanity_gate(True, 30.0, None, CFG).passed)

    def test_unprofitable_above_cap_without_fcf_path_fails(self):
        self.assertFalse(valuation_insanity_gate(True, 80.0, False, CFG).passed)

    def test_unprofitable_above_cap_with_credible_fcf_path_passes(self):
        self.assertTrue(valuation_insanity_gate(True, 80.0, True, CFG).passed)

    def test_missing_profitability_data_fails_closed(self):
        self.assertFalse(valuation_insanity_gate(None, None, None, CFG).passed)

    def test_missing_ps_when_unprofitable_fails_closed(self):
        self.assertFalse(valuation_insanity_gate(True, None, True, CFG).passed)


class JudgmentGateTests(unittest.TestCase):
    def test_single_variable_dependency(self):
        self.assertTrue(single_variable_dependency_gate(False).passed)
        self.assertFalse(single_variable_dependency_gate(True).passed)
        self.assertFalse(single_variable_dependency_gate(None).passed)

    def test_governance_risk(self):
        self.assertTrue(governance_risk_gate(False).passed)
        self.assertFalse(governance_risk_gate(True).passed)
        self.assertFalse(governance_risk_gate(None).passed)

    def test_catalyst_duration(self):
        self.assertTrue(catalyst_duration_gate(300, 500).passed)
        self.assertFalse(catalyst_duration_gate(600, 500).passed)
        self.assertFalse(catalyst_duration_gate(None, 500).passed)


class PreScoringOrchestrationTests(unittest.TestCase):
    def test_all_clean_inputs_pass(self):
        inputs = PreScoringGateInputs(
            days_to_next_binary_event=90,
            is_unprofitable=False,
            depends_on_single_variable=False,
            catalyst_horizon_days=200,
            option_dte_days=500,
            unresolved_accounting_or_governance_risk=False,
        )
        self.assertTrue(all_passed(evaluate_pre_scoring_gates(CFG, inputs)))

    def test_unassessed_inputs_do_not_silently_pass(self):
        checks = evaluate_pre_scoring_gates(CFG, PreScoringGateInputs())
        self.assertFalse(all_passed(checks))
        self.assertEqual(len(failing(checks)), 5)  # every judgment-dependent gate unresolved


class LiquidityVetoTests(unittest.TestCase):
    def test_dte_gate(self):
        self.assertTrue(dte_gate(500, CFG).passed)
        self.assertFalse(dte_gate(300, CFG).passed)
        self.assertFalse(dte_gate(1000, CFG).passed)

    def test_quote_age_gate(self):
        self.assertTrue(quote_age_gate(45, CFG).passed)
        self.assertFalse(quote_age_gate(90, CFG).passed)

    def test_spread_gate_matches_the_2026_09_03_crm_quote(self):
        # Real Jan-2028 $230 CRM call captured in Phase 0: ask 78.95, bid
        # 75.60 -> 4.34% spread, under the 6% cap.
        r = spread_gate(75.60, 78.95, CFG)
        self.assertTrue(r.passed)
        self.assertAlmostEqual(float(r.reason.split("%")[0]), 4.34, places=1)

    def test_spread_gate_rejects_wide_spread(self):
        self.assertFalse(spread_gate(70.0, 79.0, CFG).passed)  # ~12%

    def test_open_interest_gate(self):
        self.assertTrue(open_interest_gate(720, CFG).passed)  # the same CRM contract
        self.assertFalse(open_interest_gate(113, CFG).passed)  # 2026-07 INTU chain, per project history

    def test_volume_gate_unavailable_fails_closed(self):
        self.assertFalse(volume_gate(None, CFG).passed)
        self.assertTrue(volume_gate(15, CFG).passed)

    def test_marketable_limit_gate_needs_both_inputs(self):
        self.assertFalse(marketable_limit_gate(None, 79.0).passed)
        self.assertFalse(marketable_limit_gate(80.0, None).passed)
        self.assertTrue(marketable_limit_gate(80.0, 79.0).passed)
        self.assertFalse(marketable_limit_gate(78.0, 79.0).passed)

    def test_iv_outlier_gate(self):
        self.assertTrue(iv_local_outlier_gate(0.44, [0.42, 0.43, 0.45, 0.46]).passed)
        self.assertFalse(iv_local_outlier_gate(0.90, [0.42, 0.43, 0.45, 0.46]).passed)
        self.assertFalse(iv_local_outlier_gate(None, [0.42, 0.43]).passed)
        self.assertFalse(iv_local_outlier_gate(0.44, [0.42]).passed)

    def test_premium_vs_fair_value_pending_phase_3(self):
        r = premium_vs_fair_value_gate(80.0, None, CFG)
        self.assertFalse(r.passed)
        self.assertIn("Phase 3", r.reason)

    def test_premium_vs_fair_value_within_bound(self):
        self.assertTrue(premium_vs_fair_value_gate(80.0, 75.0, CFG).passed)  # +6.7%

    def test_premium_vs_fair_value_exceeds_bound(self):
        self.assertFalse(premium_vs_fair_value_gate(90.0, 75.0, CFG).passed)  # +20%


class LiquidityOrchestrationTests(unittest.TestCase):
    def test_real_crm_contract_clears_the_fully_available_checks(self):
        # Phase 0's captured live quote, minus the two Phase-3-dependent
        # checks (fair value, modeled entry cost) which correctly stay
        # unresolved until engine.optmodel exists.
        inputs = LiquidityVetoInputs(
            dte_days=505,
            quote_age_seconds=5,
            bid=75.60,
            ask=78.95,
            open_interest=720,
            entry_premium=78.95,
            median_20d_volume=8,
            strike_iv=0.4374,
            neighbor_ivs=[0.41, 0.43, 0.45],
        )
        checks = evaluate_liquidity_vetoes(CFG, inputs)
        names_failing = {c.name for c in failing(checks)}
        self.assertEqual(
            names_failing,
            {"volume_20d_median", "marketable_limit_fill", "premium_vs_fair_value"},
        )


if __name__ == "__main__":
    unittest.main()
