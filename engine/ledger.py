"""§17's paper ledger (state/calibration.json), made able to calibrate.

ADR 0013 made the ledger the year-one output, but through 2026-11-03 nothing
ever filled in an entry's `realized_outcome`, and a name that cleared on two
consecutive days was logged twice. Both meant §17's 50-observation count could
not move: the unvalidated-setup cap (0.25% of NAV) was permanent by
construction, not by evidence. ADR 0021 adds the missing lifecycle:

- **One entry per episode.** While a name has an open entry, a fresh clear is
  a re-confirmation of that entry, not a new observation (`open_entry`).
- **Marks.** `weekly-review` marks every open entry at the logged contract's
  bid (`mark`), so the record shows the path, not only the endpoint.
- **Close.** After `calibration.outcome_horizon_days`, or on a kill switch,
  the entry closes at its latest mark (`close`). Only closed entries count
  toward calibration (`closed_count` / `is_calibrated`).

Entries are plain dicts so the JSON file stays the source of truth; nothing
here reads or writes files.
"""
from __future__ import annotations

from datetime import date

from .config import get


def open_entry(entries: list[dict], ticker: str) -> dict | None:
    """The ticker's entry that has no `realized_outcome` yet, if any. Entries
    marked `duplicate_of` (re-logs written before ADR 0021) are ignored."""
    for e in entries:
        if e.get("ticker") == ticker and e.get("realized_outcome") is None and not e.get("duplicate_of"):
            return e
    return None


def reconfirm(entry: dict, today: str, s11_total: int) -> dict:
    """Record a same-episode clear on the open entry instead of logging a new
    one. Returns the updated entry."""
    entry.setdefault("reconfirmed", []).append({"date": today, "s11_total": s11_total})
    return entry


def mark(entry: dict, as_of: str, bid: float | None, note: str | None = None,
         share_price: float | None = None) -> dict:
    """Append a mark at the contract's bid (what a paper exit would get).
    A missing quote is recorded as such, never filled in. `share_price`
    also tracks the share fallback (ADR 0022) against the entry's
    `share_fallback.spot`, so each vehicle gets its own record."""
    p0 = entry.get("executable_entry_p0")
    rec = {"date": as_of, "bid": bid}
    if bid is not None and p0:
        rec["return_pct"] = round((bid / p0 - 1) * 100.0, 2)
    spot0 = (entry.get("share_fallback") or {}).get("spot")
    if share_price is not None:
        rec["share_price"] = share_price
        if spot0:
            rec["share_return_pct"] = round((share_price / spot0 - 1) * 100.0, 2)
    if note:
        rec["note"] = note
    entry.setdefault("marks", []).append(rec)
    return entry


def due_to_close(entry: dict, today: str, cfg: dict) -> bool:
    horizon = get(cfg, "calibration.outcome_horizon_days")
    return (date.fromisoformat(today) - date.fromisoformat(entry["date"])).days >= horizon


def close(entry: dict, as_of: str, reason: str) -> dict:
    """Close at the latest mark that has a bid. Raises if there is none: an
    outcome with no observed exit price would be a fabricated observation."""
    priced = [m for m in entry.get("marks", []) if m.get("bid") is not None]
    if not priced:
        raise ValueError(f"{entry.get('ticker')} {entry.get('date')}: no priced mark to close at")
    last = priced[-1]
    entry["realized_outcome"] = {
        "closed_on": as_of,
        "exit_bid": last["bid"],
        "exit_mark_date": last["date"],
        "return_pct": last.get("return_pct"),
        "share_return_pct": last.get("share_return_pct"),
        "reason": reason,
    }
    return entry


def closed_count(entries: list[dict], mechanism: str, structure_type: str) -> int:
    return sum(
        1 for e in entries
        if e.get("mechanism") == mechanism
        and e.get("structure_type") == structure_type
        and e.get("realized_outcome") is not None
        and not e.get("duplicate_of")
    )


def is_calibrated(entries: list[dict], mechanism: str, structure_type: str, cfg: dict) -> bool:
    """§17: normal sizing needs this many *closed* comparable observations."""
    need = get(cfg, "sizing.min_comparable_observations_for_normal_size")
    return closed_count(entries, mechanism, structure_type) >= need
