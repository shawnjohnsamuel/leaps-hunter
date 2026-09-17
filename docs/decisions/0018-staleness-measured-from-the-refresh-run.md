# ADR 0018: Macro staleness is measured from the refresh run, not the data's `as_of`

**Status:** accepted (2026-09-17) · **Amends:** [ADR 0015](0015-equity-gate-owned-by-daily-screen.md)

## Context

ADR 0015 gave `daily-screen` a staleness ceiling on macro state: use it under 7 days, flag it
loudly at 8–14, stop past 14. It measured all three bands against `macro-latest.json`'s `as_of`.

`macro-refresh` sets `as_of` to the newest data date **common to every series it fetched**. One of
those series is WALCL, the Fed balance sheet, which publishes weekly: observations are dated
Wednesday and released Thursday afternoon. So a Sunday-evening refresh writes an `as_of` that is
already 4–6 days old, and it stays pinned there all week until the next Wednesday print.

The two clocks were therefore never the same thing:

- **"Has anyone refreshed recently?"** — what the bands are actually for.
- **"How old is the slowest series in the file?"** — what `as_of` measures, and it is bounded
  below by WALCL's weekly cadence no matter how recently the refresh ran.

This fired on **2026-09-17**. `macro-refresh` had run on 09-14, three days earlier. The screen
recorded `staleness_flag: "as_of=2026-09-09 is 8 calendar days old"` and led its Slack message with
`MACRO STATE STALE`. It would have repeated every Thursday and Friday, which is exactly the
alert-fatigue pattern the loud flag exists to avoid — and it also pulled the 14-day hard stop about
four days earlier than intended, since a missed Sunday would reach 15 days from `as_of` while the
last real refresh was only 11 days old.

Replacing the basis raises the obvious counter-risk: a run date says nothing about whether FRED
stopped publishing a series. A recent refresh over frozen data would look perfectly healthy.

## Decision

**1. The bands measure from `last_refreshed`.** `macro-refresh` writes it on every run that
completes step 1, including runs where nothing moved, and `engine.macro.macro_staleness` returns
the day count plus a `current` / `flag` / `stop` band. Thresholds live in config
(`macro_staleness.flag_after_days: 7`, `stop_after_days: 14`), per ADR 0010. `as_of` stays in the
file as data provenance and is explicitly not the staleness basis; `macro-latest.json` carries a
`date_semantics` note saying so, because the two dates sitting side by side is what invited the
mistake.

If `last_refreshed` is missing — a file written before this ADR — `daily-screen` falls back to
`as_of` and says so in the notification. The fallback reads pessimistic, which is the safe
direction.

**2. Source freshness is a separate, per-series check.** `engine.macro.stale_sources` compares each
fetched series' newest observation against its own cadence, from config
(`max_source_lag_days: daily 6, weekly 12, monthly 45`, with a `source_cadence` map naming each
FRED id and `CAPE`). `macro-refresh` runs it every time and records the result. A series past its
limit is reported prominently rather than written into a clean-looking file, and a series with no
cadence entry is reported as `unconfigured` rather than silently passed.

That split is the point: a fresh run date answers "did the job run", and the per-source check
answers "did the data actually move". Neither alone is sufficient.

## Consequences

- The weekly Thursday/Friday false alarm is gone. Today's state (refreshed 09-14, checked 09-17)
  reads **3 days, `current`**, where the old basis read 8 days and flagged.
- The hard stop now triggers 14 days after the last actual refresh, which is what ADR 0015 meant.
- A frozen upstream series is caught by name and cadence instead of hiding behind a recent run.
- `config.example.yaml` now differs from §20 in three places (this, ADR 0016's
  `breadth_min_coverage`, ADR 0017's `tripwires`), all pinned in `test_config.py`. `v7.md` stays
  verbatim.
- The first `macro-refresh` after this ADR must write `last_refreshed`. It was backfilled by hand
  to 2026-09-14, the last real refresh, so `daily-screen` reads the correct band immediately rather
  than waiting a cycle on the fallback.
