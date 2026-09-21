# ADR 0019: `engine.sources` sends no custom User-Agent (SEC EDGAR excepted) — FRED started rejecting the old one

**Status:** accepted (2026-09-21) · **Related:** [ADR 0011](0011-https-over-mcp-and-macro-sources.md),
[ADR 0014](0014-macro-fetch-desktop-only.md)

## Context

`engine.sources._get` has sent every request — FRED, multpl.com, Alpha Vantage, SEC EDGAR alike
— the same custom header since ADR 0011: `User-Agent: leaps-hunter/1.0 (research; contact via
repo owner)`.

The 2026-09-21 weekly macro-refresh (desktop, normal internet access — see ADR 0014 on why this
can't run from a cloud routine) found `fetch_fred_series` raising `TimeoutError` on every
attempt against `https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd=1900-01-01`.
Isolating it: `curl -A "leaps-hunter/1.0 (research; contact via repo owner)"` against that exact
URL reproducibly fails (exit 92 / read timeout — the connection drops or hangs), while the
identical request with curl's own default UA, or urllib's default UA, returns `200` in well
under a second. Nothing else about the request differs. The run was completed by patching
`sources._UA = {}` at runtime for that session.

multpl.com and Alpha Vantage were not observed failing with the old custom UA — only FRED was.
But a single `_UA` constant fed all four sources, so any fix touches all of them; there's no
recorded evidence any of the other three *need* a custom UA either, so there's no reason to keep
sending one to them just because FRED tolerated it up to now.

SEC EDGAR is different in kind, not just observation: its own developer-facing access policy
(https://www.sec.gov/os/webmaster-faq#developers) states a descriptive UA identifying the
requester is required, and requests without one are liable to be blocked — this is documented
behavior, not something inferred from one bad run.

This session could not re-run `fetch_fred_series`/`fetch_cape_series` against the live hosts to
confirm the fix end-to-end: it runs in a cloud sandbox, and per ADR 0014 that sandbox's egress
policy denies `fred.stlouisfed.org`, `www.multpl.com`, `www.alphavantage.co`, and
`data.sec.gov` outright (`403` on the CONNECT tunnel, confirmed again here) — a blanket network
policy unrelated to request headers. The fix below is verified by the curl isolation above and
by fixture-backed unit tests; live confirmation needs the next desktop `macro-refresh` run.

## Decision

`_get` sends **no custom `User-Agent`** by default — nothing that impersonates a browser, just
urllib's own identifying default string. This applies to FRED, multpl.com, and Alpha Vantage.

SEC EDGAR (`fetch_sec_company_concept`) keeps sending the identifying UA
(`leaps-hunter/1.0 (research; contact via repo owner)`) explicitly, since SEC's own policy asks
for one.

`_get` also gained a bounded retry: one retry after a 2s delay on `TimeoutError` or
`urllib.error.URLError`, and the per-attempt timeout dropped from 30s to 15s (so a genuinely
hung connection like the one observed here fails and retries well inside a minute instead of
burning up to 60s before the caller even sees the first error).

## Rationale

- Matching curl's own default behavior (no `-A` at all) is the most literal read of "the
  identical request with a default UA works" — not substituting a browser-like string, which
  would be a form of the impersonation this project has deliberately avoided since ADR 0011.
- Consolidating FRED/multpl/Alpha Vantage on one no-custom-UA default (rather than special-casing
  FRED alone) keeps `_get` simple and doesn't require guessing which of the other two might be
  next to start minding the string — there's no evidence either needs it, keyed or not.
- SEC is kept as a named exception with its own constant (`_SEC_UA`) rather than folded into the
  default, because its requirement is policy, not a workaround for an observed failure, and
  removing it would risk trading one host's breakage for another's.
- A runtime monkeypatch (`sources._UA = {}`) is not a fix, just how the blocked run was
  unblocked in the moment; baking the same behavior into the module means the next scheduled
  `macro-refresh` doesn't need the same manual intervention.

## Consequences

- `engine.sources._get(url, headers=...)` now takes an optional `headers` argument; every
  call site but `fetch_sec_company_concept` keeps the default.
- If FRED (or any of the other three) starts requiring a UA in the future, that's a new,
  opposite-direction §21 event, not a reversion of this one.
- This ADR's fix is unverified against the live network from this session — see Context. The
  next desktop `macro-refresh` run is the actual confirmation; if `fetch_fred_series` still
  times out there, this ADR's diagnosis is wrong and needs revisiting, not just retried harder.
