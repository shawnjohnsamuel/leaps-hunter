#!/usr/bin/env python3
"""Sanitize a private v7 daily-screen report into its public artifact.

Strict ALLOWLIST design (ADR 0002 / migration plan Phase 7): fields are *copied in*
by name, never filtered out. Anything not explicitly listed here does not exist
publicly. Two fields in particular must NEVER be read into the output at all --
`account_ref` and `nav_at_run` -- v7's daily-screen writes both to the private
record (S0's NAV precondition check) and neither has any public-facing purpose;
this script's `sanitize()` function simply never names them, which is the
allowlist design's whole point: a leak here would require someone to add a new
line that reads a forbidden key, not merely fail to remove one.

v6.1's schema (regime verdict, thesis, tiers, correlation_set/held-ticker checks)
is gone -- this script targets ONLY v7-shaped private input
(`framework_version` starting "7."). The 5 already-published v6.1 public artifacts
in public-data/ are untouched, static files; the frontend renders them in legacy
mode (see app/lib/data.ts) rather than this script ever re-processing them.

Usage:  sanitize.py <private-daily.json> <public-out-dir>
Exits non-zero (publishing must abort) if a leak tripwire fires.
"""
import json
import re
import sys
from pathlib import Path

# Holdings-indicating language that must never appear in any public free-text field.
# Deliberately phrase-based rather than single-word: bare "holding"/"position" are
# ordinary market-commentary words, and firing on them produced a false positive on
# 2026-08-12 (v6.1 era) that blocked a clean publish. v7's daily-screen has no
# concept of "held" tickers in its own output (S15's portfolio-risk check reads
# positions in-memory but never logs them), so this tripwire is defense in depth,
# not the primary boundary mechanism -- the primary mechanism is the allowlist
# itself never naming account_ref/nav_at_run.
FORBIDDEN_TEXT = re.compile(
    r"\b(holdings|portfolio|cost basis|average buy price|shares? (?:i|we) (?:own|hold)"
    r"|(?:already|currently) held|(?:i|we) (?:own|hold)\b|(?:my|our) position)",
    re.I,
)

# Structured fail_category values that mean "this name is worth naming publicly as
# a near miss" -- distinguishes a name worth spotlighting from ordinary rejections
# aggregated into gates_summary. Matches daily-screen SKILL.md's fixed vocabulary.
NOTABLE_NEAR_MISS_CATEGORIES = {"s10_unresolved_confirmation", "s11_threshold", "s11_subgate", "s12_liquidity", "s12_ev"}

DISCLAIMER = (
    "Output of a rules-based AI research system. NOT financial advice; no client "
    "relationship exists; this may be wrong. Do your own research. Options can lose "
    "100% of premium. Hypothetical results are not real returns."
)


def clean_text(s, field):
    """Pass a curated free-text field through the tripwire."""
    if s is None:
        return None
    if FORBIDDEN_TEXT.search(s):
        sys.exit(f"LEAK TRIPWIRE ({field}): forbidden term in text — publishing aborted:\n  {s!r}")
    return s


def _score_summary(entry):
    """A short, safe public summary derived from S11's numeric bounds -- never the
    full 8-dimension breakdown (that level of live-application detail stays
    private even though the methodology itself, framework/v7.md, is fully
    public). None of these fields ever touch account_ref/nav_at_run."""
    lo, hi, thr = entry.get("s11_score_low"), entry.get("s11_score_high"), entry.get("s11_threshold")
    if lo is None or hi is None or thr is None:
        return None
    if lo == hi:
        return f"scored {lo}/{thr} needed"
    return f"scored {lo}-{hi}/{thr} needed"


def sanitize(priv: dict) -> dict:
    fw = priv.get("framework_version") or ""
    if not fw.startswith("7."):
        sys.exit(f"REFUSED: sanitize.py v2 targets v7 private records only (got framework_version={fw!r}). "
                 "v6.1 records were already sanitized as static files; do not re-run this script on them.")

    # Trust the private record's own top-level `result` field directly rather than
    # re-deriving it by pattern-matching free text (run_time_note can legitimately
    # *mention* another day's DATA INSUFFICIENT outcome in passing while describing
    # today's own, different result -- string-matching the whole note for that
    # phrase produced exactly that false positive during testing, 2026-09-04).
    if priv.get("per_name") is None and priv.get("result", "").upper() not in ("HOLIDAY",):
        result = "DATA_INSUFFICIENT"
    elif priv.get("candidates_clearing_s11", 0) > 0:
        result = "CANDIDATE"
    else:
        result = (priv.get("result") or "NO TRADE").upper().replace(" ", "_")
        if result not in ("NO_TRADE", "HOLIDAY", "CANDIDATE", "DATA_INSUFFICIENT"):
            result = "NO_TRADE"

    macro = priv.get("macro")
    macro_pub = None
    if macro:
        active = macro.get("hard_gates_active") or {}
        active_names = [k for k, v in active.items() if v]
        macro_pub = {
            "R": macro.get("R"),
            "restricted": macro.get("restricted"),
            "score_threshold": macro.get("score_threshold"),
            "hard_gate_active": bool(active_names),
            "hard_gate_names": active_names,
        }

    per_name = priv.get("per_name") or {}
    gates_summary = {}
    candidates = []
    near_misses = []
    for ticker, entry in per_name.items():
        cat = entry.get("fail_category", "unknown")
        mechanism = entry.get("mechanism")
        if cat == "cleared":
            score = _score_summary(entry)
            candidates.append({
                "ticker": ticker,
                "mechanism": mechanism,
                "score": score,
                "one_line": clean_text(entry.get("result"), f"per_name.{ticker}.result"),
            })
            continue
        gates_summary[cat] = gates_summary.get(cat, 0) + 1
        if cat in NOTABLE_NEAR_MISS_CATEGORIES:
            near_misses.append({
                "ticker": ticker,
                "mechanism": mechanism,
                "category": cat,
                "score": _score_summary(entry),
                "note": clean_text(entry.get("result"), f"per_name.{ticker}.result"),
            })

    pub = {
        "schema_version": 2,
        "kind": "public-daily",
        "disclaimer": DISCLAIMER,
        "date": priv["date"],
        "framework_version": priv.get("framework_version"),
        "result": result,
        "macro": macro_pub,
        "candidates_examined": priv.get("candidates_examined"),
        "candidates_clearing_gates": priv.get("candidates_clearing_s7_s10"),
        "candidates": candidates,
        "nearest_misses": near_misses,
        "gates_summary": gates_summary,
        "notable_finding": clean_text(priv.get("notable_finding"), "notable_finding"),
    }
    return pub


# Field names that must NEVER appear anywhere in a published document, whatever the
# schema. Checked against the whole serialized blob as a final, whole-document net --
# the allowlist in sanitize() is the primary control; this is defense in depth.
FORBIDDEN_DOCUMENT_TERMS = (
    "account_ref", "nav_at_run", "account_number", "correlation_set",
    "portfolio_correlation", "average_buy_price", "\"quantity\"",
)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    priv_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    priv = json.loads(priv_path.read_text())
    pub = sanitize(priv)

    blob = json.dumps(pub)
    for term in FORBIDDEN_DOCUMENT_TERMS:
        if term in blob:
            sys.exit(f"LEAK TRIPWIRE (document): '{term}' present — publishing aborted")

    out = out_dir / "daily" / f"{pub['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pub, indent=2) + "\n")
    (out_dir / "latest.json").write_text(json.dumps(pub, indent=2) + "\n")
    print(f"sanitized -> {out}")


if __name__ == "__main__":
    main()
