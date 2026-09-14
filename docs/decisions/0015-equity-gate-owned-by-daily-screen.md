# ADR 0015: `daily-screen` owns the equity-deleveraging gate; macro state gets a staleness ceiling

**Status:** accepted (2026-09-14) · **Amends:** [ADR 0014](0014-macro-fetch-desktop-only.md),
[ADR 0012](0012-breadth-escalation-and-fail-closed.md)

## Context

ADR 0014 moved every §6 macro fetch into a desktop-only `macro-refresh` skill, because FRED,
Alpha Vantage and multpl.com are egress-blocked from cloud routines. That was correct for the
*sources*, but it silently attached two unrelated problems to the same weekly, human-dependent
cadence.

**Problem 1 — the fastest-moving gate inherited the slowest cadence.** §6.1's three hard gates
have very different input dynamics. `credit_stress` (HY OAS) and `inflation_duration_shock`
(real/nominal yields, 5y5y breakevens) drift slowly; a weekly read is honest. But
`equity_deleveraging` keys off VIX and the S&P's distance from its 200-day mean — both of which
can move decisively in a single session. Reading a week-old VIX to decide whether a
deleveraging event is underway defeats the gate's purpose.

**Problem 2 — the release streak was being stepped on the wrong clock.**
`engine.macro.step_hard_gate` advances `consecutive_release_days` by one per *call*.
`state/config.yaml` sets `release_consecutive_closes: 5` for all three gates — the name says
*closes*, meaning trading-day closes. But the only caller was `macro-refresh`, running weekly.
An active gate would therefore have taken **five weeks to release, not five sessions** — a 5-7x
error that had never surfaced only because no gate has ever been active. It would have surfaced
for the first time during a real stress event, holding the book flat for over a month after
conditions normalized.

**Problem 3 — `daily-screen` had no staleness ceiling on macro state.** It hard-gates on Stage A
freshness (`last_stage_a_review` ≤7 days, §0.2) but had no equivalent check on
`macro-latest.json`. Between 2026-09-08 and 2026-09-10 it screened three sessions against a
macro read that reached 8 days old. The runs flagged it in free text on their own initiative,
but nothing in the skill required it and no threshold existed. On 2026-09-14 the scheduled
desktop refresh *started* on time (Sunday 09:44 ET) but its session was suspended when the app
closed and did not commit until Monday 11:08 ET — 41 minutes after that morning's screen had
already scored all 15 names against a 5-day-old threshold.

Because `restricted_regime.score_threshold` is the binding constraint on nearly every near-miss
this project has recorded (80 under RESTRICTED vs 75 under NORMAL), a stale macro read does not
fail loudly — it quietly moves every verdict.

## Decision

**1. `daily-screen` owns `hard_gates.equity_deleveraging`.** It computes that gate fresh every
session from live VIX and SPX via Robinhood's `get_indexes` / `get_index_quotes` /
`get_index_historicals` — confirmed reachable from the cloud sandbox, unlike FRED — steps it with
`engine.macro.step_hard_gate`, and writes back that key only. `macro-refresh` must no longer
compute or step it; two writers would double-advance the release streak.

This makes `state/macro-latest.json` a split-ownership file, the same pattern already proven on
`state/watchlist.json` (`macro-refresh` owns `ntm`, `weekly-review` owns everything else). The
invariant is the same: writers touch disjoint keys, so concurrent pushes merge cleanly.

Ownership after this ADR:

| Key | Owner | Cadence |
|---|---|---|
| `restricted_regime.*` | `macro-refresh` | weekly (desktop) |
| `hard_gates.credit_stress` | `macro-refresh` | weekly (desktop) |
| `hard_gates.inflation_duration_shock` | `macro-refresh` | weekly (desktop) |
| `hard_gates.equity_deleveraging` | **`daily-screen`** | every session (cloud) |
| `breadth` | unassigned — see below | never yet run |
| `watchlist.json` → `ntm` | `macro-refresh` | weekly (desktop) |
| `watchlist.json` → all else | `weekly-review` | weekly (cloud) |

**2. `daily-screen` gets a three-band staleness rule on `macro-latest.json.as_of`**, symmetric
with §0.2's existing Stage A clock: ≤7 days use as-is; 8-14 days proceed but record a structured
`macro.staleness_flag` *and* lead the run's Slack notification with the warning; >14 days stop
with `NO TRADE — DATA INSUFFICIENT`. Past two weeks a regime read is no longer evidence about
today, and scoring against an unverified threshold is worse than not scoring.

**3. `macro-refresh` runs after `weekly-review`, not before.** The prior guidance ("ideally right
before this skill") targeted the wrong consumer: `weekly-review`'s use of macro/NTM state is
purely informational — every decision it makes is company-specific. The routine that needs fresh
state is `daily-screen`. And `weekly-review` can *admit* names, which carry no `ntm` at all until
the next refresh, so refreshing afterward closes that gap in the same cycle. The desktop task now
runs Sunday evening: after Sunday's review, ~16 hours before Monday's first screen — enough
buffer that even a multi-hour suspended session still lands in time.

## Consequences

- The gate most sensitive to same-day conditions is now computed same-day, from live data, with
  no dependency on a human being at their laptop.
- The release-streak cadence bug is fixed for `equity_deleveraging`. It **remains open** for
  `credit_stress` and `inflation_duration_shock`, which are still stepped weekly by
  `macro-refresh` — acceptable for now because their inputs genuinely move slowly, but the
  `release_consecutive_closes: 5` config value means something different for them than its name
  implies. Either rename the key per-gate or teach `macro-refresh` to step by elapsed trading
  days; deliberately deferred, not overlooked.
- `breadth` still has no owner and has never been populated. Under ADR 0012's fail-closed rule,
  if VIX and SPX ever both fire, `equity_deleveraging_trigger` returns `True` on missing breadth
  — so the first genuine stress event auto-halts new entries regardless of actual market breadth.
  That is the conservative direction and is intentional, but it is an unexercised path. See the
  open item in `docs/v7-migration-plan.md`.
- Staleness is now visible where a human actually looks (Slack), not only in a JSON field nobody
  reads on a green day.
