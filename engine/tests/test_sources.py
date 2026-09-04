"""Sources' pure parsing/computation functions, tested against fixtures
captured from real responses — never against the live network (Alpha
Vantage in particular throttled after two rapid requests on 2026-09-03)."""
import unittest
from datetime import date

from engine.sources import _parse_fred_csv, _parse_multpl_cape, compute_ntm_eps_revision

FRED_FIXTURE = (
    "observation_date,BAMLH0A0HYM2\n"
    "2026-08-31,2.65\n"
    "2026-09-01,.\n"
    "2026-09-02,2.66\n"
)

MULTPL_FIXTURE = (
    "<html><body><table id='datatable'>"
    "<tr><td>Sep 2, 2026</td><td>41.93</td>"
    "<td>Jul 1, 2026</td><td>40.73</td>"
    "<td>Jun 1, 2026</td><td>40.50</td></tr>"
    "</table></body></html>"
)

# Real CRM payload shape captured 2026-09-03, trimmed to the fields the blend
# needs. The FY1/FY2 EPS values are the actual figures returned that day.
AV_CRM_FIXTURE = {
    "symbol": "CRM",
    "estimates": [
        {
            "date": "2017-04-30",
            "horizon": "fiscal quarter",
            "eps_estimate_average": "0.90",
            "eps_estimate_average_60_days_ago": "0.88",
        },
        {
            "date": "2027-01-31",
            "horizon": "fiscal year",
            "eps_estimate_average": "14.6707",
            "eps_estimate_average_60_days_ago": "14.1275",
            "eps_estimate_analyst_count": "25",
        },
        {
            "date": "2028-01-31",
            "horizon": "fiscal year",
            "eps_estimate_average": "15.5560",
            "eps_estimate_average_60_days_ago": "15.5139",
            "eps_estimate_analyst_count": "52",
        },
    ],
}

AV_THROTTLED_FIXTURE = {
    "Information": "Thank you for using Alpha Vantage! Please consider spreading "
    "out your free API requests more sparingly (1 request per second)."
}

AV_ONE_FORWARD_YEAR_FIXTURE = {
    "estimates": [
        {
            "date": "2027-01-31",
            "horizon": "fiscal year",
            "eps_estimate_average": "14.67",
            "eps_estimate_average_60_days_ago": "14.13",
        },
    ]
}

AS_OF = date(2026, 9, 3)


class FredParsingTests(unittest.TestCase):
    def test_skips_missing_value_marker(self):
        rows = _parse_fred_csv(FRED_FIXTURE)
        self.assertEqual(rows, [("2026-08-31", 2.65), ("2026-09-02", 2.66)])


class MultplCapeParsingTests(unittest.TestCase):
    def test_extracts_date_value_pairs(self):
        rows = _parse_multpl_cape(MULTPL_FIXTURE)
        self.assertEqual(
            rows, [("Sep 2, 2026", 41.93), ("Jul 1, 2026", 40.73), ("Jun 1, 2026", 40.50)]
        )


class NtmEpsRevisionTests(unittest.TestCase):
    def test_fy1_fy2_blend_matches_verified_run(self):
        # Regression fixture: this exact blend was computed and hand-verified
        # against the live Alpha Vantage response on 2026-09-03.
        r = compute_ntm_eps_revision(AV_CRM_FIXTURE, AS_OF)
        self.assertTrue(r.available)
        self.assertAlmostEqual(r.ntm_eps_now, 15.1922, places=3)
        self.assertAlmostEqual(r.ntm_eps_60d_ago, 14.9441, places=3)
        self.assertAlmostEqual(r.revision_pct, 1.66, places=1)
        self.assertEqual(r.analyst_count, 25)
        # Below both §10 thresholds today.
        self.assertLess(r.revision_pct, 5.0)
        self.assertLess(r.revision_pct, 10.0)

    def test_historical_quarters_are_excluded_not_summed(self):
        # The bug this fixture regression-tests: an earlier version summed
        # "the next four fiscal quarter records" without filtering to the
        # future first, and silently included the 2017 quarter above.
        r = compute_ntm_eps_revision(AV_CRM_FIXTURE, AS_OF)
        self.assertNotAlmostEqual(r.ntm_eps_now, 0.90, places=2)

    def test_throttled_response_is_unavailable_not_a_failed_score(self):
        r = compute_ntm_eps_revision(AV_THROTTLED_FIXTURE, AS_OF)
        self.assertFalse(r.available)
        self.assertIsNone(r.revision_pct)
        self.assertIn("no estimates", r.reason)

    def test_fewer_than_two_forward_years_is_unavailable(self):
        r = compute_ntm_eps_revision(AV_ONE_FORWARD_YEAR_FIXTURE, AS_OF)
        self.assertFalse(r.available)
        self.assertIn("1 forward fiscal year", r.reason)


if __name__ == "__main__":
    unittest.main()
