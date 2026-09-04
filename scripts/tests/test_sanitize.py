"""Leak tests for scripts/sanitize.py v2 (Phase 7 / ADR 0002).

Uses only synthetic fixtures with fabricated account_ref/nav_at_run values --
never a real private-repo file. Public CI must never depend on private-repo
access; that boundary is exactly what these tests exist to protect.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sanitize import sanitize, FORBIDDEN_DOCUMENT_TERMS, clean_text


def _base_private(**overrides):
    d = {
        "schema_version": 1,
        "framework_version": "7.0",
        "date": "2099-01-15",
        "run_type": "daily_screen",
        "run_time_note": "A routine run.",
        "result": "NO TRADE",
        "macro": {
            "hard_gates_active": {"credit_stress": False, "inflation_duration_shock": False, "equity_deleveraging": False},
            "R": 2, "restricted": False, "score_threshold": 75, "kelly_multiplier": 0.25, "as_of": "2099-01-14",
        },
        "account_ref": "999999999",
        "nav_at_run": 123456.78,
        "watchlist_reviewed": "2099-01-15",
        "candidates_examined": 3,
        "candidates_clearing_s7_s10": 1,
        "candidates_clearing_s11": 0,
        "per_name": {
            "FAKECO": {
                "mechanism": "M1", "fail_category": "s10_no_pattern",
                "result": "NO TRADE -- no S10 pattern cleared",
            },
            "FAKECO2": {
                "mechanism": "M2", "fail_category": "s11_threshold",
                "s11_score_low": 60, "s11_score_high": 74, "s11_threshold": 75,
                "result": "NO TRADE -- fails S11 threshold",
            },
            "FAKECO3": {
                "mechanism": "M3", "fail_category": "cleared",
                "s11_score_low": 82, "s11_score_high": 82, "s11_threshold": 75,
                "result": "CANDIDATE -- cleared every gate",
            },
        },
        "nearest_misses": ["FAKECO2 (74 vs 75 threshold, -1)"],
        "notable_finding": "A synthetic finding for testing.",
    }
    d.update(overrides)
    return d


class SanitizeLeakTests(unittest.TestCase):
    def test_account_ref_and_nav_never_appear_in_output(self):
        pub = sanitize(_base_private())
        blob = json.dumps(pub)
        self.assertNotIn("999999999", blob)
        self.assertNotIn("123456.78", blob)
        self.assertNotIn("account_ref", blob)
        self.assertNotIn("nav_at_run", blob)

    def test_forbidden_document_terms_absent_from_a_clean_run(self):
        pub = sanitize(_base_private())
        blob = json.dumps(pub)
        for term in FORBIDDEN_DOCUMENT_TERMS:
            self.assertNotIn(term, blob, f"forbidden term {term!r} leaked into public output")

    def test_clean_text_tripwire_fires_on_holdings_language(self):
        with self.assertRaises(SystemExit):
            clean_text("we own a large stake in this name", "test_field")
        with self.assertRaises(SystemExit):
            clean_text("our position in this name is sizable", "test_field")

    def test_clean_text_passes_ordinary_market_commentary(self):
        # "position" and "holding" alone must NOT false-positive (the 2026-08-12 bug).
        self.assertEqual(clean_text("the Fed is holding rates steady", "f"), "the Fed is holding rates steady")
        self.assertEqual(clean_text("strong positioning ahead of earnings", "f"), "strong positioning ahead of earnings")

    def test_refuses_non_v7_input(self):
        with self.assertRaises(SystemExit):
            sanitize(_base_private(framework_version="6.1"))

    def test_result_trusts_private_result_field_not_free_text(self):
        # Regression: run_time_note mentioning a DIFFERENT day's "DATA INSUFFICIENT"
        # outcome in passing must not flip THIS day's result (found 2026-09-04).
        priv = _base_private(run_time_note="An earlier firing today wrote a NO TRADE -- DATA INSUFFICIENT record.")
        pub = sanitize(priv)
        self.assertEqual(pub["result"], "NO_TRADE")

    def test_data_insufficient_when_per_name_absent(self):
        priv = _base_private(per_name=None, result="NO TRADE")
        pub = sanitize(priv)
        self.assertEqual(pub["result"], "DATA_INSUFFICIENT")

    def test_holiday_respected_even_without_per_name(self):
        priv = _base_private(per_name=None, result="HOLIDAY")
        pub = sanitize(priv)
        self.assertEqual(pub["result"], "HOLIDAY")

    def test_candidate_when_something_clears(self):
        pub = sanitize(_base_private(candidates_clearing_s11=1))
        self.assertEqual(pub["result"], "CANDIDATE")
        self.assertEqual(len(pub["candidates"]), 1)
        self.assertEqual(pub["candidates"][0]["ticker"], "FAKECO3")

    def test_gates_summary_aggregates_by_fail_category_with_human_readable_labels(self):
        # Public JSON carries GATE_LABELS' relabeled text, not the raw fail_category
        # code -- keeps the artifact self-describing for any consumer, matching
        # v6.1's own GATE_LABELS convention (2026-09-04 fix: the raw codes were
        # showing up unlabeled on the live dashboard next to v6.1's formatted ones).
        pub = sanitize(_base_private())
        self.assertEqual(pub["gates_summary"].get("no entry pattern"), 1)
        self.assertEqual(pub["gates_summary"].get("scored below threshold"), 1)
        self.assertNotIn("s10_no_pattern", pub["gates_summary"])
        self.assertNotIn("s11_threshold", pub["gates_summary"])
        # The cleared name must not appear in gates_summary at all.
        self.assertNotIn("cleared", pub["gates_summary"])

    def test_nearest_miss_includes_score_summary_not_full_dimension_breakdown(self):
        pub = sanitize(_base_private())
        nm = pub["nearest_misses"][0]
        self.assertEqual(nm["ticker"], "FAKECO2")
        self.assertEqual(nm["score"], "scored 60-74/75 needed")
        # Full S11 dimension-by-dimension detail is never in the private fixture's
        # per_name entry to begin with here, but assert the public schema has no
        # key that could carry it either.
        self.assertNotIn("s11_dimensions", nm)

    def test_macro_object_carries_only_safe_aggregate_fields(self):
        pub = sanitize(_base_private())
        self.assertEqual(set(pub["macro"].keys()), {"R", "restricted", "score_threshold", "hard_gate_active", "hard_gate_names"})

    def test_output_json_serializable_and_well_formed(self):
        pub = sanitize(_base_private())
        json.dumps(pub)  # must not raise
        for key in ("schema_version", "kind", "disclaimer", "date", "result"):
            self.assertIn(key, pub)


if __name__ == "__main__":
    unittest.main()
