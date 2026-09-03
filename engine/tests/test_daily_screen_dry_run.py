"""Phase 5's frozen-fixture-day dry run (per the migration plan's Phase 5
exit criterion). Every fixture value in fixtures/dry_run_2026-09-03.json was
captured live on 2026-09-03 -- FRED/CAPE macro series, CRWD's actual daily
closes, and a real Alpha Vantage NTM read -- so this test replays
daily-screen's §1 (macro) and §2a-2b (binary event gate, panic pattern)
procedure exactly as SKILL.md documents it, without hitting the network
again. It is an integration test of the SKILL's documented sequence, not
just the individual functions each already-passing unit test covers.
"""
import json
import unittest
from pathlib import Path

from engine.config import TEMPLATE_PATH, load_config
from engine.gates import binary_event_gate
from engine.macro import (
    HardGateState,
    compute_restricted_regime,
    credit_stress_release_met,
    credit_stress_trigger,
    equity_deleveraging_release_met,
    equity_deleveraging_trigger,
    inflation_shock_release_met,
    inflation_shock_trigger,
    step_hard_gate,
)
from engine.patterns import panic_pattern
from engine.sources import NTMResult

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "dry_run_2026-09-03.json").read_text()
)
CFG = load_config(TEMPLATE_PATH)


class DailyScreenDryRunTests(unittest.TestCase):
    """Follows SKILL.md's daily-screen procedure step by step against the
    frozen 2026-09-03 fixture."""

    def test_step1_macro_gates_and_R_match_the_live_run(self):
        m = FIXTURE["macro"]
        expected = FIXTURE["expected_macro_result"]

        g1_trigger = credit_stress_trigger(m["hy_oas_now_pct"], m["hy_oas_20d_ago_pct"], CFG)
        g1_release = credit_stress_release_met(m["hy_oas_now_pct"], CFG)
        g1 = step_hard_gate(None, g1_trigger, g1_release,
                             CFG["macro_hard_gates"]["credit_stress"]["release_consecutive_closes"])
        self.assertEqual(g1.active, expected["credit_stress_active"])

        g2_trigger = inflation_shock_trigger(m["real10_delta_10d"], m["nominal10_delta_10d"], m["breakeven_delta_10d"], CFG)
        g2_release = inflation_shock_release_met(m["real10_delta_10d"], m["nominal10_delta_10d"], m["breakeven_delta_10d"], CFG)
        g2 = step_hard_gate(None, g2_trigger, g2_release,
                             CFG["macro_hard_gates"]["inflation_duration_shock"]["release_consecutive_closes"])
        self.assertEqual(g2.active, expected["inflation_duration_shock_active"])

        g3_trigger = equity_deleveraging_trigger(m["vix_now"], m["vix_prev"], m["spx_pct_below_200dma"], None, CFG)
        g3_release = equity_deleveraging_release_met(m["vix_now"], None, CFG)
        g3 = step_hard_gate(None, g3_trigger, g3_release,
                             CFG["macro_hard_gates"]["equity_deleveraging"]["release_consecutive_closes"])
        self.assertEqual(g3.active, expected["equity_deleveraging_active"])

        # Percentile history reconstructed exactly as in test_macro.py's own
        # R=4 regression: 1..100 with the captured value as its own rank position.
        history = list(range(1, 101))
        r = compute_restricted_regime(
            CFG, m["cape_now"], history, m["credit_percentile_now"], history,
            m["real30_now"], history, m["liquidity_contracting"],
        )
        self.assertEqual(r.R, expected["R"])
        self.assertEqual(r.restricted, expected["restricted"])
        self.assertEqual(r.score_threshold, expected["score_threshold"])
        self.assertEqual(r.kelly_multiplier, expected["kelly_multiplier"])

    def test_step2a_binary_event_gate_clears(self):
        c = FIXTURE["candidate"]
        result = binary_event_gate(c["days_to_next_binary_event"], CFG)
        self.assertEqual(result.passed, FIXTURE["expected_candidate_result"]["binary_event_gate_passed"])

    def test_step2b_panic_pattern_fully_clears(self):
        c = FIXTURE["candidate"]
        ntm = NTMResult(
            available=True,
            revision_pct=c["ntm_revision_pct"],
            ntm_eps_now=c["ntm_eps_now"],
            ntm_eps_60d_ago=c["ntm_eps_60d_ago"],
            analyst_count=c["ntm_analyst_count"],
        )
        result = panic_pattern(CFG, c["closes"], ntm)
        expected = FIXTURE["expected_candidate_result"]
        self.assertEqual(result.qualifies, expected["panic_pattern_qualifies"])
        self.assertEqual(result.confirmed, expected["panic_pattern_confirmed"])
        self.assertEqual(result.clears, expected["panic_pattern_clears"])

    def test_step3_is_deliberately_not_run(self):
        # S11 scoring, S12.1 liquidity, S12-14 pricing/sizing all need a live
        # option-chain pull and judgment-scored inputs this fixture correctly
        # does not fabricate -- documented, not silently skipped.
        self.assertIn("note", FIXTURE["expected_candidate_result"])


if __name__ == "__main__":
    unittest.main()
