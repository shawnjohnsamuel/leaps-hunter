"""engine.sizing — §13.3 feasibility and §14 robust fractional Kelly."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.optmodel import executable_entry
from engine.sizing import (
    NAVCapInputs,
    compute_f_trade,
    compute_feasibility,
    generate_posterior_draws,
    kelly_f_star,
    nav_caps,
    robust_kelly_fraction,
)

CFG = load_config(TEMPLATE_PATH)


class KellyFStarTests(unittest.TestCase):
    def test_classic_coin_flip_matches_the_textbook_formula(self):
        # p=0.6 win (+100%), q=0.4 lose (-100%): f* = p - q/b = 0.6 - 0.4/1 = 0.2.
        f = kelly_f_star([0.6, 0.4], [1.0, -1.0], f_cap=1.0)
        self.assertAlmostEqual(f, 0.2, places=4)

    def test_negative_edge_gives_zero_not_negative(self):
        # Unbounded Kelly would want f=-0.2 here; constrained to [0, cap] -> 0.
        f = kelly_f_star([0.4, 0.6], [1.0, -1.0], f_cap=1.0)
        self.assertEqual(f, 0.0)

    def test_certain_total_loss_gives_zero(self):
        f = kelly_f_star([1.0], [-1.0], f_cap=1.0)
        self.assertEqual(f, 0.0)

    def test_domain_clipping_never_crashes_on_a_large_cap(self):
        # f_cap=5.0 would otherwise push 1+f*r <= 0 for the -100% outcome.
        f = kelly_f_star([0.6, 0.4], [1.0, -1.0], f_cap=5.0)
        self.assertLess(f, 1.0)

    def test_cap_binds_when_optimum_exceeds_it(self):
        f = kelly_f_star([0.6, 0.4], [1.0, -1.0], f_cap=0.05)
        self.assertEqual(f, 0.05)


class RobustKellyTests(unittest.TestCase):
    def test_robust_fraction_is_more_conservative_than_the_point_estimate(self):
        draws = generate_posterior_draws([0.6, 0.4], [1.0, -1.0], n_draws=10_000, seed=42)
        f_robust = robust_kelly_fraction(draws, f_cap=1.0, quantile=0.10)
        self.assertGreater(f_robust, 0.0)
        self.assertLess(f_robust, 0.2)  # below the noiseless point estimate

    def test_reproducible_given_a_seed(self):
        draws_a = generate_posterior_draws([0.6, 0.4], [1.0, -1.0], n_draws=1000, seed=7)
        draws_b = generate_posterior_draws([0.6, 0.4], [1.0, -1.0], n_draws=1000, seed=7)
        self.assertEqual(
            robust_kelly_fraction(draws_a, 1.0), robust_kelly_fraction(draws_b, 1.0)
        )

    def test_negative_edge_is_robustly_zero(self):
        draws = generate_posterior_draws([0.3, 0.7], [1.0, -1.0], n_draws=2000, seed=1)
        self.assertEqual(robust_kelly_fraction(draws, f_cap=1.0), 0.0)


class NavCapsTests(unittest.TestCase):
    def test_unvalidated_setup_caps_at_quarter_point_before_calibration(self):
        caps = nav_caps(CFG, NAVCapInputs(is_calibrated=False))
        self.assertAlmostEqual(caps["f_instrument"], 0.0025)  # 0.25%

    def test_calibrated_itm_or_spread_caps_at_1_25_pct(self):
        caps = nav_caps(CFG, NAVCapInputs(is_calibrated=True, structure_type="single_itm_or_spread"))
        self.assertAlmostEqual(caps["f_instrument"], 0.0125)

    def test_calibrated_atm_convexity_caps_at_0_75_pct(self):
        caps = nav_caps(CFG, NAVCapInputs(is_calibrated=True, structure_type="single_atm_convexity"))
        self.assertAlmostEqual(caps["f_instrument"], 0.0075)

    def test_existing_exposure_reduces_headroom(self):
        caps = nav_caps(CFG, NAVCapInputs(existing_issuer_exposure_pct=0.01))  # 1.0% already committed
        self.assertAlmostEqual(caps["f_issuer"], 0.005)  # 1.5% cap - 1.0% used

    def test_headroom_floors_at_zero_not_negative(self):
        caps = nav_caps(CFG, NAVCapInputs(existing_mechanism_exposure_pct=0.10))  # already over the 3% cap
        self.assertEqual(caps["f_mechanism"], 0.0)


class ComputeFTradeTests(unittest.TestCase):
    def test_zero_or_negative_f_robust_is_always_zero_no_exceptions(self):
        r = compute_f_trade(f_robust=0.0, kelly_multiplier=0.25, caps={"f_instrument": 0.05})
        self.assertEqual(r.f_trade, 0.0)
        self.assertTrue(r.allocation_zero)
        r2 = compute_f_trade(f_robust=-0.1, kelly_multiplier=0.25, caps={"f_instrument": 0.05})
        self.assertEqual(r2.f_trade, 0.0)

    def test_kelly_binds_when_smaller_than_caps(self):
        r = compute_f_trade(f_robust=0.02, kelly_multiplier=0.25, caps={"f_instrument": 0.05})
        self.assertEqual(r.binding_cap, "kelly")
        self.assertAlmostEqual(r.f_trade, 0.005)

    def test_instrument_cap_binds_when_smaller_than_kelly(self):
        r = compute_f_trade(f_robust=0.5, kelly_multiplier=0.25, caps={"f_instrument": 0.0025})
        self.assertEqual(r.binding_cap, "f_instrument")
        self.assertAlmostEqual(r.f_trade, 0.0025)

    def test_restricted_multiplier_lowers_f_trade(self):
        normal = compute_f_trade(f_robust=0.5, kelly_multiplier=0.25, caps={"f_instrument": 1.0})
        restricted = compute_f_trade(f_robust=0.5, kelly_multiplier=0.125, caps={"f_instrument": 1.0})
        self.assertLess(restricted.f_trade, normal.f_trade)


class FeasibilityTests(unittest.TestCase):
    def test_reproduces_the_2026_09_03_crm_min_feasible_nav(self):
        # Real Phase 0 quote: ask 78.95, bid 75.60 -> executable entry 79.7875.
        entry = executable_entry(ask=78.95, bid=75.60, fees=0.0, cfg=CFG)
        r = compute_feasibility(f_trade=0.0025, nav=1_000_000, entry_price_per_share=entry)
        self.assertAlmostEqual(r.min_feasible_nav, 3_191_500, delta=1000)
        self.assertEqual(r.n_max, 0)
        self.assertFalse(r.feasible)

    def test_feasible_once_nav_clears_the_minimum(self):
        entry = executable_entry(ask=78.95, bid=75.60, fees=0.0, cfg=CFG)
        r = compute_feasibility(f_trade=0.0025, nav=3_500_000, entry_price_per_share=entry)
        self.assertGreaterEqual(r.n_max, 1)
        self.assertTrue(r.feasible)

    def test_zero_f_trade_is_infeasible_at_any_nav(self):
        r = compute_feasibility(f_trade=0.0, nav=1_000_000_000, entry_price_per_share=79.79)
        self.assertEqual(r.n_max, 0)
        self.assertFalse(r.feasible)
        self.assertEqual(r.min_feasible_nav, float("inf"))

    def test_calibration_lowers_the_min_feasible_nav(self):
        entry = executable_entry(ask=78.95, bid=75.60, fees=0.0, cfg=CFG)
        unvalidated = compute_feasibility(f_trade=0.0025, nav=1_000_000, entry_price_per_share=entry)
        calibrated = compute_feasibility(f_trade=0.0125, nav=1_000_000, entry_price_per_share=entry)
        self.assertGreater(unvalidated.min_feasible_nav, calibrated.min_feasible_nav)



class FeasibilityDiagnosticsTests(unittest.TestCase):
    def test_mu_2026_11_03_reproduces_the_logged_figures(self):
        # daily/2026-11-03.json: MU Jan-2028 $600 call, P0 377.525, f_trade 0.0025.
        r = compute_feasibility(0.0025, 37670.62, 377.525, calibrated_cap_pct=1.25)
        self.assertEqual(r.n_max, 0)
        self.assertAlmostEqual(r.min_feasible_nav, 15_101_000, delta=1_000)
        self.assertAlmostEqual(r.min_feasible_nav_calibrated, 3_020_200, delta=100)
        self.assertAlmostEqual(r.contract_pct_of_nav, 100.2, places=1)

    def test_diagnostics_are_optional(self):
        r = compute_feasibility(0.0025, 100_000, 5.0)
        self.assertIsNone(r.min_feasible_nav_calibrated)



class ShareFallbackTests(unittest.TestCase):
    MU = dict(spot=833.59, probs=[0.15, 0.50, 0.25, 0.10], moves=[-0.30, 0.15, 0.45, 0.90],
              kelly_multiplier=0.125, nav=37670.62, seed=7, n_draws=2000)

    def test_mu_2026_11_03_scenarios_size_to_the_loss_cap(self):
        from engine.sizing import share_fallback
        r = share_fallback(CFG, **self.MU)
        self.assertTrue(r.passes_acceptance)
        self.assertEqual(r.binding, "max_loss_cap")
        self.assertAlmostEqual(r.loss_at_worst_pct_nav, 0.25, places=2)  # the configured cap
        self.assertAlmostEqual(r.dollars, 37670.62 * 0.0025 / 0.30, delta=0.05)
        self.assertAlmostEqual(r.review_price, 583.51, places=2)
        self.assertEqual(r.whole_shares, 0)  # fractional only at this size
        self.assertGreater(r.shares, 0)

    def test_kelly_binds_when_the_cap_is_loose(self):
        import copy
        from engine.sizing import share_fallback
        cfg = copy.deepcopy(CFG)
        cfg["share_fallback"]["max_loss_pct_nav"] = 50
        r = share_fallback(cfg, **self.MU)
        self.assertEqual(r.binding, "kelly")
        self.assertLessEqual(r.fraction_of_nav, 0.125 + 1e-9)  # multiplier x f_robust, f_robust <= 1

    def test_no_edge_sizes_to_zero_and_fails_acceptance(self):
        from engine.sizing import share_fallback
        r = share_fallback(CFG, 100.0, [0.6, 0.4], [-0.2, 0.1], 0.125, 50_000, seed=1, n_draws=500)
        self.assertEqual(r.dollars, 0.0)
        self.assertFalse(r.passes_acceptance)


if __name__ == "__main__":
    unittest.main()
