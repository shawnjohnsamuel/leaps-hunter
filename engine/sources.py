"""HTTP data sources for the v7 engine (ADR 0011): prefer a keyless or keyed
HTTPS endpoint over an MCP connector for anything on the daily path.
Robinhood is the one exception — its live chain, NAV and positions have no
HTTP equivalent, so those enter the engine as arguments from the calling
skill, which reaches Robinhood over MCP. This module never talks to
Robinhood.

Each source splits a thin `fetch_*` (network I/O) from a pure `_parse_*` or
`compute_*` function, so tests exercise the parsing/computation logic
against recorded fixtures without touching the network — Alpha Vantage in
particular rate-limits aggressively (throttled after two rapid requests,
observed 2026-09-03).
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from html import unescape

_UA = {"User-Agent": "leaps-hunter/1.0 (research; contact via repo owner)"}
_TIMEOUT = 30


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- FRED -----

def _parse_fred_csv(text: str) -> list[tuple[str, float]]:
    rows = list(csv.reader(io.StringIO(text)))[1:]
    return [(r[0], float(r[1])) for r in rows if len(r) > 1 and r[1] not in (".", "")]


def fetch_fred_series(series_id: str) -> list[tuple[str, float]]:
    """(date, value) pairs, oldest first, keyless. ADR 0011: BAMLH0A0HYM2
    for §6.1's absolute credit gate; BAA10Y for §6.2's percentile — FRED
    caps ICE BofA series at ~3 years regardless of an API key (confirmed
    2026-09-03: the keyed JSON endpoint returns the same 795 observations
    as this anonymous CSV)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd=1900-01-01"
    return _parse_fred_csv(_get(url))


# -------------------------------------------------------- Shiller CAPE -----

def _parse_multpl_cape(html: str) -> list[tuple[str, float]]:
    m = re.search(r"<table.*?</table>", html, re.S)
    if not m:
        return []
    cells = [
        unescape(re.sub(r"<[^>]+>", "", c)).strip()
        for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(0), re.S)
    ]
    pairs = [
        (cells[i], cells[i + 1])
        for i in range(0, len(cells) - 1, 2)
        if re.match(r"^[A-Z][a-z]{2} \d", cells[i])
    ]
    out = []
    for d, v in pairs:
        num = re.sub(r"[^\d.]", "", v)
        if num:
            out.append((d, float(num)))
    return out


def fetch_cape_series() -> list[tuple[str, float]]:
    """(date, CAPE) pairs, newest first — multpl.com's own order, Shiller
    series back to 1871. Feeds §6.2's cape_gt_95pct percentile component."""
    return _parse_multpl_cape(_get("https://www.multpl.com/shiller-pe/table/by-month"))


# ----------------------------------------------------- Alpha Vantage -----

@dataclass(frozen=True)
class NTMResult:
    """§10's 60-day NTM EPS revision, or a stated reason it is unavailable.
    §3: an unobtainable required metric disqualifies the pattern — it is
    never scored as a fail. Callers must check `available` before reading
    `revision_pct`.
    """

    available: bool
    revision_pct: float | None = None
    ntm_eps_now: float | None = None
    ntm_eps_60d_ago: float | None = None
    analyst_count: int | None = None
    reason: str | None = None


def fetch_av_earnings_estimates(symbol: str, api_key: str) -> dict:
    url = (
        "https://www.alphavantage.co/query?function=EARNINGS_ESTIMATES"
        f"&symbol={symbol}&apikey={api_key}"
    )
    return json.loads(_get(url))


def compute_ntm_eps_revision(payload: dict, as_of: date) -> NTMResult:
    """Blend the next two forward fiscal years, weighted by how much of FY1
    remains, into a next-twelve-months figure comparable across tickers with
    different fiscal year ends.

    Corrected 2026-09-03: an earlier version summed "the next four fiscal
    quarter records". That silently summed HISTORICAL quarters (the
    `estimates` array is not pre-filtered to the future — sorting ascending
    and taking the first four pulled 2017 data), and failed outright on
    names that expose fewer than four forward quarters, CRM included.
    Fiscal-year records are dense and both carry `_60_days_ago`, so the
    blend uses those instead of raw quarters.
    """
    estimates = payload.get("estimates")
    if not estimates:
        return NTMResult(
            available=False,
            reason="no estimates in response (rate-limited or unknown symbol)",
        )

    def _num(e, k):
        v = e.get(k)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    fy = sorted(
        (
            e
            for e in estimates
            if e.get("horizon") == "fiscal year" and date.fromisoformat(e["date"]) > as_of
        ),
        key=lambda e: e["date"],
    )
    if len(fy) < 2:
        return NTMResult(
            available=False,
            reason=f"only {len(fy)} forward fiscal year(s) available, need 2",
        )

    fy1, fy2 = fy[0], fy[1]
    cur1, cur2 = _num(fy1, "eps_estimate_average"), _num(fy2, "eps_estimate_average")
    ago1 = _num(fy1, "eps_estimate_average_60_days_ago")
    ago2 = _num(fy2, "eps_estimate_average_60_days_ago")
    if None in (cur1, cur2, ago1, ago2):
        return NTMResult(available=False, reason="null EPS estimate on one side of the FY1/FY2 blend")

    days_to_fy1_end = (date.fromisoformat(fy1["date"]) - as_of).days
    w = max(0.0, min(1.0, days_to_fy1_end / 365.0))
    ntm_now = w * cur1 + (1 - w) * cur2
    ntm_ago = w * ago1 + (1 - w) * ago2
    if not ntm_ago:
        return NTMResult(available=False, reason="60-days-ago NTM baseline is zero")

    revision_pct = (ntm_now / ntm_ago - 1.0) * 100.0
    analyst_count = _num(fy1, "eps_estimate_analyst_count")
    return NTMResult(
        available=True,
        revision_pct=revision_pct,
        ntm_eps_now=ntm_now,
        ntm_eps_60d_ago=ntm_ago,
        analyst_count=int(analyst_count) if analyst_count is not None else None,
    )


# --------------------------------------------------------- SEC EDGAR -----

def fetch_sec_company_concept(cik10: str, taxonomy: str, tag: str) -> dict:
    """cik10 is the zero-padded 10-digit CIK, e.g. '0001108524' for CRM.
    SEC requires a descriptive User-Agent identifying the requester; feeds
    §8's retention/RPO checks and §11's fundamentals once §8 is built."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json"
    return json.loads(_get(url))
