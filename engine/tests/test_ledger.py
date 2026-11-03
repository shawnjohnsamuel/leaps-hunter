"""engine.ledger — the §17 paper ledger's episode, mark and close lifecycle."""
import unittest

from engine.config import TEMPLATE_PATH, load_config
from engine.ledger import close, closed_count, due_to_close, is_calibrated, mark, open_entry, reconfirm

CFG = load_config(TEMPLATE_PATH)


def _entry(ticker="MU", day="2026-11-02", **kw):
    e = {"date": day, "ticker": ticker, "mechanism": "M1", "structure_type": "single_itm_or_spread",
         "executable_entry_p0": 378.35, "realized_outcome": None}
    e.update(kw)
    return e


class LedgerTests(unittest.TestCase):
    def test_a_second_clear_reconfirms_the_open_episode(self):
        entries = [_entry()]
        e = open_entry(entries, "MU")
        self.assertIs(e, entries[0])
        reconfirm(e, "2026-11-03", 81)
        self.assertEqual(entries[0]["reconfirmed"], [{"date": "2026-11-03", "s11_total": 81}])
        self.assertIsNone(open_entry(entries, "SNOW"))

    def test_pre_adr_duplicates_are_ignored(self):
        entries = [_entry(), _entry(day="2026-11-03", duplicate_of="2026-11-02")]
        self.assertIs(open_entry(entries, "MU"), entries[0])

    def test_mark_records_return_and_missing_quotes(self):
        e = mark(_entry(), "2026-11-09", 400.0)
        self.assertAlmostEqual(e["marks"][0]["return_pct"], 5.72, places=2)
        mark(e, "2026-11-16", None, note="no quote")
        self.assertNotIn("return_pct", e["marks"][1])

    def test_mark_tracks_the_share_fallback_too(self):
        e = mark(_entry(share_fallback={"spot": 833.59}), "2026-11-09", 400.0, share_price=870.0)
        self.assertAlmostEqual(e["marks"][0]["share_return_pct"], 4.37, places=2)

    def test_close_uses_the_latest_priced_mark(self):
        e = _entry()
        mark(e, "2026-11-09", 400.0)
        mark(e, "2026-11-16", None)
        close(e, "2027-05-01", "horizon")
        self.assertEqual(e["realized_outcome"]["exit_bid"], 400.0)
        self.assertIsNone(open_entry([e], "MU"))

    def test_close_refuses_without_a_priced_mark(self):
        with self.assertRaises(ValueError):
            close(_entry(), "2027-05-01", "horizon")

    def test_horizon(self):
        self.assertFalse(due_to_close(_entry(), "2027-04-30", CFG))
        self.assertTrue(due_to_close(_entry(), "2027-05-01", CFG))

    def test_only_closed_entries_count_toward_calibration(self):
        open_one = _entry()
        done = mark(_entry(ticker="GEV"), "2026-12-01", 10.0)
        close(done, "2027-05-01", "horizon")
        dup = _entry(ticker="GEV", duplicate_of="x", realized_outcome={"return_pct": 1})
        entries = [open_one, done, dup]
        self.assertEqual(closed_count(entries, "M1", "single_itm_or_spread"), 1)
        self.assertFalse(is_calibrated(entries, "M1", "single_itm_or_spread", CFG))


if __name__ == "__main__":
    unittest.main()
