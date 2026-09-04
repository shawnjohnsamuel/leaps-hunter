"""engine.portfolio — §15's variance/ES test and the ITM-to-ATM roll math."""
import unittest

from engine.portfolio import (
    Position,
    cholesky,
    correlated_normal_draws,
    evaluate_itm_to_atm_roll,
    evaluate_portfolio_risk,
    expected_shortfall,
    exposure_vector,
    position_pnl,
    reprice_position,
    simulate_portfolio_pnl_distribution,
    value_at_risk,
)


class CholeskyTests(unittest.TestCase):
    def test_reconstructs_a_known_2x2_covariance(self):
        cov = [[4.0, 2.0], [2.0, 3.0]]
        L = cholesky(cov)
        reconstructed = [
            [sum(L[i][k] * L[j][k] for k in range(2)) for j in range(2)] for i in range(2)
        ]
        for i in range(2):
            for j in range(2):
                self.assertAlmostEqual(reconstructed[i][j], cov[i][j], places=6)

    def test_diagonal_covariance_gives_a_diagonal_root(self):
        L = cholesky([[9.0, 0.0], [0.0, 16.0]])
        self.assertAlmostEqual(L[0][0], 3.0)
        self.assertAlmostEqual(L[1][1], 4.0)
        self.assertAlmostEqual(L[0][1], 0.0)


class CorrelatedDrawsTests(unittest.TestCase):
    def test_independent_dims_reproduce_specified_variance(self):
        draws = correlated_normal_draws([[4.0, 0.0], [0.0, 9.0]], n_draws=8000, seed=1)
        dim0 = [d[0] for d in draws]
        dim1 = [d[1] for d in draws]
        var0 = sum(x * x for x in dim0) / len(dim0)
        var1 = sum(x * x for x in dim1) / len(dim1)
        self.assertAlmostEqual(var0, 4.0, delta=0.3)
        self.assertAlmostEqual(var1, 9.0, delta=0.5)

    def test_positive_covariance_produces_positively_correlated_draws(self):
        draws = correlated_normal_draws([[1.0, 0.8], [0.8, 1.0]], n_draws=8000, seed=2)
        cov_est = sum(d[0] * d[1] for d in draws) / len(draws)
        self.assertAlmostEqual(cov_est, 0.8, delta=0.1)


class PositionPricingTests(unittest.TestCase):
    def test_pnl_is_zero_at_the_entry_mark(self):
        pos = Position("CRM", contracts=1, strike=230.0, spot=264.13, tau_years=505 / 365.0,
                        r=0.04, q=0.0, sigma=0.4374, entry_cost_per_contract=0.0)
        mark = reprice_position(pos, spot_return=0.0, tau_elapsed_years=0.0, sigma_shift=0.0)
        pos_at_mark = Position("CRM", 1, 230.0, 264.13, 505 / 365.0, 0.04, 0.0, 0.4374, mark)
        self.assertAlmostEqual(position_pnl(pos_at_mark, 0.0, 0.0, 0.0), 0.0, places=6)

    def test_a_rally_helps_a_long_call(self):
        pos = Position("CRM", 1, 230.0, 264.13, 505 / 365.0, 0.04, 0.0, 0.4374, entry_cost_per_contract=7979.0)
        pnl_up = position_pnl(pos, spot_return=0.10, tau_elapsed_years=0.0, sigma_shift=0.0)
        pnl_flat = position_pnl(pos, spot_return=0.0, tau_elapsed_years=0.0, sigma_shift=0.0)
        self.assertGreater(pnl_up, pnl_flat)

    def test_expiring_far_otm_approaches_a_full_premium_loss(self):
        pos = Position("CRM", 1, 230.0, 264.13, 0.5, 0.04, 0.0, 0.44, entry_cost_per_contract=7979.0)
        pnl = position_pnl(pos, spot_return=-0.5, tau_elapsed_years=0.5, sigma_shift=0.0)
        self.assertAlmostEqual(pnl, -7979.0, delta=1.0)


class PortfolioSimulationTests(unittest.TestCase):
    def test_distribution_has_the_requested_length_and_real_spread(self):
        positions = [
            Position("CRM", 1, 230.0, 264.13, 1.0, 0.04, 0.0, 0.44, 7979.0),
            Position("NOW", 1, 130.0, 144.10, 1.0, 0.04, 0.0, 0.40, 4200.0),
        ]
        cov = [[0.04, 0.02], [0.02, 0.05]]
        pnls = simulate_portfolio_pnl_distribution(positions, cov, n_draws=500, tau_elapsed_years=0.06, seed=3)
        self.assertEqual(len(pnls), 500)
        self.assertGreater(max(pnls) - min(pnls), 0)


class RiskStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.pnls = [-i for i in range(100)]  # losses 0..99, uniform

    def test_value_at_risk_matches_the_hand_computed_quantile(self):
        self.assertAlmostEqual(value_at_risk(self.pnls, confidence=0.95), 95, delta=1)

    def test_expected_shortfall_averages_the_worst_tail(self):
        self.assertAlmostEqual(expected_shortfall(self.pnls, confidence=0.95), 97, delta=1)


class PortfolioRiskTests(unittest.TestCase):
    def test_passes_when_the_new_book_is_less_risky(self):
        old = [-100, -50, 0, 50, 100]
        new = [-20, -10, 0, 10, 20]
        r = evaluate_portfolio_risk(old, new)
        self.assertTrue(r.passes)

    def test_fails_on_variance_when_the_new_book_is_riskier(self):
        old = [-20, -10, 0, 10, 20]
        new = [-100, -50, 0, 50, 100]
        r = evaluate_portfolio_risk(old, new)
        self.assertFalse(r.passes_variance)
        self.assertFalse(r.passes)


class ItmToAtmRollTests(unittest.TestCase):
    IDENTITY = [[1.0, 0.0], [0.0, 1.0]]

    def test_reproduces_a_hand_worked_example(self):
        # g0=[0,0], gD=[1,0] (old, per contract), gA=[2,0] (new, per contract),
        # n_old=10, sigma=I -> a=4, b=0, c=-100, discriminant=400, n_A_max=5.
        r = evaluate_itm_to_atm_roll(
            g0=[0.0, 0.0], g_old_per_contract=[1.0, 0.0], g_new_per_contract=[2.0, 0.0],
            sigma=self.IDENTITY, n_old_contracts=10,
            es_rises=False, any_sizing_cap_breached=False,
        )
        self.assertEqual(r.n_a_max, 5)
        self.assertAlmostEqual(r.discriminant, 400.0)
        self.assertTrue(r.permitted)

    def test_unresolved_es_or_cap_check_never_permits_the_roll(self):
        r = evaluate_itm_to_atm_roll(
            g0=[0.0, 0.0], g_old_per_contract=[1.0, 0.0], g_new_per_contract=[2.0, 0.0],
            sigma=self.IDENTITY, n_old_contracts=10,
        )  # es_rises and any_sizing_cap_breached default to None
        self.assertFalse(r.permitted)
        self.assertIn("not yet evaluated", r.reason)

    def test_rising_es_blocks_an_otherwise_valid_roll(self):
        r = evaluate_itm_to_atm_roll(
            g0=[0.0, 0.0], g_old_per_contract=[1.0, 0.0], g_new_per_contract=[2.0, 0.0],
            sigma=self.IDENTITY, n_old_contracts=10, es_rises=True, any_sizing_cap_breached=False,
        )
        self.assertFalse(r.permitted)

    def test_zero_new_exposure_is_the_degenerate_case(self):
        r = evaluate_itm_to_atm_roll(
            g0=[0.0, 0.0], g_old_per_contract=[1.0, 0.0], g_new_per_contract=[0.0, 0.0],
            sigma=self.IDENTITY, n_old_contracts=10, es_rises=False, any_sizing_cap_breached=False,
        )
        self.assertFalse(r.permitted)
        self.assertIn("degenerate", r.reason)

    def test_no_old_position_gives_n_a_max_zero(self):
        r = evaluate_itm_to_atm_roll(
            g0=[0.0, 0.0], g_old_per_contract=[1.0, 0.0], g_new_per_contract=[2.0, 0.0],
            sigma=self.IDENTITY, n_old_contracts=0, es_rises=False, any_sizing_cap_breached=False,
        )
        self.assertEqual(r.n_a_max, 0)
        self.assertFalse(r.permitted)


class ExposureVectorTests(unittest.TestCase):
    def test_matches_the_s15_formula(self):
        g = exposure_vector(contracts=2, spot=100.0, delta=0.7, vega=1.2, gamma=0.01)
        self.assertAlmostEqual(g[0], 2 * 100 * 100.0 * 0.7)
        self.assertAlmostEqual(g[1], 2 * 100 * 1.2)
        self.assertAlmostEqual(g[2], 2 * 50 * 100.0**2 * 0.01)


if __name__ == "__main__":
    unittest.main()
