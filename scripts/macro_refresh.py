"""Deterministic macro-refresh (ADR 0021): the `macro-refresh` skill's steps 1,
1a, 2 and 3 as one script, so they can run unattended in a GitHub Action
instead of a desktop Claude session.

Why a script: every number this job produces already comes from an engine
function, and the job has no judgment calls. Run as a desktop scheduled task it
stalled on permission prompts (the 2026-10-18 and 2026-10-25 runs stopped at
their first command and wrote nothing), which left daily-screen 16 days stale
and halted it on 2026-10-27/28. GitHub's runners are not behind the cloud-routine
egress block (ADR 0014), so FRED, multpl.com and Alpha Vantage are reachable.

Usage (from the public repo's root):
    python -m scripts.macro_refresh --data /path/to/leaps-hunter-data [--today YYYY-MM-DD] [--skip-ntm]

Reads ALPHA_VANTAGE_API_KEY from the environment; without it, NTM is skipped
and every cached `ntm` field is left as it is. Writes only
state/macro-latest.json (never `hard_gates.equity_deleveraging` or `breadth`,
which daily-screen owns) and the `ntm` field of each state/watchlist.json name.
Exits non-zero, writing nothing, if any FRED or CAPE fetch fails: a stale
number must never be written back as a fresh one. Committing is the caller's job.

Step 1b (the NYSE breadth universe from Massive) is not here: Massive is a
desktop extension. That list moves a handful of names a month and is only read
when breadth is needed, so the desktop skill refreshes it occasionally.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from engine import macro, sources
from engine.config import get, load_config

FRED_SERIES = ["BAMLH0A0HYM2", "BAA10Y", "DFII10", "DGS10", "T5YIFR", "DFII30", "WALCL", "WTREGEN", "RRPONTSYD"]


def _fetch(fn, *args, attempts: int = 3):
    for i in range(attempts):
        try:
            series = fn(*args)
            if series:
                return series
            err = "empty series"
        except Exception as e:  # network errors surface as several exception types
            err = f"{type(e).__name__}: {e}"
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{fn.__name__}{args}: {err}")


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _advance(gate: dict, rows, cfg_key: str, cfg: dict, today: str, label: str) -> tuple[dict, int]:
    cursor = gate.get("last_observation_date")
    if not cursor:
        raise RuntimeError(f"{label}: last_observation_date missing; refusing to guess a start date (ADR 0017)")
    prev = macro.HardGateState(gate["active"], gate.get("consecutive_release_days", 0))
    state, new_cursor, steps = macro.advance_hard_gate(
        prev, rows, after=cursor, release_streak_required=get(cfg, cfg_key))
    latest = sorted(rows)[-1]
    gate = dict(gate)
    gate.update({
        "active": state.active,
        "consecutive_release_days": state.consecutive_release_days,
        "last_checked": today,
        "last_observation_date": new_cursor,
        "trigger_fired_today": latest[1],
        "release_condition_met_today": latest[2],
        "replay_note": (f"ADR 0017: stepped once per trading-day close after last_observation_date. "
                        f"{today} run (scripts/macro_refresh.py): replayed {steps} close(s) from cursor "
                        f"{cursor} to {new_cursor}; {'ACTIVE' if state.active else 'inactive'}/"
                        f"{state.consecutive_release_days} at end."),
    })
    return gate, steps


def refresh_macro(data: Path, cfg: dict, today: str) -> tuple[dict, list[str]]:
    path = data / "state" / "macro-latest.json"
    m = json.loads(path.read_text())

    fred = {sid: _fetch(sources.fetch_fred_series, sid) for sid in FRED_SERIES}
    cape = _fetch(sources.fetch_cape_series)

    credit, credit_steps = _advance(
        m["hard_gates"]["credit_stress"], macro.credit_stress_daily(fred["BAMLH0A0HYM2"], cfg),
        "macro_hard_gates.credit_stress.release_consecutive_closes", cfg, today, "credit_stress")
    infl, infl_steps = _advance(
        m["hard_gates"]["inflation_duration_shock"],
        macro.inflation_shock_daily(fred["DFII10"], fred["DGS10"], fred["T5YIFR"], cfg),
        "macro_hard_gates.inflation_duration_shock.release_consecutive_closes", cfg, today,
        "inflation_duration_shock")

    liquidity = macro.net_liquidity_series(fred["WALCL"], fred["WTREGEN"], fred["RRPONTSYD"])
    rr = macro.compute_restricted_regime(
        cfg,
        cape_now=cape[-1][1], cape_history=[v for _, v in cape],
        credit_now=fred["BAA10Y"][-1][1], credit_history=[v for _, v in fred["BAA10Y"]],
        real30_now=fred["DFII30"][-1][1], real30_history=[v for _, v in fred["DFII30"]],
        liquidity_contracting=macro.net_liquidity_contracting(liquidity),
    )

    latest = {sid: s[-1][0] for sid, s in fred.items()}
    latest["CAPE"] = cape[-1][0]
    lag = macro.stale_sources(latest, today, cfg)
    as_of = min(latest.values())

    prev_r = m.get("restricted_regime", {}).get("R")
    m["as_of"] = as_of
    m["last_refreshed"] = today
    m["run_type"] = "macro_refresh"
    m["hard_gates"]["credit_stress"] = credit
    m["hard_gates"]["inflation_duration_shock"] = infl
    m["restricted_regime"] = {
        "R": rr.R, "components": rr.components, "restricted": rr.restricted,
        "score_threshold": rr.score_threshold, "kelly_multiplier": rr.kelly_multiplier, "as_of": as_of,
    }
    m["source_freshness"] = {
        "checked_on": today,
        "basis": "ADR 0018: engine.macro.stale_sources against config macro_staleness.source_cadence / max_source_lag_days",
        "latest_observation_by_series": latest,
        "stale": [list(s) for s in lag.stale],
        "unconfigured": lag.unconfigured,
        "ok": lag.ok,
    }
    lines = [
        f"R={rr.R} ({'RESTRICTED' if rr.restricted else 'normal'}, threshold {rr.score_threshold}, "
        f"kelly {rr.kelly_multiplier}x){'' if prev_r == rr.R else f' -- CHANGED from {prev_r}'}",
        f"credit_stress replayed {credit_steps} close(s) to {credit['last_observation_date']}, "
        f"{'ACTIVE' if credit['active'] else 'inactive'}",
        f"inflation_duration_shock replayed {infl_steps} close(s) to {infl['last_observation_date']}, "
        f"{'ACTIVE' if infl['active'] else 'inactive'}",
        "source freshness: " + ("ok" if lag.ok else f"STALE {lag.stale} UNCONFIGURED {lag.unconfigured}"),
    ]
    m["refresh_history_note"] = (
        f"{today} macro-refresh by scripts/macro_refresh.py (GitHub Action, ADR 0021): fetched all nine "
        f"FRED series and Shiller CAPE. " + "; ".join(lines) + ". Did not touch "
        "hard_gates.equity_deleveraging or breadth (daily-screen's, ADRs 0015/0016)."
    )
    _dump(path, m)
    return m, lines


def refresh_ntm(data: Path, today: str, api_key: str) -> list[str]:
    path = data / "state" / "watchlist.json"
    w = json.loads(path.read_text())
    refreshed, kept = [], []
    as_of = date.fromisoformat(today)
    for i, name in enumerate(w["names"]):
        if i:
            time.sleep(1.5)
        try:
            payload = sources.fetch_av_earnings_estimates(name["ticker"], api_key)
        except Exception as e:
            kept.append(f"{name['ticker']} (fetch error {type(e).__name__})")
            continue
        if "Information" in payload or "Note" in payload:
            # Rate limit: stop calling; every remaining name keeps its cached value.
            kept += [n["ticker"] + " (rate-limited)" for n in w["names"][i:]]
            break
        result = sources.compute_ntm_eps_revision(payload, as_of)
        if result.available or not (name.get("ntm") or {}).get("available"):
            name["ntm"] = {**asdict(result), "as_of": today}
            refreshed.append(name["ticker"])
        else:
            kept.append(f"{name['ticker']} (new result unavailable: {result.reason}; kept cached)")
    _dump(path, w)
    return [f"NTM refreshed {len(refreshed)}/{len(w['names'])}"] + ([f"kept cached: {', '.join(kept)}"] if kept else [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--skip-ntm", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.data / "state" / "config.yaml")
    try:
        _, lines = refresh_macro(a.data, cfg, a.today)
    except RuntimeError as e:
        print(f"MACRO REFRESH FAILED -- nothing written: {e}", file=sys.stderr)
        return 1
    key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if a.skip_ntm:
        lines.append("NTM skipped (--skip-ntm)")
    elif not key:
        lines.append("NTM skipped: ALPHA_VANTAGE_API_KEY not set; cached values kept")
    else:
        lines += refresh_ntm(a.data, a.today, key)
    summary = f"macro-refresh {a.today}: " + "; ".join(lines)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(summary + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
