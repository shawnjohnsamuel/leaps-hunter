# Storage schema — framework v7.0

**Adopted:** 2026-09-03 · Supersedes [`storage-schema.md`](storage-schema.md) (v6.1)

v7 has no regime verdict, no thesis object, no repeat-candidate guard. Its state is the
mechanism taxonomy, the macro hard-gate/throttle state, and the calibration ledger. All of it
lives in the **private** data repo (`leaps-hunter-data`, ADR 0002), under `state/` — never in
this (public) repo, and NAV is never written to disk in either repo (ADR 0013).

```
state/config.yaml          the single threshold source (§20), plus portfolio.account_ref
state/watchlist.json       Stage A output — mechanism, evidence, kill switches, patterns
state/macro-latest.json    persisted §6.1 hard-gate state + last §6.2 R computation
state/calibration.json     the §17 paper-trade ledger
weekly/YYYY-MM-DD.json     Stage A run record (Phase 5)
daily/YYYY-MM-DD.json      Stage B run record (Phase 5)
adhoc/<ticker>-*.json      bench-check run records (Phase 5)
```

Design rules carried forward from v6: file-per-day where a run produces one (greppable,
diffable, absence = failure signal); `schema_version` on every file; numbers that couldn't be
verified are `null` with a note, never estimated (`[ASSUMPTION]` per §2, more broadly — every
field on the engine's output carries one of §2's three labels in spirit, even where the JSON
doesn't spell out the tag literally). New for v7: engine code and `config.yaml`'s template
arrive in the private repo via a versioned release script (Phase 6), not by hand-editing there
— the private repo always records which engine version produced a given run (§21).

## `state/config.yaml`

A byte-identical copy of [`engine/config.example.yaml`](../engine/config.example.yaml) — itself
an `awk`-extracted, not hand-transcribed, copy of §20 — plus one addition:

```yaml
portfolio:
  nav: null              # ALWAYS null — read live each run, never stored (ADR 0013)
  currency: USD
  account_ref: null      # SET BY HUMAN — the Robinhood account_number for the LEAPS book
```

`account_ref` must be set before any real run. Phase 0 found the connector returns multiple
accounts on this login and at least one carries zero NAV; the engine never infers which is
correct (`engine.sizing.NAVCapInputs`' existing-exposure fields apply the same rule).

## `state/watchlist.json`

Stage A's output (§4.1): a **soft target of 15 companies** (25 is a hard ceiling, never a
target to grow toward — project addition, 2026-09-03, since v7.md's own 15–25 range has no
mechanism against a bigger list diluting average evidence quality), each mapped to exactly one
§5 mechanism with dated evidence. Seeded with the 9 names from §5's own seed list; expansion
toward 15 began 2026-09-03 with the staleness/cap-and-replace disciplines below in place first.

| Field | Notes |
|---|---|
| `ticker`, `company` | — |
| `mechanism` | `M1` \| `M2` \| `M3` \| `M4` |
| `status` | `active` \| `mechanism_ok_no_current_dislocation` \| `gated_binary_event` \| `retired` — a name can be mechanism-eligible without being a current hunting target; status says which |
| `evidence` | array of `{claim, type: FACT\|ASSUMPTION, source, as_of}` — §2's labeling, applied literally |
| `kill_switch` | the §9 mechanism-level kill switch text, plus any name-specific addendum |
| `kill_switch_check_<date>` | dated result of the most recent kill-switch re-check — always present after the first real `weekly-review` pass on a name, even when the result is "not triggered" |
| `permitted_entry_patterns` | subset of the four §10 patterns judged plausible for this name's mechanism (e.g. M1 names never get `quiet_inflection`; M3 names never get `bottleneck_expansion`) |
| `s8_status` | `null` \| `"in_progress"` \| `"pass"` \| `"fail"` — only meaningful for M3 names. `"in_progress"` is a real, honest state (not a placeholder): some §8 dimensions clear, at least one is genuinely inconclusive on the evidence gathered so far — see `s8_detail` |
| `s8_detail` | present once §8 has been run for real: one `[FACT]`/`[ASSUMPTION]`-labeled note per dimension (core retention, forward demand, usage/engagement, pricing/competitive, filing/transcript) |
| `next_earnings` | from Robinhood `get_earnings_results`, checked against §7's 14-day blackout |
| `verification_depth` | `"phase4_seed"` (initial pass, lighter bar) or `"weekly_review_<date>"` (a real evidence pass — news/filings/fundamentals actually pulled that date, not just a kill-switch check) |
| `mechanism_reverified_through` | `YYYY-MM-DD`, ~75 days past the last real evidence pass (project addition, 2026-09-03). Past this date, the next `weekly-review` must either refresh the name for real or retire it as stale — this is what stops a name coasting indefinitely just because its kill switch never fired |

**Cap-and-replace discipline** (project addition, 2026-09-03): below the 15-name soft target,
new candidates are admitted outright on the same §5 evidence bar as any existing name. At or
above 15, admitting one requires retiring the current weakest-evidenced name in the same pass
— thinnest/oldest evidence, furthest past its `mechanism_reverified_through` date, or longest-
dormant `mechanism_ok_no_current_dislocation` status. Full reasoning in
`.claude/skills/weekly-review/SKILL.md` §6.

## `state/macro-latest.json`

Persists [`engine.macro.HardGateState`](../engine/macro.py) per §6.1 gate — `active` and
`consecutive_release_days` — so the daily routine performs a one-step state transition each
run rather than replaying history. Breadth has no history to replay against regardless (it
only starts accumulating once a desktop-cadence job first runs, ADR 0012), which is exactly
why the hard-gate design is incremental for all three gates uniformly, not just the one that
strictly requires it (see the module's own docstring). Also carries the last
[`RestrictedRegimeResult`](../engine/macro.py) (§6.2) and a `breadth` block populated by that
desktop-cadence job (ADR 0012 — Massive Market Data is absent from cloud routines).

## `state/calibration.json`

The §17 paper-trade ledger. Every candidate that clears §11 scoring gets an entry — regardless
of whether §13.3 (`engine.sizing.compute_feasibility`) finds it feasible at current NAV. This
*is* the calibration cohort: `min_comparable_observations_for_normal_size` (50, from §20) is
the count of realized-outcome entries needed before a mechanism/structure combination graduates
from the 0.25% unvalidated-setup cap to its full structure-specific cap. An infeasible entry is
not a wasted screen — it is exactly as valuable to the ledger as a feasible one.

## Reader contracts

- **`bench-check`** (Phase 5): reads `state/watchlist.json` and `state/macro-latest.json` to
  reuse the daily/weekly work at near-zero token cost — see the migration plan §4.
- **A missing `weekly/` or `daily/` file for a session that should have run one** still means
  the automation failed, same as v6.1's rule; the file types just changed shape.
