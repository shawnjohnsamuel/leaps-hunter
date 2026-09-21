"""Sources' pure parsing/computation functions, tested against fixtures
captured from real responses — never against the live network (Alpha
Vantage in particular throttled after two rapid requests on 2026-09-03)."""
import io
import json
import unittest
from datetime import date
from unittest import mock

from engine.config import TEMPLATE_PATH, load_config
from engine.macro import stale_sources
from engine.sources import (
    _parse_fred_csv,
    _parse_multpl_cape,
    compute_ntm_eps_revision,
    fetch_av_earnings_estimates,
    fetch_fred_series,
    fetch_sec_company_concept,
    parse_robinhood_daily_closes,
)

FRED_FIXTURE = (
    "observation_date,BAMLH0A0HYM2\n"
    "2026-08-31,2.65\n"
    "2026-09-01,.\n"
    "2026-09-02,2.66\n"
)

# multpl.com's own shape, kept verbatim so the parser is tested against what
# the site actually serves: display dates, newest first, months not contiguous.
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
    def test_dates_are_iso_and_rows_are_oldest_first(self):
        # multpl serves "Sep 2, 2026" newest first; the parser normalises both
        # so a CAPE series is shaped exactly like a FRED one and `[-1]` is the
        # latest observation in either.
        rows = _parse_multpl_cape(MULTPL_FIXTURE)
        self.assertEqual(
            rows, [("2026-06-01", 40.50), ("2026-07-01", 40.73), ("2026-09-02", 41.93)]
        )

    def test_non_date_cells_are_skipped_not_emitted(self):
        html = (
            "<html><body><table>"
            "<tr><td>Shiller PE</td><td>Value</td>"
            "<td>Sep 2, 2026</td><td>41.93</td></tr>"
            "</table></body></html>"
        )
        self.assertEqual(_parse_multpl_cape(html), [("2026-09-02", 41.93)])

    def test_latest_date_feeds_stale_sources_without_conversion(self):
        # The point of the ISO change (ADR 0018): the CAPE row goes straight
        # into stale_sources alongside the FRED ids. Converting it ad hoc in a
        # scratch script, as the 2026-09-21 refresh had to, is the failure mode
        # this pins shut.
        cape = _parse_multpl_cape(MULTPL_FIXTURE)
        fred = _parse_fred_csv(FRED_FIXTURE)
        latest_by_series = {"CAPE": cape[-1][0], "BAMLH0A0HYM2": fred[-1][0]}
        self.assertEqual(latest_by_series, {"CAPE": "2026-09-02", "BAMLH0A0HYM2": "2026-09-02"})

        cfg = load_config(TEMPLATE_PATH)
        self.assertTrue(stale_sources(latest_by_series, "2026-09-08", cfg).ok)
        # 18 days on, each judged on its own cadence: past the daily series'
        # 6-day limit, still well inside CAPE's monthly 45.
        r = stale_sources(latest_by_series, "2026-09-20", cfg)
        self.assertEqual([s for s, _, _ in r.stale], ["BAMLH0A0HYM2"])
        self.assertEqual(r.unconfigured, [])


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


class RobinhoodDailyClosesTests(unittest.TestCase):
    PAYLOAD = {"data": {"results": [
        {"symbol": "AAA", "bars": [
            {"begins_at": "2026-09-11T00:00:00Z", "close_price": "12.00"},
            {"begins_at": "2026-09-09T00:00:00Z", "close_price": "10.00"},
            {"begins_at": "2026-09-10T00:00:00Z", "close_price": "10.00", "interpolated": True},
        ]},
        {"symbol": "EMPTY", "bars": []},
    ]}}

    def test_drops_interpolated_and_sorts_oldest_first(self):
        out = parse_robinhood_daily_closes(self.PAYLOAD)
        self.assertEqual(out["AAA"], [("2026-09-09", 10.0), ("2026-09-11", 12.0)])

    def test_symbol_without_bars_is_absent_not_empty(self):
        self.assertNotIn("EMPTY", parse_robinhood_daily_closes(self.PAYLOAD))

    def test_malformed_payload_yields_nothing(self):
        self.assertEqual(parse_robinhood_daily_closes({}), {})


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RequestHeaderTests(unittest.TestCase):
    """Headers are per source. FRED began dropping connections that carry the
    custom User-Agent on 2026-09-21; SEC EDGAR rejects requests without one."""

    def _capture(self, body: bytes, call):
        sent = []

        def fake_urlopen(req, timeout):
            sent.append(req)
            return _FakeResponse(body)

        with mock.patch("engine.sources.urllib.request.urlopen", fake_urlopen):
            call()
        return sent[0]

    def test_fred_sends_no_custom_user_agent(self):
        req = self._capture(FRED_FIXTURE.encode(), lambda: fetch_fred_series("BAMLH0A0HYM2"))
        self.assertIsNone(req.get_header("User-agent"))

    def test_av_rate_limit_notice_never_carries_the_key(self):
        notice = b'{"Information": "We have detected your API key as TESTKEY123 and our standard API rate limit is 25 requests per day."}'
        sent = []

        def fake_urlopen(req, timeout):
            sent.append(req)
            return _FakeResponse(notice)

        with mock.patch("engine.sources.urllib.request.urlopen", fake_urlopen):
            payload = fetch_av_earnings_estimates("CRM", "TESTKEY123")
        self.assertNotIn("TESTKEY123", json.dumps(payload))
        self.assertIn("[redacted]", payload["Information"])
        self.assertFalse(compute_ntm_eps_revision(payload, date(2026, 9, 21)).available)

    def test_sec_keeps_its_descriptive_user_agent(self):
        req = self._capture(b"{}", lambda: fetch_sec_company_concept("0001108524", "us-gaap", "Revenues"))
        self.assertIn("leaps-hunter", req.get_header("User-agent"))


if __name__ == "__main__":
    unittest.main()
