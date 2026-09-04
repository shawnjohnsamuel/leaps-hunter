"""engine.macro against literal fixture values (hard gates) and synthetic
series (R throttle) — no network calls. See test_macro_live.py for the
end-to-end reproduction against real fetched data."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.macro import (
    HardGateState,
    compute_restricted_regime,
    credit_stress_release_met,
    credit_stress_trigger,
    equity_deleveraging_release_met,
    equity_deleveraging_trigger,
    inflation_shock_release_met,
    inflation_shock_trigger,
    net_liquidity_contracting,
    net_liquidity_series,
    percentile_rank,
    step_hard_gate,
)

CFG = load_config(TEMPLATE_PATH)


class StepHardGateTests(unittest.TestCase):
    def test_inactive_stays_inactive_without_trigger(self):
        s = step_hard_gate(None, triggered_today=False, release_condition_met_today=False,
                            release_streak_required=5)
        self.assertFalse(s.active)

    def test_trigger_activates_from_inactive(self):
        s = step_hard_gate(None, triggered_today=True, release_condition_met_today=False,
                            release_streak_required=5)
        self.assertTrue(s.active)
        self.assertEqual(s.consecutive_release_days, 0)

    def test_release_streak_must_reach_required_count(self):
        s = HardGateState(active=True, consecutive_release_days=0)
        for expected_streak in range(1, 5):
            s = step_hard_gate(s, triggered_today=False, release_condition_met_today=True,
                                release_streak_required=5)
            self.assertTrue(s.active)
            self.assertEqual(s.consecutive_release_days, expected_streak)
        s = step_hard_gate(s, triggered_today=False, release_condition_met_today=True,
                            release_streak_required=5)
        self.assertFalse(s.active)
        self.assertEqual(s.consecutive_release_days, 0)

    def test_a_single_broken_day_resets_the_streak(self):
        s = HardGateState(active=True, consecutive_release_days=3)
        s = step_hard_gate(s, triggered_today=False, release_condition_met_today=False,
                            release_streak_required=5)
        self.assertTrue(s.active)
        self.assertEqual(s.consecutive_release_days, 0)

    def test_unavailable_release_input_fails_closed(self):
        s = HardGateState(active=True, consecutive_release_days=3)
        s = step_hard_gate(s, triggered_today=False, release_condition_met_today=None,
                            release_streak_required=5)
        self.assertTrue(s.active)
        self.assertEqual(s.consecutive_release_days, 0)


class CreditStressTests(unittest.TestCase):
    def test_absolute_trigger(self):
        self.assertTrue(credit_stress_trigger(5.5, 5.0, CFG))  # 550bp

    def test_widening_trigger(self):
        # +160bp over 20d (>=150bp) while above the 450bp floor
        self.assertTrue(credit_stress_trigger(4.6, 3.0, CFG))

    def test_no_trigger_at_current_reading(self):
        # 2026-09-03 live HY OAS reading, well below both conditions
        self.assertFalse(credit_stress_trigger(2.66, 2.60, CFG))

    def test_release_below_floor(self):
        self.assertTrue(credit_stress_release_met(4.4, CFG))

    def test_no_release_above_floor(self):
        self.assertFalse(credit_stress_release_met(4.6, CFG))


class InflationShockTests(unittest.TestCase):
    def test_all_three_deltas_must_fire(self):
        self.assertTrue(inflation_shock_trigger(0.45, 0.40, 0.25, CFG))
        self.assertFalse(inflation_shock_trigger(0.30, 0.40, 0.25, CFG))  # real delta short

    def test_release_needs_all_three_below_half_threshold(self):
        self.assertTrue(inflation_shock_release_met(0.10, 0.10, 0.05, CFG))
        self.assertFalse(inflation_shock_release_met(0.25, 0.10, 0.05, CFG))  # real at full half


class EquityDeleveragingTests(unittest.TestCase):
    def test_all_three_conditions_trigger(self):
        self.assertTrue(equity_deleveraging_trigger(33, 32, -11, 30, CFG))

    def test_breadth_unavailable_fails_closed_when_escalated(self):
        self.assertTrue(equity_deleveraging_trigger(33, 32, -11, None, CFG))

    def test_healthy_breadth_prevents_trigger(self):
        self.assertFalse(equity_deleveraging_trigger(33, 32, -11, 40, CFG))

    def test_single_vix_close_does_not_trigger(self):
        self.assertFalse(equity_deleveraging_trigger(33, 20, -11, 30, CFG))

    def test_shallow_drawdown_does_not_trigger(self):
        self.assertFalse(equity_deleveraging_trigger(33, 32, -5, 30, CFG))

    def test_release_requires_both_conditions(self):
        self.assertTrue(equity_deleveraging_release_met(20, 50, CFG))
        self.assertFalse(equity_deleveraging_release_met(26, 50, CFG))

    def test_release_breadth_unavailable_fails_closed(self):
        self.assertFalse(equity_deleveraging_release_met(20, None, CFG))


class PercentileRankTests(unittest.TestCase):
    def test_basic_rank(self):
        self.assertEqual(percentile_rank([1, 2, 3, 4, 5], 3), 40.0)

    def test_extremes(self):
        self.assertEqual(percentile_rank([1, 2, 3], 0), 0.0)
        self.assertEqual(percentile_rank([1, 2, 3], 10), 100.0)


class NetLiquidityTests(unittest.TestCase):
    def setUp(self):
        # 20 synthetic weekly WALCL points, TGA/RRP flat, WALCL trending down
        # over the trailing 13-period window used by net_liquidity_contracting.
        self.walcl = [(f"2026-{1 + i // 4:02d}-{1 + (i % 4) * 7:02d}", 6800.0 - i * 5.0)
                      for i in range(20)]
        self.wtregen = [(d, 900.0) for d, _ in self.walcl]
        self.rrp = [(d, 0.5) for d, _ in self.walcl]

    def test_series_alignment_and_units(self):
        series = net_liquidity_series(self.walcl, self.wtregen, self.rrp)
        self.assertEqual(len(series), 20)
        # WALCL(0) - TGA - RRP*1000 = 6800 - 900 - 500 = 5400
        self.assertAlmostEqual(series[0][1], 5400.0)

    def test_contracting_detected_over_lookback(self):
        series = net_liquidity_series(self.walcl, self.wtregen, self.rrp)
        self.assertTrue(net_liquidity_contracting(series, lookback_periods=13))

    def test_not_contracting_when_flat(self):
        flat = [(d, 6800.0) for d, _ in self.walcl]
        series = net_liquidity_series(flat, self.wtregen, self.rrp)
        self.assertFalse(net_liquidity_contracting(series, lookback_periods=13))


class RestrictedRegimeTests(unittest.TestCase):
    def _run(self, cape_now, credit_now, real30_now, liquidity_contracting):
        history = list(range(1, 101))  # 1..100, so percentile_rank is exact
        return compute_restricted_regime(
            CFG, cape_now, history, credit_now, history, real30_now, history,
            liquidity_contracting,
        )

    def test_zero_components_is_normal(self):
        r = self._run(cape_now=10, credit_now=90, real30_now=10, liquidity_contracting=False)
        self.assertEqual(r.R, 0)
        self.assertFalse(r.restricted)
        self.assertEqual(r.score_threshold, 75)
        self.assertEqual(r.kelly_multiplier, 0.25)

    def test_reproduces_the_2026_09_03_preview(self):
        # cape 99.1st, credit 10.5th (<20th, so it FIRES), real30 99.7th, liquidity contracting
        r = self._run(cape_now=99, credit_now=10, real30_now=99, liquidity_contracting=True)
        self.assertEqual(r.R, 4)
        self.assertTrue(r.restricted)
        self.assertEqual(r.score_threshold, 80)
        self.assertEqual(r.kelly_multiplier, 0.125)

    def test_threshold_flips_exactly_at_trigger_R(self):
        # Exactly 3 of 4 components -> restricted (trigger_R = 3 in config).
        r = self._run(cape_now=99, credit_now=10, real30_now=99, liquidity_contracting=False)
        self.assertEqual(r.R, 3)
        self.assertTrue(r.restricted)
        two = self._run(cape_now=99, credit_now=10, real30_now=10, liquidity_contracting=False)
        self.assertEqual(two.R, 2)
        self.assertFalse(two.restricted)


if __name__ == "__main__":
    unittest.main()
