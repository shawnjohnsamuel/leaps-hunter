"""engine.feed — screener-feed persistence and promotion (ADR 0020)."""
import copy
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.feed import (
    normalize_tickers,
    notification_lines,
    promotable,
    tickers_from_scan,
    update_feed,
)

CFG = load_config(TEMPLATE_PATH)  # window 5, min_hits 3, prune_after 10

# Sessions around a gap: 11-26 is Thanksgiving and the feed didn't run on
# 11-27, so neither date is a session.
DAYS = ["2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-30",
        "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04", "2026-12-07",
        "2026-12-08", "2026-12-09", "2026-12-10"]

WATCHLIST = {"names": [
    {"ticker": "GEV", "status": "active"},
    {"ticker": "CRM", "status": "mechanism_ok_no_current_dislocation"},
    {"ticker": "OLD", "status": "retired"},
]}


def run(days_hits, feed=None):
    """Apply a sequence of (date, hits_by_source) sessions."""
    for day, hits in days_hits:
        feed = update_feed(feed, hits, day, CFG)
    return feed


class UpdateFeedTests(unittest.TestCase):
    def test_init_from_none(self):
        f = update_feed(None, {"T1": ["INTU"]}, DAYS[0], CFG)
        self.assertEqual(f["schema_version"], 1)
        self.assertEqual(f["sessions"], [DAYS[0]])
        self.assertEqual(f["last_updated"], DAYS[0])
        rec = f["tickers"]["INTU"]
        self.assertEqual(rec["first_seen"], DAYS[0])
        self.assertEqual(rec["last_seen"], DAYS[0])
        self.assertEqual(rec["hit_dates"], [DAYS[0]])
        self.assertEqual(rec["hit_sources_by_date"], {DAYS[0]: ["T1"]})
        self.assertEqual(rec["sources"], ["T1"])
        self.assertEqual(f["last_run"], {"date": DAYS[0], "sources_ok": ["T1"],
                                         "sources_failed": {}, "truncated": []})

    def test_does_not_mutate_input(self):
        f = update_feed(None, {"T1": ["INTU"]}, DAYS[0], CFG)
        before = copy.deepcopy(f)
        update_feed(f, {"T1": ["ADBE"]}, DAYS[1], CFG)
        self.assertEqual(f, before)

    def test_same_day_rerun_is_idempotent(self):
        once = update_feed(None, {"T1": ["INTU"], "T2": ["XNDU"]}, DAYS[0], CFG)
        twice = update_feed(once, {"T1": ["INTU"], "T2": ["XNDU"]}, DAYS[0], CFG)
        self.assertEqual(once, twice)
        self.assertEqual(twice["sessions"], [DAYS[0]])
        self.assertEqual(twice["tickers"]["INTU"]["hit_dates"], [DAYS[0]])

    def test_same_day_rerun_replaces_that_days_hits(self):
        f = update_feed(None, {"T1": ["INTU", "ADBE"]}, DAYS[0], CFG)
        f = update_feed(f, {"T1": ["INTU"]}, DAYS[0], CFG)
        self.assertNotIn("ADBE", f["tickers"])  # its only hit was replaced away
        self.assertEqual(f["tickers"]["INTU"]["hit_dates"], [DAYS[0]])

    def test_rerun_with_a_failed_source_keeps_its_earlier_same_day_hits(self):
        f = update_feed(None, {"T1": ["INTU"], "T3": ["CRDO"]}, DAYS[0], CFG)
        f = update_feed(f, {"T1": ["INTU"]}, DAYS[0], CFG, sources_failed={"T3": "timeout"})
        self.assertIn("CRDO", f["tickers"])

    def test_failed_source_leaves_others_intact_and_is_recorded(self):
        f = update_feed(None, {"T1": ["INTU"], "T2": ["XNDU"], "T4": ["BULL"]}, DAYS[0], CFG,
                        sources_failed={"T3": "scan not found"}, truncated=["T4"])
        self.assertEqual(set(f["tickers"]), {"INTU", "XNDU", "BULL"})
        self.assertEqual(f["last_run"]["sources_ok"], ["T1", "T2", "T4"])
        self.assertEqual(f["last_run"]["sources_failed"], {"T3": "scan not found"})
        self.assertEqual(f["last_run"]["truncated"], ["T4"])
        self.assertEqual(f["sessions"], [DAYS[0]])

    def test_all_sources_failed_records_no_session(self):
        f = update_feed(None, {"T1": ["INTU"]}, DAYS[0], CFG)
        f = update_feed(f, {}, DAYS[1], CFG, sources_failed={k: "down" for k in ("T1", "T2", "T3", "T4")})
        self.assertEqual(f["sessions"], [DAYS[0]])
        self.assertEqual(f["last_run"]["date"], DAYS[1])
        self.assertEqual(f["last_run"]["sources_ok"], [])

    def test_empty_scan_still_counts_as_a_session(self):
        # A scan that answered with zero rows is an observation, not a failure.
        f = update_feed(None, {"T1": []}, DAYS[0], CFG)
        self.assertEqual(f["sessions"], [DAYS[0]])
        self.assertEqual(f["tickers"], {})

    def test_ticker_normalization(self):
        f = update_feed(None, {"T1": [" intu ", "INTU", "", "  ", None, "adbe"]}, DAYS[0], CFG)
        self.assertEqual(sorted(f["tickers"]), ["ADBE", "INTU"])
        self.assertEqual(normalize_tickers([" intu ", "Intu", ""]), ["INTU"])

    def test_sources_union_across_days(self):
        f = run([(DAYS[0], {"T2": ["BULL"]}), (DAYS[1], {"T4": ["BULL"]})])
        rec = f["tickers"]["BULL"]
        self.assertEqual(rec["sources"], ["T2", "T4"])
        self.assertEqual(rec["first_seen"], DAYS[0])
        self.assertEqual(rec["last_seen"], DAYS[1])

    def test_pruning_after_prune_after_sessions(self):
        # INTU hits once, then 9 more sessions pass: still inside the last 10.
        seq = [(DAYS[0], {"T1": ["INTU"]})] + [(d, {"T1": ["ADBE"]}) for d in DAYS[1:10]]
        f = run(seq)
        self.assertIn("INTU", f["tickers"])
        # The 11th session pushes its last_seen outside the last 10.
        f = update_feed(f, {"T1": ["ADBE"]}, DAYS[10], CFG)
        self.assertNotIn("INTU", f["tickers"])
        self.assertEqual(len(f["sessions"]), 10)
        self.assertEqual(f["sessions"][-1], DAYS[10])

    def test_hit_dates_trimmed_to_retained_sessions(self):
        f = run([(d, {"T1": ["ADBE"]}) for d in DAYS[:12]])
        rec = f["tickers"]["ADBE"]
        self.assertEqual(rec["hit_dates"], f["sessions"])
        self.assertEqual(set(rec["hit_sources_by_date"]), set(f["sessions"]))
        self.assertEqual(rec["first_seen"], DAYS[0])  # full history kept

    def test_rejects_a_date_before_the_latest_session(self):
        f = update_feed(None, {"T1": ["INTU"]}, DAYS[1], CFG)
        with self.assertRaises(ValueError):
            update_feed(f, {"T1": ["INTU"]}, DAYS[0], CFG)

    def test_rejects_missing_config(self):
        with self.assertRaises(ValueError):
            update_feed(None, {"T1": ["INTU"]}, DAYS[0], {"screener_feed": {"window": 5}})


class PromotableTests(unittest.TestCase):
    def test_three_of_five_promotes_two_of_five_does_not(self):
        seq = [
            (DAYS[0], {"T1": ["INTU", "ADBE"]}),
            (DAYS[1], {"T1": ["INTU"]}),
            (DAYS[2], {"T1": ["INTU", "ADBE"]}),
            (DAYS[3], {"T1": []}),
            (DAYS[4], {"T1": []}),
        ]
        p = promotable(run(seq), WATCHLIST, DAYS[4], CFG)
        self.assertEqual([i["ticker"] for i in p["promotable"]], ["INTU"])
        self.assertEqual(p["promotable"][0]["hits_in_window"], 3)
        self.assertTrue(p["window_full"])

    def test_nothing_promotes_before_the_window_is_full(self):
        f = run([(d, {"T1": ["INTU"]}) for d in DAYS[:4]])
        p = promotable(f, WATCHLIST, DAYS[3], CFG)
        self.assertEqual(p["promotable"], [])
        self.assertFalse(p["window_full"])
        self.assertEqual(p["window_sessions"], 4)

    def test_window_counts_sessions_not_calendar_days(self):
        # DAYS[3]..DAYS[4] spans Thanksgiving: 11-25 -> 11-30 is five calendar
        # days but consecutive sessions. A calendar-day window would lose hits.
        seq = [(DAYS[0], {"T1": []}), (DAYS[1], {"T1": []}), (DAYS[2], {"T1": ["INTU"]}),
               (DAYS[3], {"T1": ["INTU"]}), (DAYS[4], {"T1": ["INTU"]})]
        p = promotable(run(seq), WATCHLIST, DAYS[4], CFG)
        self.assertEqual([i["ticker"] for i in p["promotable"]], ["INTU"])

    def test_hits_outside_the_window_do_not_count(self):
        seq = [(DAYS[0], {"T1": ["INTU"]}), (DAYS[1], {"T1": ["INTU"]})] + \
              [(d, {"T1": ["ADBE"]}) for d in DAYS[2:6]] + [(DAYS[6], {"T1": ["INTU"]})]
        p = promotable(run(seq), WATCHLIST, DAYS[6], CFG)
        self.assertNotIn("INTU", [i["ticker"] for i in p["promotable"]])

    def test_watchlist_exclusion_and_retired_rehit(self):
        seq = [(d, {"T1": ["GEV", "CRM", "OLD", "new"]}) for d in DAYS[:5]]
        p = promotable(run(seq), WATCHLIST, DAYS[4], CFG)
        self.assertEqual([i["ticker"] for i in p["promotable"]], ["NEW"])
        self.assertEqual([i["ticker"] for i in p["retired_rehit"]], ["OLD"])

    def test_multi_source_within_window_only(self):
        # BULL: T2 on the first session only (falls out of the window),
        # T4 on the last five. ARM: T1 and T3 inside the window, only 2 hits.
        seq = [(DAYS[0], {"T2": ["BULL"]})] + \
              [(d, {"T4": ["BULL"]}) for d in DAYS[1:6]]
        seq[4] = (DAYS[4], {"T4": ["BULL"], "T1": ["ARM"]})
        seq[5] = (DAYS[5], {"T4": ["BULL"], "T3": ["ARM"]})
        p = promotable(run(seq), WATCHLIST, DAYS[5], CFG)
        bull = p["promotable"][0]
        self.assertEqual(bull["ticker"], "BULL")
        self.assertEqual(bull["sources"], ["T4"])
        self.assertFalse(bull["multi_source"])
        # ARM is flagged multi-source but not promoted: 2 hits < min_hits.
        self.assertEqual([i["ticker"] for i in p["multi_source"]], ["ARM"])
        self.assertNotIn("ARM", [i["ticker"] for i in p["promotable"]])

    def test_multi_source_excludes_watchlist_names(self):
        seq = [(d, {"T1": ["GEV"], "T3": ["GEV"]}) for d in DAYS[:2]]
        p = promotable(run(seq), WATCHLIST, DAYS[1], CFG)
        self.assertEqual(p["multi_source"], [])

    def test_deterministic_sort_order(self):
        seq = [
            (DAYS[0], {"T1": ["ZZZ", "AAA", "MMM"], "T3": ["MMM"]}),
            (DAYS[1], {"T1": ["ZZZ", "AAA", "MMM", "BBB"]}),
            (DAYS[2], {"T1": ["ZZZ", "AAA", "MMM", "BBB"]}),
            (DAYS[3], {"T1": ["ZZZ", "BBB"]}),
            (DAYS[4], {"T1": []}),
        ]
        p = promotable(run(seq), WATCHLIST, DAYS[4], CFG)
        # ZZZ 4 hits; then the 3-hit names: MMM first (multi-source), AAA, BBB.
        self.assertEqual([i["ticker"] for i in p["promotable"]], ["ZZZ", "MMM", "AAA", "BBB"])

    def test_future_sessions_ignored(self):
        f = run([(d, {"T1": ["INTU"]}) for d in DAYS[:6]])
        p = promotable(f, WATCHLIST, DAYS[3], CFG)
        self.assertFalse(p["window_full"])
        self.assertEqual(p["last_session"], DAYS[3])


class ScanParsingTests(unittest.TestCase):
    def test_extracts_tickers_only(self):
        resp = {"data": {"result": {"total_items": 3, "results": [
            {"ticker": "abnb", "instrument_id": "x", "cells": ["1.2"]},
            {"ticker": ""},
            {"ticker": "CHTR"},
        ]}}}
        self.assertEqual(tickers_from_scan(resp), (["ABNB", "CHTR"], False))

    def test_truncated_when_total_exceeds_rows(self):
        resp = {"data": {"result": {"total_items": 40, "results": [{"ticker": "A"}]}}}
        self.assertEqual(tickers_from_scan(resp), (["A"], True))

    def test_malformed_response_raises(self):
        with self.assertRaises(ValueError):
            tickers_from_scan({"error": "scan not found"})


class NotificationTests(unittest.TestCase):
    def test_summary_line_matches_spec_shape(self):
        hits = {"T1": ["A", "B"], "T2": ["C"], "T3": ["D"], "T4": ["BULL"]}
        promo = {"promotable": [{"ticker": "INTU", "hits_in_window": 4, "sources": ["T1"],
                                 "multi_source": False}],
                 "retired_rehit": [],
                 "multi_source": [{"ticker": "BULL", "hits_in_window": 2, "sources": ["T2", "T4"],
                                   "multi_source": True}],
                 "window_full": True, "window_sessions": 5}
        self.assertEqual(
            notification_lines(hits, promo, source_order=["T1", "T2", "T3", "T4"]),
            ["Screener feed: 5 hits (T1 2 / T2 1 / T3 1 / T4 1) | promotable: INTU | multi-source: BULL"],
        )

    def test_warning_line_for_failed_and_truncated(self):
        promo = {"promotable": [], "retired_rehit": [], "multi_source": [],
                 "window_full": False, "window_sessions": 2}
        lines = notification_lines({"T1": ["A"], "T2": [], "T4": ["B"]}, promo,
                                   sources_failed={"T3": "scan not found"}, truncated=["T4"],
                                   source_order=["T1", "T2", "T3", "T4"])
        self.assertEqual(lines, [
            "Screener feed: 2 hits (T1 1 / T2 0 / T3 failed / T4 1) | promotable: none yet (sessions recorded: 2)",
            "Screener feed warning: T3 failed (scan not found) | T4 truncated",
        ])


if __name__ == "__main__":
    unittest.main()
