"""Confirms both the parser AND the config.example.yaml transcription are
correct, by checking exact values against §20 as reproduced in
framework/v7.md."""
import unittest

from engine.config import TEMPLATE_PATH, get, load_config


class ConfigTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config(TEMPLATE_PATH)

    def test_top_level(self):
        self.assertEqual(self.cfg["version"], 7.0)
        self.assertEqual(
            self.cfg["supersedes"], ["v4.0", "v5.0", "v6.0", "v6.1", "v8.0-draft"]
        )

    def test_portfolio_nav_stays_null(self):
        # ADR 0013: NAV is read live and never stored; the template reflects that.
        self.assertIsNone(get(self.cfg, "portfolio.nav"))
        self.assertEqual(get(self.cfg, "portfolio.currency"), "USD")

    def test_macro_hard_gates(self):
        self.assertEqual(get(self.cfg, "macro_hard_gates.credit_stress.hy_oas_bp_absolute"), 550)
        self.assertEqual(get(self.cfg, "macro_hard_gates.equity_deleveraging.vix_level"), 32)
        self.assertEqual(
            get(self.cfg, "macro_hard_gates.equity_deleveraging.spx_pct_below_200dma"), 10
        )

    def test_restricted_regime(self):
        self.assertEqual(get(self.cfg, "restricted_regime.trigger_R"), 3)
        self.assertEqual(get(self.cfg, "restricted_regime.score_threshold_normal"), 75)
        self.assertEqual(get(self.cfg, "restricted_regime.score_threshold_restricted"), 80)
        self.assertEqual(get(self.cfg, "restricted_regime.kelly_multiplier_normal"), 0.25)
        self.assertEqual(get(self.cfg, "restricted_regime.kelly_multiplier_restricted"), 0.125)
        self.assertEqual(get(self.cfg, "restricted_regime.minimum_deployment_floor"), "none")

    def test_event_gates(self):
        self.assertEqual(get(self.cfg, "event_gates.binary_event_blackout_days"), 14)
        self.assertIs(get(self.cfg, "event_gates.spread_exception_permitted"), False)

    def test_seat_decay_gate(self):
        self.assertEqual(get(self.cfg, "seat_decay_gate.grr_min_pct"), 85)
        self.assertIs(get(self.cfg, "seat_decay_gate.nondisclosure_is_pass"), False)

    def test_entry_patterns(self):
        self.assertEqual(get(self.cfg, "entry_patterns.panic.drawdown_pct_range"), [10, 20])
        self.assertEqual(get(self.cfg, "entry_patterns.breakout.max_30d_gain_pct"), 20)

    def test_scoring_flow_maps(self):
        self.assertEqual(get(self.cfg, "scoring.thesis_fit"), {"points": 20, "min": 12})
        self.assertEqual(get(self.cfg, "scoring.invalidation_clarity"), {"points": 5, "min": 5})
        self.assertEqual(
            get(self.cfg, "scoring.fundamental_confirm"), {"points": 15, "min": None}
        )

    def test_option_vetoes(self):
        self.assertEqual(get(self.cfg, "option_vetoes.dte_range"), [365, 900])
        self.assertEqual(get(self.cfg, "option_vetoes.open_interest_min"), 500)
        self.assertEqual(get(self.cfg, "option_vetoes.quoted_spread_max_pct"), 6)

    def test_acceptance(self):
        self.assertEqual(get(self.cfg, "acceptance.ev_to_expected_loss_min"), 0.50)

    def test_delta_policy(self):
        self.assertEqual(get(self.cfg, "delta_policy.normal"), [0.60, 0.85])
        self.assertEqual(get(self.cfg, "delta_policy.convexity_exception"), [0.55, 0.70])
        self.assertEqual(get(self.cfg, "delta_policy.hard_gate_active"), "none")

    def test_sizing_caps(self):
        self.assertEqual(get(self.cfg, "sizing.kelly_posterior_draws_min"), 10000)
        self.assertIs(get(self.cfg, "sizing.full_kelly_permitted"), False)
        self.assertEqual(get(self.cfg, "sizing.caps_pct_of_nav.single_issuer"), 1.50)
        self.assertEqual(get(self.cfg, "sizing.caps_pct_of_nav.total_leaps_book"), 8.00)
        self.assertEqual(
            get(self.cfg, "sizing.min_comparable_observations_for_normal_size"), 50
        )

    def test_watchlist(self):
        self.assertEqual(get(self.cfg, "watchlist.target_size"), [15, 25])
        self.assertIs(get(self.cfg, "watchlist.saaspocalypse_as_core_mechanism"), False)

    def test_get_missing_key_returns_default(self):
        self.assertIsNone(get(self.cfg, "nonexistent.path"))
        self.assertEqual(get(self.cfg, "nonexistent.path", default="fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
