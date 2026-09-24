"""Screener feed: persistence tracking for the four saved Legend scans
(ADR 0020).

The feed is a candidate source for Stage A, never a gate. `daily-screen`
runs the scans and records hits through `update_feed`; `weekly-review`
reads persistent hits through `promotable` and sends each one down its
normal admission path. Nothing here screens, scores or admits a name.

Pure functions, no I/O: the skill makes the `run_scan` calls and reads and
writes `state/screener-feed.json`. Persistence is counted in *sessions* (days
the feed actually ran), never calendar days, so a holiday or a fully failed
run doesn't count against a name.

Thresholds (`window`, `min_hits`, `prune_after`) come from the config's
`screener_feed` block (ADR 0010), never literals here.
"""
from __future__ import annotations

import copy

from .config import get

SCHEMA_VERSION = 1


def _feed_cfg(cfg: dict) -> tuple[int, int, int]:
    window = get(cfg, "screener_feed.window")
    min_hits = get(cfg, "screener_feed.min_hits")
    prune_after = get(cfg, "screener_feed.prune_after")
    for name, value in (("window", window), ("min_hits", min_hits), ("prune_after", prune_after)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"screener_feed.{name} must be a positive integer, got {value!r}")
    return window, min_hits, prune_after


def normalize_tickers(tickers) -> list[str]:
    """Strip, uppercase, drop empties and non-strings, dedupe; keep first-seen order."""
    out: list[str] = []
    for t in tickers or []:
        if not isinstance(t, str):
            continue
        s = t.strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def tickers_from_scan(result: dict) -> tuple[list[str], bool]:
    """Extract tickers from a `run_scan` response and whether it was truncated.

    Reads `data.result.results[].ticker` only, ignoring every other column
    (they are raw unformatted strings the feed doesn't need). Truncated means
    `total_items` exceeds the rows returned, i.e. the scan hit a row cap; we
    don't paginate. Accepts either the full response or its `data` object.
    Raises ValueError on a response without that shape, so a malformed reply
    is recorded as a failed source rather than an empty one.
    """
    data = result.get("data", result) if isinstance(result, dict) else None
    inner = data.get("result") if isinstance(data, dict) else None
    rows = inner.get("results") if isinstance(inner, dict) else None
    if not isinstance(rows, list):
        raise ValueError("run_scan response has no data.result.results list")
    tickers = normalize_tickers(r.get("ticker") for r in rows if isinstance(r, dict))
    total = inner.get("total_items")
    truncated = isinstance(total, int) and total > len(rows)
    return tickers, truncated


def update_feed(feed: dict | None, hits_by_source: dict[str, list[str]], today: str,
                cfg: dict, sources_failed: dict[str, str] | None = None,
                truncated: list[str] | None = None) -> dict:
    """Return a NEW feed dict with today's session recorded.

    `hits_by_source` holds only the sources that answered; a failed source is
    absent there and named in `sources_failed` with its error string.

    - `feed=None` initializes an empty schema_version 1 feed.
    - Idempotent per date: re-running the same day replaces that day's hits
      for every source that answered this time. A source that failed on the
      re-run keeps whatever it recorded earlier the same day.
    - If no source answered, today is not added as a session (nothing was
      observed); only `last_run` is updated.
    - Tickers are dropped once their `last_seen` falls outside the last
      `prune_after` sessions, and `sessions` is trimmed to the last
      `max(window, prune_after)`. Per-ticker `hit_dates` are trimmed to the
      retained sessions; `first_seen` and `sources` keep their full history
      while the ticker stays in the file.
    """
    window, _, prune_after = _feed_cfg(cfg)
    sources_failed = dict(sources_failed or {})
    truncated = sorted(set(truncated or []))

    new = copy.deepcopy(feed) if feed else {
        "schema_version": SCHEMA_VERSION, "last_updated": None, "sessions": [],
        "last_run": None, "tickers": {},
    }
    sessions: list[str] = new["sessions"]
    if sessions and today < sessions[-1]:
        raise ValueError(f"today {today} is before the latest recorded session {sessions[-1]}")

    ok = {src: normalize_tickers(hits) for src, hits in hits_by_source.items()
          if src not in sources_failed}
    new["last_run"] = {
        "date": today,
        "sources_ok": sorted(ok),
        "sources_failed": sources_failed,
        "truncated": truncated,
    }
    new["last_updated"] = today
    if not ok:
        return new

    if not sessions or sessions[-1] != today:
        sessions.append(today)

    tickers: dict = new["tickers"]
    # Clear today's hits for every source that answered, then re-add them.
    for rec in tickers.values():
        today_srcs = rec["hit_sources_by_date"].get(today)
        if today_srcs is None:
            continue
        kept = [s for s in today_srcs if s not in ok]
        if kept:
            rec["hit_sources_by_date"][today] = kept
        else:
            del rec["hit_sources_by_date"][today]
            rec["hit_dates"].remove(today)

    for src, hits in ok.items():
        for t in hits:
            rec = tickers.setdefault(t, {
                "sources": [], "first_seen": today, "last_seen": today,
                "hit_dates": [], "hit_sources_by_date": {},
            })
            day = rec["hit_sources_by_date"].setdefault(today, [])
            if src not in day:
                day.append(src)
                day.sort()
            if today not in rec["hit_dates"]:
                rec["hit_dates"].append(today)
            if src not in rec["sources"]:
                rec["sources"].append(src)
                rec["sources"].sort()

    # Recompute last_seen (a same-day re-run can remove today's only hit),
    # then prune and trim.
    retained = sessions[-max(window, prune_after):]
    recent = set(sessions[-prune_after:])
    retained_set = set(retained)
    for t in list(tickers):
        rec = tickers[t]
        rec["hit_dates"] = sorted(d for d in rec["hit_dates"] if d in retained_set)
        rec["hit_sources_by_date"] = {d: rec["hit_sources_by_date"][d] for d in rec["hit_dates"]}
        if not rec["hit_dates"]:
            del tickers[t]
            continue
        rec["last_seen"] = rec["hit_dates"][-1]
        if rec["last_seen"] not in recent:
            del tickers[t]
    new["sessions"] = retained
    new["tickers"] = dict(sorted(tickers.items()))
    return new


def _watchlist_status(watchlist: dict) -> dict[str, str]:
    """Ticker -> status from `state/watchlist.json`'s `names` list."""
    out = {}
    for entry in (watchlist or {}).get("names", []):
        t = entry.get("ticker")
        if isinstance(t, str) and t.strip():
            out[t.strip().upper()] = entry.get("status")
    return out


def promotable(feed: dict, watchlist: dict, today: str, cfg: dict) -> dict:
    """Return the tickers persistent enough for a Stage A admission look.

    Window = the last `window` recorded sessions on or before `today`.
    A ticker qualifies with at least `min_hits` hits in the window, and
    nothing qualifies until the window is full. Qualifying tickers already on
    the watchlist are excluded; a retired one goes to `retired_rehit` instead.

    `multi_source` lists every off-watchlist ticker two or more scans hit
    within the window, whatever its hit count. It is a review-priority flag,
    never a promotion.

    Each item: `{ticker, hits_in_window, sources, multi_source}`, where
    `sources` are the scans that hit it within the window. Lists are sorted by
    hits desc, multi_source first, ticker asc.
    """
    window, min_hits, _ = _feed_cfg(cfg)
    sessions = [s for s in (feed or {}).get("sessions", []) if s <= today]
    win = sessions[-window:]
    win_set = set(win)
    full = len(win) >= window
    result = {
        "promotable": [],
        "retired_rehit": [],
        "multi_source": [],
        "window_sessions": len(win),
        "window_full": full,
        "last_session": sessions[-1] if sessions else None,
    }

    on_list = _watchlist_status(watchlist)
    for t, rec in ((feed or {}).get("tickers") or {}).items():
        dates = [d for d in rec.get("hit_dates", []) if d in win_set]
        if not dates:
            continue
        srcs = sorted({s for d in dates for s in rec.get("hit_sources_by_date", {}).get(d, [])})
        item = {"ticker": t, "hits_in_window": len(dates), "sources": srcs,
                "multi_source": len(srcs) >= 2}
        status = on_list.get(t)
        if status is not None and status != "retired":
            continue
        if item["multi_source"]:
            result["multi_source"].append(item)
        if full and len(dates) >= min_hits:
            result["promotable" if status is None else "retired_rehit"].append(item)

    def order(i):
        return (-i["hits_in_window"], not i["multi_source"], i["ticker"])

    for key in ("promotable", "retired_rehit", "multi_source"):
        result[key].sort(key=order)
    return result


def notification_lines(hits_by_source: dict[str, list[str]], promo: dict,
                       sources_failed: dict[str, str] | None = None,
                       truncated: list[str] | None = None,
                       source_order: list[str] | None = None) -> list[str]:
    """The run notification's feed line, plus a warning line if any scan
    failed or was truncated. `source_order` is the configured scan keys, so a
    failed source still shows in the counts as `failed`."""
    sources_failed = sources_failed or {}
    truncated = truncated or []
    order = source_order or sorted(set(hits_by_source) | set(sources_failed))
    counts, total = [], 0
    for src in order:
        if src in sources_failed:
            counts.append(f"{src} failed")
        else:
            n = len(normalize_tickers(hits_by_source.get(src, [])))
            total += n
            counts.append(f"{src} {n}")
    promo_names = ", ".join(i["ticker"] for i in promo.get("promotable", [])) or "none"
    if not promo.get("window_full", True):
        promo_names = f"none yet (sessions recorded: {promo.get('window_sessions', 0)})"
    multi = [i["ticker"] for i in promo.get("multi_source", [])]
    line = f"Screener feed: {total} hits ({' / '.join(counts)}) | promotable: {promo_names}"
    if multi:
        line += f" | multi-source: {', '.join(multi)}"
    if promo.get("retired_rehit"):
        line += f" | retired re-hit: {', '.join(i['ticker'] for i in promo['retired_rehit'])}"
    lines = [line]
    warnings = [f"{src} failed ({err})" for src, err in sources_failed.items()]
    warnings += [f"{src} truncated" for src in sorted(truncated)]
    if warnings:
        lines.append("Screener feed warning: " + " | ".join(warnings))
    return lines
