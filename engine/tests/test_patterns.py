"""engine.patterns — §10's four entry patterns, split between mechanical
checks (tested against constructed price series) and caller-supplied
judgment inputs (tested for correct "missing input => not confirmed" wiring,
per §3: an unobtainable metric disqualifies, it never defaults to a pass).
"""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.patterns import (
    BottleneckExpansionInputs,
    BreakoutInputs,
    QuietInflectionInputs,
    bottleneck_expansion_pattern,
    breakout_pattern,
    multiple_expansion_ratio,
    panic_pattern,
    price_60d_ago,
    quiet_inflection_pattern,
    relative_underperformance_pts,
)
from engine.priceseries import is_range_bound
from engine.sources import NTMResult

CFG = load_config(TEMPLATE_PATH)

GOOD_NTM = NTMResult(available=True, revision_pct=12.0, ntm_eps_now=1.12, ntm_eps_60d_ago=1.0)
WEAK_NTM = NTMResult(available=True, revision_pct=2.0, ntm_eps_now=1.02, ntm_eps_60d_ago=1.0)
CUT_NTM = NTMResult(available=True, revision_pct=-8.0, ntm_eps_now=0.92, ntm_eps_60d_ago=1.0)
SMALL_CUT_NTM = NTMResult(available=True, revision_pct=-2.0, ntm_eps_now=0.98, ntm_eps_60d_ago=1.0)
UNAVAILABLE_NTM = NTMResult(available=False, reason="only 1 forward fiscal year(s) available, need 2")


class PanicPatternTests(unittest.TestCase):
    def test_qualifies_via_drawdown_window(self):
        # 27 flat sessions then a 3-session drop of 15% (within [10,20] and [2,5]).
        prices = [100.0] * 27 + [95.0, 90.0, 85.0]
        r = panic_pattern(CFG, prices, SMALL_CUT_NTM)
        self.assertTrue(r.qualifies)

    def test_qualifies_via_sigma_when_drawdown_insufficient(self):
        # Low-volatility name (+/-0.1-0.2% daily) with a single -5% outlier day
        # that never reaches a 10% cumulative decline over any 2-5 day window.
        prices = [100.0]
        for i in range(60):
            prices.append(prices[-1] * (1 + (0.002 if i % 2 == 0 else -0.001)))
        prices.append(prices[-1] * 0.95)
        r = panic_pattern(CFG, prices, SMALL_CUT_NTM)
        self.assertTrue(r.qualifies)

    def test_does_not_qualify_when_flat(self):
        prices = [100.0] * 40
        r = panic_pattern(CFG, prices, SMALL_CUT_NTM)
        self.assertFalse(r.qualifies)

    def test_confirmed_when_cut_within_bound(self):
        prices = [100.0] * 27 + [95.0, 90.0, 85.0]
        r = panic_pattern(CFG, prices, SMALL_CUT_NTM)  # -2% cut, max allowed 5%
        self.assertTrue(r.confirmed)

    def test_not_confirmed_when_cut_exceeds_max(self):
        prices = [100.0] * 27 + [95.0, 90.0, 85.0]
        r = panic_pattern(CFG, prices, CUT_NTM)  # -8% cut, max allowed 5%
        self.assertFalse(r.confirmed)

    def test_not_confirmed_when_ntm_missing(self):
        prices = [100.0] * 27 + [95.0, 90.0, 85.0]
        r = panic_pattern(CFG, prices, None)
        self.assertFalse(r.confirmed)

    def test_not_confirmed_when_ntm_unavailable(self):
        prices = [100.0] * 27 + [95.0, 90.0, 85.0]
        r = panic_pattern(CFG, prices, UNAVAILABLE_NTM)
        self.assertFalse(r.confirmed)


class QuietInflectionPatternTests(unittest.TestCase):
    def test_qualifies_needs_at_least_two_accelerating(self):
        one = QuietInflectionInputs(accelerating_metrics_count=1, ntm=GOOD_NTM)
        two = QuietInflectionInputs(accelerating_metrics_count=2, ntm=GOOD_NTM)
        self.assertFalse(quiet_inflection_pattern(CFG, one).qualifies)
        self.assertTrue(quiet_inflection_pattern(CFG, two).qualifies)

    def test_confirmed_via_underperformance(self):
        i = QuietInflectionInputs(
            accelerating_metrics_count=3, ntm=GOOD_NTM, relative_underperformance_pts=7.0
        )
        self.assertTrue(quiet_inflection_pattern(CFG, i).confirmed)

    def test_confirmed_via_range_bound_instead(self):
        i = QuietInflectionInputs(accelerating_metrics_count=3, ntm=GOOD_NTM, is_range_bound=True)
        self.assertTrue(quiet_inflection_pattern(CFG, i).confirmed)

    def test_not_confirmed_when_revision_too_weak(self):
        i = QuietInflectionInputs(
            accelerating_metrics_count=3, ntm=WEAK_NTM, relative_underperformance_pts=10.0
        )
        self.assertFalse(quiet_inflection_pattern(CFG, i).confirmed)

    def test_not_confirmed_without_underperformance_or_range_bound(self):
        i = QuietInflectionInputs(accelerating_metrics_count=3, ntm=GOOD_NTM)
        self.assertFalse(quiet_inflection_pattern(CFG, i).confirmed)


class BreakoutPatternTests(unittest.TestCase):
    def _ramp(self, n, daily_pct):
        prices = [100.0]
        for _ in range(n):
            prices.append(prices[-1] * (1 + daily_pct))
        return prices

    def test_qualifies_new_high_with_gain_in_bounds(self):
        prices = self._ramp(140, 0.001)  # gentle ramp, ~2-3% over 30d
        i = BreakoutInputs(ntm=GOOD_NTM, multiple_expansion_ratio=0.2)
        r = breakout_pattern(CFG, prices, i)
        self.assertTrue(r.qualifies)

    def test_does_not_qualify_when_30d_gain_too_large(self):
        prices = [100.0] * 100 + self._ramp(40, 0.01)[1:]  # ~35% 30d gain
        i = BreakoutInputs(ntm=GOOD_NTM, multiple_expansion_ratio=0.2)
        r = breakout_pattern(CFG, prices, i)
        self.assertFalse(r.qualifies)

    def test_confirmed_needs_both_revision_and_bounded_expansion(self):
        prices = self._ramp(140, 0.001)
        good = breakout_pattern(CFG, prices, BreakoutInputs(ntm=GOOD_NTM, multiple_expansion_ratio=0.2))
        weak_revision = breakout_pattern(
            CFG, prices, BreakoutInputs(ntm=WEAK_NTM, multiple_expansion_ratio=0.2)
        )
        too_much_expansion = breakout_pattern(
            CFG, prices, BreakoutInputs(ntm=GOOD_NTM, multiple_expansion_ratio=0.9)
        )
        missing_expansion = breakout_pattern(CFG, prices, BreakoutInputs(ntm=GOOD_NTM))
        self.assertTrue(good.confirmed)
        self.assertFalse(weak_revision.confirmed)
        self.assertFalse(too_much_expansion.confirmed)
        self.assertFalse(missing_expansion.confirmed)


class BottleneckExpansionPatternTests(unittest.TestCase):
    def setUp(self):
        self.flat_prices = [100.0] * 40  # 0% 30d gain, well under any cap

    def test_qualifies_needs_backlog_growth_and_stability(self):
        good = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=18.0, backlog_to_revenue_stable_or_rising=True
        )
        short = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=10.0, backlog_to_revenue_stable_or_rising=True
        )
        missing = BottleneckExpansionInputs()
        self.assertTrue(bottleneck_expansion_pattern(CFG, self.flat_prices, good).qualifies)
        self.assertFalse(bottleneck_expansion_pattern(CFG, self.flat_prices, short).qualifies)
        self.assertFalse(bottleneck_expansion_pattern(CFG, self.flat_prices, missing).qualifies)

    def test_confirmed_needs_pricing_evidence_and_no_failed_option_check(self):
        full = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=18.0,
            backlog_to_revenue_stable_or_rising=True,
            pricing_or_margin_evidence=True,
            option_valuation_passed=True,
        )
        deferred_option_check = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=18.0,
            backlog_to_revenue_stable_or_rising=True,
            pricing_or_margin_evidence=True,
        )
        failed_option_check = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=18.0,
            backlog_to_revenue_stable_or_rising=True,
            pricing_or_margin_evidence=True,
            option_valuation_passed=False,
        )
        no_pricing = BottleneckExpansionInputs(
            backlog_vs_revenue_growth_pts=18.0, backlog_to_revenue_stable_or_rising=True
        )
        self.assertTrue(bottleneck_expansion_pattern(CFG, self.flat_prices, full).confirmed)
        # ADR 0021: None defers the check to §12, which runs it before any CANDIDATE.
        r = bottleneck_expansion_pattern(CFG, self.flat_prices, deferred_option_check)
        self.assertTrue(r.confirmed)
        self.assertIn("deferred to §12", " ".join(r.reasons))
        self.assertFalse(bottleneck_expansion_pattern(CFG, self.flat_prices, failed_option_check).confirmed)
        self.assertFalse(bottleneck_expansion_pattern(CFG, self.flat_prices, no_pricing).confirmed)


class ComputedPatternInputTests(unittest.TestCase):
    def test_multiple_expansion_ratio_zero_when_price_tracks_estimates(self):
        self.assertAlmostEqual(multiple_expansion_ratio(112.0, 100.0, GOOD_NTM), 0.0)

    def test_multiple_expansion_ratio_above_half_when_price_outruns_estimates(self):
        # +30% price on +12% estimates: multiple +16.1%, ratio ~1.34.
        self.assertGreater(multiple_expansion_ratio(130.0, 100.0, GOOD_NTM), 0.5)

    def test_multiple_compression_is_negative(self):
        self.assertLess(multiple_expansion_ratio(100.0, 100.0, GOOD_NTM), 0.0)

    def test_unresolved_without_an_estimate_improvement_or_old_price(self):
        self.assertIsNone(multiple_expansion_ratio(110.0, 100.0, CUT_NTM))
        self.assertIsNone(multiple_expansion_ratio(110.0, 100.0, UNAVAILABLE_NTM))
        self.assertIsNone(multiple_expansion_ratio(110.0, 100.0, None))
        self.assertIsNone(multiple_expansion_ratio(110.0, None, GOOD_NTM))

    def test_breakout_confirms_with_the_computed_ratio(self):
        prices = [100.0] * 100 + [100.0 + i * 0.5 for i in range(1, 21)]  # gentle new high
        ratio = multiple_expansion_ratio(prices[-1], 100.0, GOOD_NTM)  # +10% price, +12% EPS
        r = breakout_pattern(CFG, prices, BreakoutInputs(ntm=GOOD_NTM, multiple_expansion_ratio=ratio))
        self.assertTrue(r.clears)

    def test_price_60d_ago_reads_the_close_on_or_before(self):
        closes = [("2026-09-01", 90.0), ("2026-09-03", 95.0), ("2026-09-08", 99.0)]
        self.assertEqual(price_60d_ago(closes, "2026-11-03"), 95.0)  # 60d back = 09-04
        self.assertIsNone(price_60d_ago(closes, "2026-10-01"))

    def test_relative_underperformance(self):
        stock = [100.0] * 10 + [95.0]
        sector = [100.0] * 10 + [103.0]
        self.assertAlmostEqual(relative_underperformance_pts(stock, sector, 10), 8.0)
        self.assertIsNone(relative_underperformance_pts(stock[:3], sector, 10))

    def test_range_bound(self):
        self.assertTrue(is_range_bound([100.0, 104.0, 98.0, 102.0], 4, 10))
        self.assertFalse(is_range_bound([100.0, 120.0, 98.0, 102.0], 4, 10))


if __name__ == "__main__":
    unittest.main()
