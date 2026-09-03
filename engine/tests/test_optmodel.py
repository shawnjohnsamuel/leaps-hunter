"""engine.optmodel — §12 pricing/scenarios and §13.1/13.2 structure rules."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.gates import all_passed, failing
from engine.optmodel import (
    Scenario,
    bs_call_delta,
    bs_call_price,
    evaluate_delta_policy,
    evaluate_scenarios,
    evaluate_spread_rule,
    executable_entry,
    executable_exit,
    stressed_spread_pct,
)

CFG = load_config(TEMPLATE_PATH)


class BlackScholesTests(unittest.TestCase):
    def test_reproduces_the_real_crm_quote_within_a_few_cents(self):
        # Phase 0's live CRM Jan-2028 $230 call, 2026-09-03: spot ~264.13,
        # strike 230, ~505 DTE, IV 0.4374, live delta 0.7431, mark 77.28.
        S, K, T, r, q, sigma = 264.13, 230.0, 505 / 365.0, 0.0417, 0.0, 0.4374
        price = bs_call_price(S, K, T, r, q, sigma)
        delta = bs_call_delta(S, K, T, r, q, sigma)
        self.assertAlmostEqual(price, 77.28, delta=3.0)
        self.assertAlmostEqual(delta, 0.7431, delta=0.03)

    def test_call_price_reduces_to_intrinsic_at_expiry(self):
        self.assertAlmostEqual(bs_call_price(120, 100, 0, 0.04, 0.0, 0.3), 20.0)
        self.assertEqual(bs_call_price(90, 100, 0, 0.04, 0.0, 0.3), 0.0)

    def test_delta_bounds(self):
        self.assertGreater(bs_call_delta(100, 100, 1.0, 0.04, 0.0, 0.3), 0.0)
        self.assertLess(bs_call_delta(100, 100, 1.0, 0.04, 0.0, 0.3), 1.0)
        # Deep ITM approaches delta 1; deep OTM approaches 0.
        self.assertGreater(bs_call_delta(300, 100, 1.0, 0.04, 0.0, 0.3), 0.95)
        self.assertLess(bs_call_delta(50, 100, 1.0, 0.04, 0.0, 0.3), 0.05)


class ExecutablePricingTests(unittest.TestCase):
    def test_entry_is_never_the_midpoint(self):
        entry = executable_entry(ask=78.95, bid=75.60, fees=0.0, cfg=CFG)
        midpoint = (78.95 + 75.60) / 2
        self.assertGreater(entry, midpoint)
        self.assertAlmostEqual(entry, 78.95 + 0.25 * (78.95 - 75.60))

    def test_stressed_spread_widens_under_iv_spike_and_drawdown(self):
        base = stressed_spread_pct(4.34, 0.44, 0.44, 264.13, 264.13, CFG)
        iv_spike = stressed_spread_pct(4.34, 0.44, 0.66, 264.13, 264.13, CFG)
        drawdown = stressed_spread_pct(4.34, 0.44, 0.44, 220.0, 264.13, CFG)
        self.assertAlmostEqual(base, 4.34)
        self.assertGreater(iv_spike, base)
        self.assertGreater(drawdown, base)

    def test_exit_price_floors_at_zero(self):
        exit_price = executable_exit(
            spot_scenario=50.0, strike=230.0, tau_remaining=0.1, r=0.04, q=0.0,
            sigma_exit=0.5, w0_pct=4.34, sigma_atm_now=0.44, sigma_atm_scenario=0.7,
            spot_now=264.13, dollar_spread_width=3.35, fees=0.0, cfg=CFG,
        )
        self.assertEqual(exit_price, 0.0)


class ScenarioModelTests(unittest.TestCase):
    def test_passes_acceptance_when_asymmetric_and_ev_positive(self):
        scenarios = [
            Scenario("bear", 0.25, 40.0),
            Scenario("base", 0.45, 90.0),
            Scenario("bull", 0.20, 160.0),
            Scenario("extreme_bull", 0.10, 220.0),
        ]
        r = evaluate_scenarios(CFG, entry_price=79.79, scenarios=scenarios)
        self.assertGreater(r.ev_net, 0)
        self.assertTrue(r.passes_ev_net)
        self.assertGreaterEqual(r.ev_to_el, 0.50)
        self.assertTrue(r.passes_ev_to_el)
        self.assertTrue(r.passes_acceptance)

    def test_fails_when_expected_loss_too_large_relative_to_ev(self):
        scenarios = [
            Scenario("bear", 0.40, 30.0),
            Scenario("base", 0.40, 85.0),
            Scenario("bull", 0.20, 100.0),
        ]
        r = evaluate_scenarios(CFG, entry_price=79.79, scenarios=scenarios)
        self.assertFalse(r.passes_ev_to_el)

    def test_undefined_ev_to_el_when_no_loss_scenarios(self):
        scenarios = [Scenario("base", 0.5, 90.0), Scenario("bull", 0.5, 120.0)]
        r = evaluate_scenarios(CFG, entry_price=79.79, scenarios=scenarios)
        self.assertIsNone(r.ev_to_el)
        self.assertFalse(r.passes_ev_to_el)


class DeltaPolicyTests(unittest.TestCase):
    def test_hard_gate_blocks_everything(self):
        r = evaluate_delta_policy(CFG, delta=0.80, hard_gate_active=True, restricted=False)
        self.assertFalse(r.permitted)
        self.assertEqual(r.band, "hard_gate_active")

    def test_normal_band(self):
        self.assertTrue(evaluate_delta_policy(CFG, 0.75, False, False).permitted)
        self.assertFalse(evaluate_delta_policy(CFG, 0.90, False, False).permitted)

    def test_restricted_band_is_narrower(self):
        self.assertTrue(evaluate_delta_policy(CFG, 0.75, False, True).permitted)
        self.assertFalse(evaluate_delta_policy(CFG, 0.62, False, True).permitted)  # legal normal, not restricted

    def test_convexity_exception_needs_confirmed_pass(self):
        pending = evaluate_delta_policy(CFG, 0.58, False, False, variance_and_es_tests_passed=None)
        confirmed = evaluate_delta_policy(CFG, 0.58, False, False, variance_and_es_tests_passed=True)
        self.assertFalse(pending.permitted)
        self.assertTrue(confirmed.permitted)

    def test_below_convexity_floor_is_prohibited(self):
        self.assertFalse(evaluate_delta_policy(CFG, 0.40, False, False, variance_and_es_tests_passed=True).permitted)


class SpreadRuleTests(unittest.TestCase):
    def test_all_five_conditions_must_hold(self):
        checks = evaluate_spread_rule(
            CFG, spread_robust_log_growth=0.05, outright_robust_log_growth=0.03,
            debit_fits_nav_budget=True, both_legs_pass_liquidity=True,
            prob_above_short_strike=0.15, spread_ev_positive_after_cap=True,
        )
        self.assertTrue(all_passed(checks))

    def test_short_strike_capping_the_bull_case_fails(self):
        checks = evaluate_spread_rule(
            CFG, spread_robust_log_growth=0.05, outright_robust_log_growth=0.03,
            debit_fits_nav_budget=True, both_legs_pass_liquidity=True,
            prob_above_short_strike=0.40, spread_ev_positive_after_cap=True,
        )
        self.assertIn("short_strike_not_capping", {c.name for c in failing(checks)})

    def test_missing_inputs_never_default_to_passed(self):
        checks = evaluate_spread_rule(CFG, None, None, None, None, None, None)
        self.assertFalse(all_passed(checks))
        self.assertEqual(len(failing(checks)), 5)


if __name__ == "__main__":
    unittest.main()
