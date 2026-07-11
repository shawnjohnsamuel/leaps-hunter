#!/usr/bin/env python3
"""Sanitize a private daily LEAPS Hunter report into its public artifact.

Strict ALLOWLIST design (ADR 0002 / plan Part 7.1): fields are *copied in* by name,
never filtered out. Anything not explicitly listed here does not exist publicly —
holdings, correlation sets, and free-text that could reference positions never flow.

Usage:  sanitize.py <private-daily.json> <public-out-dir>
Exits non-zero (publishing must abort) if a leak tripwire fires.
"""
import json
import re
import sys
from pathlib import Path

# Gates whose very presence on a name reveals holdings. Named entries carrying these
# are folded into an aggregate count and never appear as tickers publicly.
HOLDINGS_GATES = {"portfolio_correlation_held", "portfolio_correlation_crowding"}

# Public vocabulary for gate types (also hides internal naming).
GATE_LABELS = {
    "binary_event": "binary-event window",
    "momentum_chasing": "momentum / chasing",
    "valuation_insanity": "valuation",
    "single_variable": "single-variable dependency",
    "liquidity_floor": "liquidity floors",
    "macro_mismatch": "macro mismatch",
    "time_insufficiency": "option duration",
    "universe_fit": "universe fit",
    "repeat_guard": "repeat guard",
}

# Words that must never appear in any public free-text field.
FORBIDDEN_TEXT = re.compile(r"\b(held|holding|holdings|portfolio|position|account)\b", re.I)

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


def sanitize(priv: dict) -> dict:
    regime = priv.get("regime") or {}
    rotation = priv.get("rotation_watch") or {}
    thesis = priv.get("thesis") or {}
    screened = priv.get("screened") or []

    gate_counts = {}
    watch_only = []
    for s in screened:
        gate = s.get("gate_failed")
        if gate in HOLDINGS_GATES:
            gate_counts["portfolio-fit"] = gate_counts.get("portfolio-fit", 0) + 1
        elif gate:
            label = GATE_LABELS.get(gate, "other")
            gate_counts[label] = gate_counts.get(label, 0) + 1
        elif s.get("disposition") == "triaged_below_threshold":
            gate_counts["scored below threshold"] = gate_counts.get("scored below threshold", 0) + 1

    candidates = []
    for c in priv.get("candidates") or []:
        if c.get("score", 0) >= 75:
            candidates.append({
                "ticker": c["ticker"],
                "score": c["score"],
                "tier": c["tier"],
                "one_line": clean_text((c.get("entry") or {}).get("why_now"), "candidate.one_line"),
            })
        elif c.get("score", 0) >= 70:
            watch_only.append(c["ticker"])

    nm = priv.get("nearest_miss") or None
    nearest_miss = None
    if nm and nm.get("ticker"):
        # Free text NEVER flows; only ticker + public gate label — and holdings gates redact fully.
        priv_entry = next((s for s in screened if s.get("ticker") == nm["ticker"]), {})
        gate = priv_entry.get("gate_failed")
        if gate in HOLDINGS_GATES:
            nearest_miss = {"ticker": None, "gate": "portfolio-fit"}
        else:
            nearest_miss = {"ticker": nm["ticker"], "gate": GATE_LABELS.get(gate, "scored below threshold")}

    pub = {
        "schema_version": 1,
        "kind": "public-daily",
        "disclaimer": DISCLAIMER,
        "date": priv["date"],
        "report_type": (priv.get("run") or {}).get("report_type"),
        "framework_version": (priv.get("run") or {}).get("framework_version"),
        "regime": {
            "verdict": regime.get("verdict"),
            "confidence": regime.get("confidence"),
            "reasoning": clean_text(regime.get("reasoning"), "regime.reasoning"),
            "effective_threshold": regime.get("effective_threshold"),
        } if regime else None,
        "rotation_watch": {
            "summary": clean_text(rotation.get("summary"), "rotation.summary"),
            "confidence": rotation.get("confidence"),
        } if rotation else None,
        "thesis": {"name": thesis.get("name"), "status": thesis.get("status")} if thesis else None,
        "screened": {"total": len(screened), "gates": gate_counts},
        "candidates": candidates,
        "watch_only": watch_only,
        "nearest_miss": nearest_miss,
        "degraded": bool((priv.get("degraded") or {}).get("is_degraded")),
    }
    return pub


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    priv_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    priv = json.loads(priv_path.read_text())
    pub = sanitize(priv)

    # Final whole-document tripwires.
    blob = json.dumps(pub)
    for term in ("correlation_set", "portfolio_correlation", "account_number", "average_buy_price", "quantity"):
        if term in blob:
            sys.exit(f"LEAK TRIPWIRE (document): '{term}' present — publishing aborted")

    # Held-ticker check, run PRIVATELY at generation time (the ticker list never leaves
    # this side of the boundary). A held ticker may only appear if it legitimately came
    # through a non-holdings screening path (e.g., market commentary) — err strict: any
    # occurrence as a JSON string value aborts publishing for human review.
    corr = priv.get("correlation_set") or {}
    held = set(corr.get("equities", [])) | set(corr.get("options", [])) | set(corr.get("etfs_passive", []))
    for t in held:
        if f'"{t}"' in blob:
            sys.exit(f"LEAK TRIPWIRE (held ticker): '{t}' appears in public output — publishing aborted")

    out = out_dir / "daily" / f"{pub['date']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pub, indent=2) + "\n")
    (out_dir / "latest.json").write_text(json.dumps(pub, indent=2) + "\n")
    print(f"sanitized -> {out}")


if __name__ == "__main__":
    main()
