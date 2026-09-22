"""engine.vehicle — stock-screen's disqualifiers, gates, scoring and
scenario math (ADR 0019)."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from engine.config import TEMPLATE_PATH, get, load_config
from engine.priceseries import realized_vol, rsi_wilder
from engine.vehicle import (
    JUDGED, VEHICLES, ContractQuote, JudgedFactors, MarketInputs, NameInputs,
    PriceScenario, ScreenContext, ScreenInputs, _bars_from_payload, _macro_context,
    call_returns, check_scenarios, csp_returns, factor_bounds, growth_summary, technicals,
    inputs_from_json, load_screen_config, main, name_disqualifiers, rank, screen, size_position, strike_for_delta,
    volatility_pricing_score,
)

CFG = load_screen_config()
V7 = load_config(TEMPLATE_PATH)

GOOD_STOCK = NameInputs(
    instrument_type="stock", avg_daily_dollar_volume=9e8, fcf_positive=True,
    share_count_growth_yoy_pct=1.5, revenue_growth_yoy_pct=20.0, integrity_red_flag=False,
    prior_year_quarter_revenue_usd=5e8,
)
GOOD_ETF = NameInputs(
    instrument_type="etf", avg_daily_dollar_volume=2e9, leveraged_or_inverse=False,
    aum_usd=5e10, expense_ratio_pct=0.20,
)
GOOD_CEF = NameInputs(
    instrument_type="cef", avg_daily_dollar_volume=4e7, aum_usd=8e8, expense_ratio_pct=1.4,
    last_price=19.0, nav_per_share=20.0, nav_age_days=1, integrity_red_flag=False,
)  # a 5% discount, NAV struck yesterday
JUDGED_ALL = JudgedFactors(8, 8, 7, 8, 6, 6)
MARKET = MarketInputs(rsi14=40, pct_above_50dma=-8, hv30=0.40, atm_iv=0.42,
                      days_to_earnings=70, days_to_nearest_catalyst=40)
SHORT_CALL = ContractQuote("2026-12-18", 88, 380, 0.68, 42.0, 43.2, 900, 0.42)
CSP = ContractQuote("2026-11-20", 60, 370, 0.25, 9.8, 10.3, 700, 0.44)
LEAP = ContractQuote("2028-01-21", 487, 340, 0.76, 118.0, 122.5, 820, 0.40)
LIVE_RESTRICTED = ScreenContext(quotes_live=True, macro_restricted=True,
                                macro_hard_gate_active=False, option_level="option_level_2")


def inputs(**overrides) -> ScreenInputs:
    base = ScreenInputs(
        ticker="AAA", name=GOOD_STOCK, judged=JUDGED_ALL, market=MARKET,
        catalyst_horizon_days=420, short_call=SHORT_CALL, csp=CSP, leap=LEAP,
    )
    return replace(base, **overrides)


def failing(checks):
    return {c.name for c in checks if not c.passed}


class ConfigTests(unittest.TestCase):
    def test_every_vehicle_has_weights_summing_to_one(self):
        for v in VEHICLES:
            self.assertAlmostEqual(sum(get(CFG, f"weights.{v}").values()), 1.0, places=9, msg=v)

    def test_weight_keys_are_known_factors(self):
        known = set(JUDGED) | {"volatility_pricing", "iv_richness"}
        for v in VEHICLES:
            self.assertLessEqual(set(get(CFG, f"weights.{v}")), known, v)

    def test_sizing_caps_default_to_v7_unvalidated_cap(self):
        # §17: no calibration record yet, so every vehicle gets the unvalidated cap.
        unvalidated = get(V7, "sizing.caps_pct_of_nav.unvalidated_setup")
        self.assertEqual(set(get(CFG, "sizing.max_loss_pct_nav").values()), {unvalidated})
        self.assertNotIn("leap", get(CFG, "sizing.max_loss_pct_nav"))


class NameDisqualifierTests(unittest.TestCase):
    def test_clean_stock_passes(self):
        self.assertEqual(failing(name_disqualifiers(CFG, GOOD_STOCK)), set())

    def test_missing_facts_fail_closed(self):
        self.assertEqual(
            failing(name_disqualifiers(CFG, NameInputs(instrument_type="stock"))),
            {"dollar_volume", "cash_runway", "dilution", "integrity"},
        )

    def test_heavy_dilution_without_growth_fails(self):
        n = replace(GOOD_STOCK, share_count_growth_yoy_pct=25.0, revenue_growth_yoy_pct=20.0)
        self.assertIn("dilution", failing(name_disqualifiers(CFG, n)))

    def test_heavy_dilution_with_twice_the_growth_passes(self):
        n = replace(GOOD_STOCK, share_count_growth_yoy_pct=25.0, revenue_growth_yoy_pct=50.0)
        self.assertNotIn("dilution", failing(name_disqualifiers(CFG, n)))

    def test_growth_from_a_tiny_base_cannot_offset_dilution(self):
        # QUBT, 2026-09-21: shares +58.9%, revenue +9,000% from a $61K quarter.
        n = replace(GOOD_STOCK, share_count_growth_yoy_pct=58.9, revenue_growth_yoy_pct=9000.0,
                    prior_year_quarter_revenue_usd=61_000)
        self.assertIn("dilution", failing(name_disqualifiers(CFG, n)))
        unknown = replace(n, prior_year_quarter_revenue_usd=None)
        self.assertIn("dilution", failing(name_disqualifiers(CFG, unknown)))

    def test_one_time_acquisition_dilution_passes_with_its_reason(self):
        # CEG, 2026-09-21: shares +14.7% from the Calpine deal, revenue +23%.
        n = replace(GOOD_STOCK, share_count_growth_yoy_pct=14.7, revenue_growth_yoy_pct=23.0)
        self.assertIn("dilution", failing(name_disqualifiers(CFG, n)))
        acq = next(c for c in name_disqualifiers(CFG, replace(n, dilution_from_acquisition=True))
                   if c.name == "dilution")
        self.assertTrue(acq.passed)
        self.assertIn("acquisition", acq.reason)

    def test_short_runway_fails_unless_funded(self):
        burning = replace(GOOD_STOCK, fcf_positive=False, cash_runway_months=8)
        self.assertIn("cash_runway", failing(name_disqualifiers(CFG, burning)))
        funded = replace(burning, funding_secured=True)
        self.assertNotIn("cash_runway", failing(name_disqualifiers(CFG, funded)))

    def test_integrity_flag_fails(self):
        n = replace(GOOD_STOCK, integrity_red_flag=True)
        self.assertIn("integrity", failing(name_disqualifiers(CFG, n)))

    def test_clean_etf_skips_company_checks(self):
        checks = name_disqualifiers(CFG, GOOD_ETF)
        self.assertEqual(failing(checks), set())
        self.assertNotIn("dilution", {c.name for c in checks})

    def test_leveraged_etf_fails(self):
        n = replace(GOOD_ETF, leveraged_or_inverse=True)
        self.assertIn("leveraged_or_inverse", failing(name_disqualifiers(CFG, n)))

    def test_clean_cef_passes_and_skips_company_checks(self):
        checks = name_disqualifiers(CFG, GOOD_CEF)
        self.assertEqual(failing(checks), set())
        names = {c.name for c in checks}
        self.assertTrue({"premium_to_nav", "nav_age", "net_assets", "expense_ratio", "integrity"} <= names)
        self.assertNotIn("dilution", names)
        self.assertNotIn("leveraged_or_inverse", names)

    def test_cef_premium_over_the_cap_fails_but_any_discount_passes(self):
        rich = replace(GOOD_CEF, last_price=25.0)  # 25% premium
        self.assertIn("premium_to_nav", failing(name_disqualifiers(CFG, rich)))
        deep = replace(GOOD_CEF, last_price=10.0)  # 50% discount
        self.assertNotIn("premium_to_nav", failing(name_disqualifiers(CFG, deep)))

    def test_cef_stale_or_missing_nav_fails_closed(self):
        self.assertIn("nav_age", failing(name_disqualifiers(CFG, replace(GOOD_CEF, nav_age_days=140))))
        self.assertIn("nav_age", failing(name_disqualifiers(CFG, replace(GOOD_CEF, nav_age_days=None))))
        self.assertIn("premium_to_nav", failing(name_disqualifiers(CFG, replace(GOOD_CEF, nav_per_share=None))))

    def test_cef_uses_its_own_expense_cap(self):
        # 1.4% would fail an ETF's 1.0% cap; a CEF's cap is 2.0%.
        self.assertNotIn("expense_ratio", failing(name_disqualifiers(CFG, GOOD_CEF)))
        self.assertIn("expense_ratio", failing(name_disqualifiers(CFG, replace(GOOD_CEF, expense_ratio_pct=2.5))))

    def test_dxyz_as_of_2026_09_22_fails_only_on_expenses(self):
        dxyz = NameInputs(instrument_type="cef", avg_daily_dollar_volume=2.92e7, aum_usd=1.045e9,
                          expense_ratio_pct=2.5, last_price=30.99, nav_per_share=34.30, nav_age_days=84,
                          integrity_red_flag=False)
        checks = name_disqualifiers(CFG, dxyz)
        self.assertEqual(failing(checks), {"expense_ratio"})
        prem = next(c for c in checks if c.name == "premium_to_nav")
        self.assertIn("9.7% discount", prem.reason)

    def test_cef_has_no_earnings_so_no_crush_floor_penalty(self):
        m = replace(MARKET, days_to_earnings=None, atm_iv=0.56)
        rich = replace(SHORT_CALL, implied_volatility=0.56)
        sc = screen(CFG, V7, inputs(name=GOOD_CEF, market=m, short_call=rich), LIVE_RESTRICTED).vehicles["short_call"]
        self.assertEqual(sc.score_ceiling, sc.score_floor)

    def test_unknown_instrument_type_fails(self):
        self.assertEqual(failing(name_disqualifiers(CFG, NameInputs(instrument_type="bond"))),
                         {"instrument_type"})


class FactorTests(unittest.TestCase):
    def test_missing_judgment_is_bounded_not_guessed(self):
        b = factor_bounds(CFG, JudgedFactors(catalyst_strength=None, **{
            k: 5 for k in JUDGED if k != "catalyst_strength"}), MARKET)
        self.assertEqual((b.floor["catalyst_strength"], b.ceiling["catalyst_strength"]), (0.0, 10.0))

    def test_out_of_range_judgment_raises(self):
        with self.assertRaises(ValueError):
            factor_bounds(CFG, replace(JUDGED_ALL, fundamental_quality=11), MARKET)

    def test_extended_chart_caps_technical_both_bounds(self):
        b = factor_bounds(CFG, replace(JUDGED_ALL, technical_setup=9), replace(MARKET, rsi14=81))
        self.assertEqual((b.floor["technical_setup"], b.ceiling["technical_setup"]), (3.0, 3.0))

    def test_unverified_extension_caps_the_floor_only(self):
        b = factor_bounds(CFG, replace(JUDGED_ALL, technical_setup=9), replace(MARKET, rsi14=None))
        self.assertEqual((b.floor["technical_setup"], b.ceiling["technical_setup"]), (3.0, 9.0))

    def test_volatility_from_iv_rank(self):
        self.assertAlmostEqual(volatility_pricing_score(CFG, MarketInputs(iv_rank=30)), 7.0)

    def test_volatility_from_iv_hv_ratio(self):
        self.assertAlmostEqual(volatility_pricing_score(CFG, MarketInputs(atm_iv=0.36, hv30=0.40)), 10.0)
        self.assertAlmostEqual(volatility_pricing_score(CFG, MarketInputs(atm_iv=0.48, hv30=0.40)), 5.0)
        self.assertAlmostEqual(volatility_pricing_score(CFG, MarketInputs(atm_iv=0.60, hv30=0.40)), 0.0)

    def test_iv_richness_is_the_complement(self):
        b = factor_bounds(CFG, JUDGED_ALL, MarketInputs(iv_rank=80, rsi14=50, pct_above_50dma=0))
        self.assertAlmostEqual(b.floor["iv_richness"], 8.0)

    def test_unknown_volatility_bounds_both_directions(self):
        b = factor_bounds(CFG, JUDGED_ALL, replace(MARKET, atm_iv=None))
        self.assertEqual((b.floor["iv_richness"], b.ceiling["iv_richness"]), (0.0, 10.0))


class ScreenTests(unittest.TestCase):
    def test_disqualified_name_is_not_scored(self):
        r = screen(CFG, V7, inputs(name=replace(GOOD_STOCK, integrity_red_flag=True)), LIVE_RESTRICTED)
        self.assertEqual(r.verdict, "DISQUALIFIED")
        self.assertEqual(r.vehicles, {})
        self.assertIsNone(r.composite)

    def test_clean_inputs_score_every_vehicle(self):
        r = screen(CFG, V7, inputs(), LIVE_RESTRICTED)
        self.assertEqual(set(r.vehicles), set(VEHICLES))
        self.assertTrue(all(v.eligible for v in r.vehicles.values()))
        self.assertEqual(r.verdict, "BEST FIT")

    def test_same_inputs_same_result(self):
        self.assertEqual(screen(CFG, V7, inputs(), LIVE_RESTRICTED), screen(CFG, V7, inputs(), LIVE_RESTRICTED))

    def test_tie_goes_to_the_configured_order(self):
        # Shares and LEAP both land on 76 with these inputs; the user's order
        # (2026-09-21) leans toward upside, so the LEAP takes the tie.
        r = screen(CFG, V7, inputs(), LIVE_RESTRICTED)
        self.assertEqual(r.vehicles["shares"].score_floor, r.vehicles["leap"].score_floor)
        self.assertEqual(r.best_vehicle, "leap")
        self.assertEqual(get(CFG, "verdict.tie_break_order"), ["leap", "shares", "short_call", "csp"])

    def test_missing_contract_makes_vehicle_ineligible(self):
        r = screen(CFG, V7, inputs(leap=None), LIVE_RESTRICTED)
        self.assertFalse(r.vehicles["leap"].eligible)
        self.assertEqual(failing(r.vehicles["leap"].gates), {"contract"})

    def test_leap_delta_uses_v7_regime_band(self):
        low = replace(LEAP, delta=0.62)
        restricted = screen(CFG, V7, inputs(leap=low), LIVE_RESTRICTED)
        normal = screen(CFG, V7, inputs(leap=low), replace(LIVE_RESTRICTED, macro_restricted=False))
        self.assertIn("delta_policy", failing(restricted.vehicles["leap"].gates))
        self.assertTrue(normal.vehicles["leap"].eligible)

    def test_leap_below_055_delta_is_prohibited_even_in_leverage_mode(self):
        ctx = replace(LIVE_RESTRICTED, macro_restricted=False, leverage_mode=True)
        r = screen(CFG, V7, inputs(leap=replace(LEAP, delta=0.45)), ctx)
        self.assertIn("delta_policy", failing(r.vehicles["leap"].gates))

    def test_leap_blocked_by_active_hard_gate(self):
        r = screen(CFG, V7, inputs(), replace(LIVE_RESTRICTED, macro_hard_gate_active=True))
        self.assertIn("delta_policy", failing(r.vehicles["leap"].gates))

    def test_leap_fails_closed_without_macro_state(self):
        ctx = replace(LIVE_RESTRICTED, macro_restricted=None, macro_hard_gate_active=None)
        r = screen(CFG, V7, inputs(), ctx)
        self.assertIn("macro_state", failing(r.vehicles["leap"].gates))

    def test_leap_expiring_before_the_catalyst_fails(self):
        r = screen(CFG, V7, inputs(catalyst_horizon_days=600), LIVE_RESTRICTED)
        self.assertIn("catalyst_duration", failing(r.vehicles["leap"].gates))

    def test_leap_uses_v7_liquidity_thresholds(self):
        # 400 OI clears stock-screen's short-dated floor (250) but not v7's (500).
        r = screen(CFG, V7, inputs(leap=replace(LEAP, open_interest=400)), LIVE_RESTRICTED)
        self.assertIn("open_interest", failing(r.vehicles["leap"].gates))

    def test_earnings_inside_expiry_with_expensive_iv_penalizes_short_call(self):
        cheap = screen(CFG, V7, inputs(), LIVE_RESTRICTED)
        crush = screen(CFG, V7, inputs(market=replace(MARKET, days_to_earnings=20, atm_iv=0.56),
                                       short_call=replace(SHORT_CALL, implied_volatility=0.56)), LIVE_RESTRICTED)
        drop = cheap.vehicles["short_call"].score_floor - crush.vehicles["short_call"].score_floor
        vol_drop = 10 * 0.20 * (volatility_pricing_score(CFG, MARKET)
                                - volatility_pricing_score(CFG, replace(MARKET, atm_iv=0.56)))
        self.assertEqual(drop, round(vol_drop + get(CFG, "vehicles.short_call.iv_crush_penalty")))

    def test_crush_is_judged_on_the_contract_not_the_30_day_atm(self):
        # PLTR, 2026-09-21: 30-day ATM IV/HV 1.13 read "not expensive", but
        # the Nov call spanning earnings carried 58% IV against 42% realized.
        m = replace(MARKET, days_to_earnings=40, atm_iv=0.475, hv30=0.42)
        base = screen(CFG, V7, inputs(market=m, short_call=replace(SHORT_CALL, implied_volatility=0.475)), LIVE_RESTRICTED)
        rich = screen(CFG, V7, inputs(market=m, short_call=replace(SHORT_CALL, implied_volatility=0.58)), LIVE_RESTRICTED)
        self.assertEqual(base.vehicles["short_call"].score_floor - rich.vehicles["short_call"].score_floor,
                         get(CFG, "vehicles.short_call.iv_crush_penalty"))
        self.assertTrue(any("IV crush" in w for w in rich.vehicles["short_call"].warnings))

    def test_etf_without_earnings_date_takes_no_crush_penalty(self):
        m = replace(MARKET, days_to_earnings=None, atm_iv=0.56)  # options expensive
        rich = replace(SHORT_CALL, implied_volatility=0.56)
        stock = screen(CFG, V7, inputs(market=m, short_call=rich), LIVE_RESTRICTED).vehicles["short_call"]
        etf = screen(CFG, V7, inputs(name=GOOD_ETF, market=m, short_call=rich), LIVE_RESTRICTED).vehicles["short_call"]
        self.assertEqual(stock.score_ceiling - stock.score_floor, get(CFG, "vehicles.short_call.iv_crush_penalty"))
        self.assertEqual(etf.score_ceiling, etf.score_floor)

    def test_no_catalyst_inside_expiry_penalizes_short_call(self):
        r = screen(CFG, V7, inputs(market=replace(MARKET, days_to_nearest_catalyst=200)), LIVE_RESTRICTED)
        base = screen(CFG, V7, inputs(), LIVE_RESTRICTED)
        self.assertEqual(base.vehicles["short_call"].score_floor - r.vehicles["short_call"].score_floor,
                         get(CFG, "vehicles.short_call.no_catalyst_penalty"))

    def test_unknown_catalyst_costs_floor_not_ceiling(self):
        r = screen(CFG, V7, inputs(market=replace(MARKET, days_to_nearest_catalyst=None)), LIVE_RESTRICTED)
        sc = r.vehicles["short_call"]
        self.assertEqual(sc.score_ceiling - sc.score_floor, get(CFG, "vehicles.short_call.no_catalyst_penalty"))

    def test_otm_short_call_needs_leverage_mode_and_is_labeled(self):
        otm = replace(SHORT_CALL, delta=0.40)
        plain = screen(CFG, V7, inputs(short_call=otm), LIVE_RESTRICTED)
        levered = screen(CFG, V7, inputs(short_call=otm), replace(LIVE_RESTRICTED, leverage_mode=True))
        self.assertIn("delta", failing(plain.vehicles["short_call"].gates))
        self.assertTrue(levered.vehicles["short_call"].eligible)
        self.assertEqual(levered.vehicles["short_call"].label, "LEVERAGE")

    def test_csp_needs_a_confirmed_permitting_options_level(self):
        for level in (None, "", "option_level_1"):
            r = screen(CFG, V7, inputs(), replace(LIVE_RESTRICTED, option_level=level))
            self.assertIn("options_level", failing(r.vehicles["csp"].gates), level)

    def test_wide_spread_is_a_veto_live_but_a_warning_after_hours(self):
        wide = replace(SHORT_CALL, bid=40.0, ask=45.0)
        live = screen(CFG, V7, inputs(short_call=wide), LIVE_RESTRICTED)
        closed = screen(CFG, V7, inputs(short_call=wide), replace(LIVE_RESTRICTED, quotes_live=False))
        self.assertIn("quoted_spread", failing(live.vehicles["short_call"].gates))
        self.assertTrue(closed.vehicles["short_call"].eligible)
        self.assertTrue(any("provisional" in w for w in closed.vehicles["short_call"].warnings))

    def test_closed_market_caps_option_confidence_at_med(self):
        r = screen(CFG, V7, inputs(), replace(LIVE_RESTRICTED, quotes_live=False))
        self.assertEqual(r.vehicles["leap"].confidence, "Med")
        self.assertEqual(r.vehicles["shares"].confidence, "High")

    def test_weak_name_is_a_pass(self):
        weak = JudgedFactors(4, 4, 4, 4, 4, 4)
        r = screen(CFG, V7, inputs(judged=weak), LIVE_RESTRICTED)
        self.assertEqual(r.verdict, "PASS")
        self.assertIsNotNone(r.composite)

    def test_shares_stay_eligible_when_no_option_is_priced(self):
        r = screen(CFG, V7, inputs(name=GOOD_ETF, short_call=None, csp=None, leap=None), LIVE_RESTRICTED)
        self.assertEqual(r.best_vehicle, "shares")
        self.assertEqual([v for v, x in r.vehicles.items() if x.eligible], ["shares"])

    def test_pass_needs_the_ceiling_below_the_line_too(self):
        weak = JudgedFactors(4, 4, 4, 4, 4, None)
        r = screen(CFG, V7, inputs(judged=weak), LIVE_RESTRICTED)
        self.assertEqual(r.verdict, "PASS")  # even a 10 on sentiment can't lift it to 60
        unknown = screen(CFG, V7, inputs(judged=JudgedFactors()), LIVE_RESTRICTED)
        self.assertEqual(unknown.verdict, "INCOMPLETE")
        self.assertIn("pass line", unknown.verdict_reason)

    def test_missing_factors_widen_the_gap_and_lower_confidence(self):
        r = screen(CFG, V7, inputs(judged=replace(JUDGED_ALL, catalyst_strength=None,
                                                  sentiment_positioning=None)), LIVE_RESTRICTED)
        s = r.vehicles["shares"]
        self.assertEqual(s.score_ceiling - s.score_floor, 20)
        self.assertEqual(s.confidence, "Low")

    def test_rank_orders_by_composite_then_puts_disqualified_last(self):
        strong = screen(CFG, V7, inputs(ticker="STRONG"), LIVE_RESTRICTED)
        weak = screen(CFG, V7, inputs(ticker="WEAK", judged=JudgedFactors(5, 5, 5, 5, 5, 5)), LIVE_RESTRICTED)
        dq = screen(CFG, V7, inputs(ticker="DQ", name=replace(GOOD_STOCK, integrity_red_flag=True)), LIVE_RESTRICTED)
        self.assertEqual([r.ticker for r in rank([dq, weak, strong])], ["STRONG", "WEAK", "DQ"])


class ScenarioTests(unittest.TestCase):
    SCEN = [PriceScenario("bear", 0.25, 80.0), PriceScenario("base", 0.5, 110.0), PriceScenario("bull", 0.25, 140.0)]

    def test_probabilities_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            check_scenarios([PriceScenario("a", 0.5, 1.0), PriceScenario("b", 0.4, 1.0)])

    def test_call_held_to_expiry_is_intrinsic(self):
        rets = call_returns(10.0, 100.0, self.SCEN, 0.0, 0.04, 0.0, 0.4)
        self.assertEqual(rets, [-1.0, 0.0, 3.0])

    def test_csp_return_on_collateral(self):
        rets = csp_returns(2.0, 100.0, self.SCEN)
        self.assertEqual(rets, [(2.0 - 20.0) / 100.0, 0.02, 0.02])

    def test_total_loss_scenario_makes_position_geometric_return_minus_one(self):
        g = growth_summary([0.25, 0.5, 0.25], [-1.0, 0.0, 3.0], 0.25)
        self.assertEqual(g.position_geometric_return, -1.0)
        self.assertGreater(g.kelly_f_star, 0)
        self.assertGreater(g.egr, 0)

    def test_no_edge_sizes_to_zero(self):
        g = growth_summary([0.5, 0.5], [-0.2, 0.1], 0.25)
        s = size_position(CFG, "shares", g, [-0.2, 0.1], 100.0, nav=100000)
        self.assertEqual((s.binding, s.units, s.fraction_of_nav), ("no_edge", 0, 0.0))

    def test_max_loss_cap_binds_on_a_long_call(self):
        rets = [-1.0, 0.0, 3.0]
        g = growth_summary([0.25, 0.5, 0.25], rets, 0.25)
        s = size_position(CFG, "short_call", g, rets, 1000.0, nav=1_000_000)
        self.assertEqual(s.binding, "max_loss_cap")
        self.assertAlmostEqual(s.fraction_of_nav, 0.0025)
        self.assertEqual(s.units, 2)
        self.assertAlmostEqual(s.min_nav_for_one_unit, 400_000)

    def test_leap_is_never_sized_here(self):
        g = growth_summary([0.5, 0.5], [-0.5, 1.0], 0.25)
        with self.assertRaises(ValueError):
            size_position(CFG, "leap", g, [-0.5, 1.0], 1000.0, nav=1e6)


class StrikeTests(unittest.TestCase):
    def test_strike_round_trips_through_black_scholes_delta(self):
        from engine.optmodel import bs_call_delta
        for delta, dte, iv in ((0.70, 60, 0.45), (0.76, 487, 0.66), (0.85, 400, 0.30)):
            k = strike_for_delta(100.0, delta, dte, iv)
            self.assertAlmostEqual(bs_call_delta(100.0, k, dte / 365, 0.04, 0.0, iv), delta, places=6)

    def test_a_quarter_delta_put_shares_the_three_quarter_call_strike(self):
        self.assertAlmostEqual(strike_for_delta(100, 0.25, 45, 0.4, put=True),
                               strike_for_delta(100, 0.75, 45, 0.4))

    def test_factor_notes_say_when_the_extension_cap_did_not_apply(self):
        notes = factor_bounds(CFG, JUDGED_ALL, MARKET).notes
        self.assertTrue(any(n.startswith("extension cap not applied") for n in notes))
        self.assertTrue(any(n.startswith("volatility_pricing") for n in notes))


class TechnicalsTests(unittest.TestCase):
    def test_rsi_of_a_series_that_only_rises_is_100(self):
        self.assertEqual(rsi_wilder([float(i) for i in range(1, 60)]), 100.0)

    def test_realized_vol_of_constant_growth_is_zero(self):
        self.assertAlmostEqual(realized_vol([100 * 1.001**i for i in range(60)]), 0.0, places=9)

    def test_short_series_takes_indicators_as_given_and_derives_hv(self):
        closes = [100 * 1.001**i for i in range(31)]
        t = technicals(closes, rsi14=48.5, sma50=90.0, high_52w=125.0, avg_volume=1e6)
        self.assertEqual(t["market"]["rsi14"], 48.5)
        self.assertAlmostEqual(t["market"]["pct_above_50dma"], (closes[-1] / 90.0 - 1) * 100)
        self.assertAlmostEqual(t["market"]["hv30"], 0.0, places=9)
        self.assertAlmostEqual(t["name"]["avg_daily_dollar_volume"], 1e6 * closes[-1])
        self.assertIsNone(t["for_judgment"]["pct_vs_200dma"])

    def test_technicals_blocks_load_as_screen_inputs(self):
        t = technicals([100 * 1.001**i for i in range(31)], rsi14=50, sma50=99, avg_volume=1e6)
        MarketInputs(**t["market"])
        NameInputs(instrument_type="stock", **t["name"])

    def test_trimming_removes_a_single_earnings_gap(self):
        closes = [100 * 1.004**i * (1 + 0.01 * (-1) ** i) for i in range(31)]
        gapped = closes[:20] + [c * 0.85 for c in closes[20:]]  # one -15% day
        self.assertGreater(realized_vol(gapped, 30), realized_vol(closes, 30) + 0.15)
        self.assertAlmostEqual(realized_vol(gapped, 30, trim_largest=1),
                               realized_vol(closes, 30, trim_largest=1), delta=0.02)

    def test_technicals_reports_trimmed_and_untrimmed_hv(self):
        closes = [100 * 1.004**i * (1 + 0.01 * (-1) ** i) for i in range(31)]
        t = technicals(closes[:20] + [c * 0.85 for c in closes[20:]], hv_trim_largest=1)
        self.assertLess(t["market"]["hv30"], t["for_judgment"]["hv30_untrimmed"])

    def test_short_series_never_derives_rsi_or_long_averages(self):
        t = technicals([float(100 + i % 3) for i in range(40)])
        self.assertIsNone(t["market"]["rsi14"])
        self.assertIsNone(t["market"]["pct_above_50dma"])
        self.assertIsNotNone(t["market"]["hv30"])

    def test_bars_payload_drops_interpolated_bars(self):
        payload = {"data": {"results": [{"symbol": "AAA", "bars": [
            {"begins_at": "2026-09-02T00:00:00Z", "close_price": "11", "volume": 5},
            {"begins_at": "2026-09-01T00:00:00Z", "close_price": "10", "volume": 4},
            {"begins_at": "2026-09-03T00:00:00Z", "close_price": "11", "volume": 0, "interpolated": True},
        ]}]}}
        self.assertEqual(_bars_from_payload(payload), ([10.0, 11.0], [4.0, 5.0]))


class CliTests(unittest.TestCase):
    def test_unknown_keys_raise_at_every_level(self):
        base = {"ticker": "A", "instrument_type": "stock"}
        for bad in ({**base, "notes": "x"}, {**base, "context": {"quotes_live": True, "csp_ok": True}},
                    {**base, "contracts": {"call": {}}}, {**base, "market": {"rsi": 50}},
                    {**base, "judged": {"fundamentals": 5}}):
            with self.assertRaises((ValueError, TypeError)):
                inputs_from_json(bad)

    def test_missing_macro_file_reads_unknown(self):
        m = _macro_context("/nonexistent/macro-latest.json", V7, "2026-09-21")
        self.assertIsNone(m["restricted"])
        self.assertIsNone(m["hard_gate_active"])

    def test_screen_ranks_files_and_labels_the_leap_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            macro = Path(tmp, "macro.json")
            macro.write_text(json.dumps({
                "last_refreshed": "2026-09-20",
                "restricted_regime": {"restricted": True, "R": 3},
                "hard_gates": {"credit_stress": {"active": False}},
            }))
            watch = Path(tmp, "watchlist.json")
            watch.write_text(json.dumps({"names": [{"ticker": "AAA", "status": "active"}]}))
            a = Path(tmp, "a.json")
            a.write_text(json.dumps({
                "ticker": "AAA", "instrument_type": "stock",
                "context": {"quotes_live": True, "option_level": "option_level_2"},
                "name": {"avg_daily_dollar_volume": 9e8, "fcf_positive": True,
                         "share_count_growth_yoy_pct": 1.5, "revenue_growth_yoy_pct": 20,
                         "integrity_red_flag": False},
                "judged": {k: {"score": 7, "evidence": "[FACT] ..."} for k in JUDGED},
                "market": {"rsi14": 40, "pct_above_50dma": -8, "hv30": 0.4, "atm_iv": 0.42,
                           "days_to_earnings": 70, "days_to_nearest_catalyst": 40},
                "catalyst_horizon_days": 420,
                "contracts": {"leap": {"expiration": "2028-01-21", "dte_days": 487, "strike": 340,
                                       "delta": 0.76, "bid": 118.0, "ask": 122.5, "open_interest": 820}},
            }))
            b = Path(tmp, "b.json")
            b.write_text(json.dumps({"ticker": "LEV", "instrument_type": "etf",
                                     "name": {"leveraged_or_inverse": True}}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["screen", "--v7-config", str(TEMPLATE_PATH), "--macro", str(macro),
                      "--watchlist", str(watch), "--today", "2026-09-21", str(b), str(a)])
            out = json.loads(buf.getvalue())
        self.assertEqual([r["ticker"] for r in out["ranked"]], ["AAA", "LEV"])
        self.assertTrue(out["macro"]["restricted"])
        self.assertIn("ON v7 WATCHLIST", out["ranked"][0]["vehicles"]["leap"]["label"])
        self.assertEqual(out["ranked"][1]["verdict"], "DISQUALIFIED")


if __name__ == "__main__":
    unittest.main()
