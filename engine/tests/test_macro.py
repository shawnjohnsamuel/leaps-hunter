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
    advance_hard_gate,
    breadth_needed,
    compute_breadth,
    credit_proxy_check,
    credit_stress_daily,
    equity_deleveraging_escalated,
    inflation_shock_daily,
    percentile_rank,
    spx_pct_vs_200dma,
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


class SpxPctVs200dmaTests(unittest.TestCase):
    def test_below_average_is_negative(self):
        closes = [100.0] * 199 + [88.0]
        self.assertLess(spx_pct_vs_200dma(closes), 0)

    def test_above_average_is_positive(self):
        closes = [100.0] * 199 + [110.0]
        self.assertGreater(spx_pct_vs_200dma(closes), 0)

    def test_uses_only_trailing_window(self):
        closes = [1.0] * 50 + [100.0] * 199 + [90.0]
        self.assertAlmostEqual(spx_pct_vs_200dma(closes), (90.0 - 99.95) / 99.95 * 100.0)

    def test_short_history_raises(self):
        with self.assertRaises(ValueError):
            spx_pct_vs_200dma([100.0] * 199)

    def test_real_drawdown_fires_the_gate_end_to_end(self):
        # Regression for the inverted-sign bug: a genuine ~12% drawdown with
        # VIX elevated and breadth weak must trigger. With the sign flipped
        # this value arrives as +12 and the gate stays silent.
        closes = [100.0] * 199 + [87.0]
        pct = spx_pct_vs_200dma(closes)
        self.assertTrue(equity_deleveraging_trigger(33, 32, pct, 30, CFG))

    def test_market_above_average_does_not_fire_even_with_high_vix(self):
        closes = [100.0] * 199 + [107.0]
        pct = spx_pct_vs_200dma(closes)
        self.assertFalse(equity_deleveraging_trigger(33, 32, pct, 30, CFG))


class BreadthNeededTests(unittest.TestCase):
    def test_calm_market_inactive_gate_skips_breadth(self):
        self.assertFalse(breadth_needed(16, 15, 7.0, gate_active=False, cfg=CFG))

    def test_escalation_requires_breadth(self):
        self.assertTrue(breadth_needed(33, 32, -11, gate_active=False, cfg=CFG))

    def test_active_gate_requires_breadth_even_when_calm(self):
        # The release check needs a fresh reading; skipping it here is the
        # deadlock ADR 0016 closes.
        self.assertTrue(breadth_needed(16, 15, 7.0, gate_active=True, cfg=CFG))

    def test_escalated_matches_trigger_precondition(self):
        # Skipping breadth must never change a trigger outcome.
        for vix, prev, spx in [(33, 32, -11), (33, 20, -11), (33, 32, -5), (16, 15, 7.0)]:
            if not equity_deleveraging_escalated(vix, prev, spx, CFG):
                self.assertFalse(equity_deleveraging_trigger(vix, prev, spx, None, CFG))


def _series(n, start=100.0, last=None):
    days = [f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]
    closes = [start] * n
    if last is not None:
        closes[-1] = last
    return list(zip(days, closes))


class ComputeBreadthTests(unittest.TestCase):
    def setUp(self):
        self.up = _series(200, last=110.0)
        self.down = _series(200, last=90.0)
        self.date = self.up[-1][0]

    def test_percentage_over_computed_names(self):
        data = {"A": self.up, "B": self.up, "C": self.up, "D": self.down}
        r = compute_breadth(data, ["A", "B", "C", "D"], CFG)
        self.assertTrue(r.available)
        self.assertAlmostEqual(r.pct_above_200dma, 75.0)
        self.assertEqual(r.as_of, self.date)

    def test_lagging_feed_is_excluded_not_mixed_in(self):
        stale = self.up[:-1] + [("1999-01-01", 500.0)]
        universe = [f"S{i}" for i in range(20)]
        data = {s: self.down for s in universe[:19]}
        data["S19"] = stale
        r = compute_breadth(data, universe, CFG)
        self.assertEqual(r.names_on_date, 19)
        self.assertEqual(r.pct_above_200dma, 0.0)

    def test_coverage_below_floor_is_unavailable(self):
        universe = [f"S{i}" for i in range(10)]
        data = {s: self.up for s in universe[:8]}
        r = compute_breadth(data, universe, CFG)
        self.assertFalse(r.available)
        self.assertIsNone(r.pct_above_200dma)
        self.assertIn("coverage", r.reason)

    def test_short_history_excluded_without_penalizing_coverage(self):
        universe = [f"S{i}" for i in range(10)]
        data = {s: self.up for s in universe[:9]}
        data["S9"] = self.up[-50:]
        r = compute_breadth(data, universe, CFG)
        self.assertTrue(r.available)
        self.assertEqual(r.names_short_history, 1)
        self.assertEqual(r.names_computed, 9)
        self.assertAlmostEqual(r.coverage, 1.0)

    def test_no_data_is_unavailable(self):
        r = compute_breadth({}, ["A"], CFG)
        self.assertFalse(r.available)

    def test_unavailable_breadth_fails_the_gate_closed_end_to_end(self):
        r = compute_breadth({}, ["A"], CFG)
        self.assertTrue(equity_deleveraging_trigger(33, 32, -11, r.pct_above_200dma, CFG))
        self.assertFalse(equity_deleveraging_release_met(20, r.pct_above_200dma, CFG))


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


def _dated(values, start_day=1):
    return [(f"2026-01-{start_day + i:02d}" if start_day + i <= 31 else f"2026-02-{start_day + i - 31:02d}", v)
            for i, v in enumerate(values)]


class AdvanceHardGateTests(unittest.TestCase):
    CALM = (False, True)

    def rows(self, *conds):
        return [(d, t, r) for (d, _), (t, r) in zip(_dated([0] * len(conds)), conds)]

    def test_steps_once_per_observation_after_cursor(self):
        rows = self.rows(self.CALM, self.CALM, self.CALM)
        _, cursor, steps = advance_hard_gate(None, rows, rows[0][0], 5)
        self.assertEqual((cursor, steps), (rows[2][0], 2))

    def test_same_day_rerun_steps_zero_times(self):
        rows = self.rows(*[self.CALM] * 3)
        active = HardGateState(active=True, consecutive_release_days=0)
        state, cursor, _ = advance_hard_gate(active, rows, "2025-12-31", 5)
        again, cursor2, steps = advance_hard_gate(state, rows, cursor, 5)
        self.assertEqual((again, cursor2, steps), (state, cursor, 0))
        self.assertEqual(again.consecutive_release_days, 3)

    def test_five_real_closes_release_an_active_gate(self):
        active = HardGateState(active=True, consecutive_release_days=0)
        state, _, _ = advance_hard_gate(active, self.rows(*[self.CALM] * 5), "2025-12-31", 5)
        self.assertFalse(state.active)

    def test_four_closes_do_not(self):
        active = HardGateState(active=True, consecutive_release_days=0)
        state, _, _ = advance_hard_gate(active, self.rows(*[self.CALM] * 4), "2025-12-31", 5)
        self.assertEqual(state, HardGateState(active=True, consecutive_release_days=4))

    def test_trigger_that_faded_before_the_weekly_run_is_still_caught(self):
        # Regression for once-per-run stepping: day 1 triggers, days 2-5 are
        # calm. Stepping only the latest (calm) day left the gate inactive.
        rows = self.rows((True, False), self.CALM, self.CALM, self.CALM, self.CALM)
        state, _, _ = advance_hard_gate(None, rows, "2025-12-31", 5)
        self.assertEqual(state, HardGateState(active=True, consecutive_release_days=4))

    def test_broken_streak_resets(self):
        active = HardGateState(active=True, consecutive_release_days=0)
        rows = self.rows(self.CALM, self.CALM, (False, False), self.CALM)
        state, _, _ = advance_hard_gate(active, rows, "2025-12-31", 5)
        self.assertEqual(state.consecutive_release_days, 1)


class DailyConditionTests(unittest.TestCase):
    def test_credit_uses_twenty_observation_lookback(self):
        rows = credit_stress_daily(_dated([3.0] * 25), CFG)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0][0], _dated([3.0] * 25)[20][0])

    def test_credit_widening_triggers_on_its_own_day(self):
        rows = credit_stress_daily(_dated([3.2] * 20 + [5.0]), CFG)
        self.assertEqual(rows, [(_dated([0] * 21)[20][0], True, False)])

    def test_inflation_aligns_dates_and_keeps_each_series_window(self):
        real, nominal, be = _dated([1.0] * 11 + [1.5]), _dated([4.0] * 11 + [4.5]), _dated([2.0] * 11 + [2.3])
        missing = be.pop(5)[0]
        rows = inflation_shock_daily(real, nominal, be, CFG)
        self.assertNotIn(missing, [d for d, _, _ in rows])
        self.assertEqual(rows[-1], (real[-1][0], True, False))


class CreditProxyTests(unittest.TestCase):
    def test_calm_ratio_does_not_trip(self):
        r = credit_proxy_check(_dated([80.0] * 21), _dated([82.0] * 21), CFG)
        self.assertTrue(r.available)
        self.assertFalse(r.tripped)
        self.assertAlmostEqual(r.drawdown_pct, 0.0)

    def test_credit_selloff_trips(self):
        r = credit_proxy_check(_dated([80.0] * 20 + [78.4]), _dated([82.0] * 21), CFG)
        self.assertTrue(r.tripped)
        self.assertAlmostEqual(r.drawdown_pct, 2.0)

    def test_rates_move_hitting_both_legs_does_not_trip(self):
        # The 2026-09-11 case: raw HYG fell on a yield spike while spreads
        # tightened. When the hedge falls in step, the ratio is unchanged.
        r = credit_proxy_check(_dated([80.0] * 20 + [78.4]), _dated([82.0] * 20 + [80.36]), CFG)
        self.assertFalse(r.tripped)

    def test_short_history_is_unavailable_not_tripped(self):
        r = credit_proxy_check(_dated([80.0] * 10), _dated([82.0] * 10), CFG)
        self.assertEqual((r.available, r.tripped), (False, False))

    def test_dates_missing_from_the_hedge_are_skipped(self):
        credit, hedge = _dated([80.0] * 22), _dated([82.0] * 22)
        hedge.pop(10)
        r = credit_proxy_check(credit, hedge, CFG)
        self.assertTrue(r.available)
        self.assertEqual(r.as_of, credit[-1][0])


if __name__ == "__main__":
    unittest.main()
