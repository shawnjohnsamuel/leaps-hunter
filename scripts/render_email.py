#!/usr/bin/env python3
"""Render the daily subscriber email (HTML + subject) from a sanitized public artifact.

Reads ONLY public-data JSON (already through the sanitizer's allowlist), so nothing
private can reach an inbox by construction. Emits JSON {subject, html} on stdout for
the broadcast workflow.

v2: targets schema_version 2 (v7). The 5 archived schema_version 1 (v6.1) days were
already emailed when they happened; this script never needs to re-render them.

Usage: render_email.py public-data/latest.json <site_url>
"""
import html
import json
import sys

DISCLAIMER = (
    "NOT FINANCIAL ADVICE. This email is the output of a rules-based AI research "
    "system. It can be wrong. Nothing here is a recommendation to buy or sell any "
    "security; no advisory relationship exists. Options can lose 100% of premium. "
    "Do your own research and consult a licensed professional."
)

MECHANISM_LABELS = {
    "M1": "bottleneck ownership",
    "M2": "AI demand multiplier",
    "M3": "narrative reversal",
    "M4": "sanctioned secondary",
}


def main():
    pub = json.loads(open(sys.argv[1]).read())
    if pub.get("kind") != "public-daily":
        sys.exit("REFUSED: input is not a sanitized public artifact (kind != 'public-daily'). "
                 "Emails render only from post-sanitizer data — run scripts/sanitize.py first.")
    if pub.get("schema_version") != 2:
        sys.exit(f"REFUSED: render_email.py v2 targets schema_version 2 (got {pub.get('schema_version')!r}).")

    site = sys.argv[2].rstrip("/")
    e = html.escape
    date = pub["date"]
    macro = pub.get("macro") or {}
    candidates = pub.get("candidates") or []
    near_misses = pub.get("nearest_misses") or []
    gates = pub.get("gates_summary") or {}
    examined = pub.get("candidates_examined") or 0
    result = pub.get("result")

    def mech(tag):
        return MECHANISM_LABELS.get(tag, tag or "")

    if result == "HOLIDAY":
        subject = f"Take the LEAP — {date}: market closed"
        body_bits = ["<p>Market holiday — no screen was run. Next session resumes the record.</p>"]
    elif result == "DATA_INSUFFICIENT":
        subject = f"Take the LEAP — {date}: data insufficient, no screen completed"
        body_bits = ["<p>A required input (live quotes, NAV, or macro state) was not verifiably "
                     "available today, so the screen stopped rather than guess. Fail-closed, not a leak.</p>"]
    elif result == "CANDIDATE" and candidates:
        tickers = ", ".join(c["ticker"] for c in candidates)
        subject = f"Take the LEAP — {date}: {tickers} surfaced"
        body_bits = [
            f"<p><b>{len(candidates)} candidate(s) cleared every gate today.</b></p>",
            "<ul>"
            + "".join(
                f"<li><b>{e(c['ticker'])}</b> — {e(mech(c.get('mechanism')))}"
                + (f" · {e(c['score'])}" if c.get("score") else "")
                + (f"<br><i>{e(c['one_line'])}</i>" if c.get("one_line") else "")
                + "</li>"
                for c in candidates
            )
            + "</ul>",
            f'<p>Full details, structure, and the honest caveats live on the site: <a href="{site}/dashboard">the record</a>.</p>',
        ]
    else:
        subject = f"Take the LEAP — {date}: 0 trades, discipline held"
        body_bits = [
            f"<p><b>Zero deployable trades today — that is the system working.</b> "
            f"{examined} names screened; every one died at a gate or fell short of the scoring bar.</p>"
        ]

    if macro:
        regime_line = "RESTRICTED" if macro.get("restricted") else "normal"
        gate_line = (
            f"macro hard gate ACTIVE ({', '.join(macro.get('hard_gate_names') or [])})"
            if macro.get("hard_gate_active") else "no macro hard gate active"
        )
        body_bits.insert(
            0,
            f"<p><b>Macro: R={e(str(macro.get('R')))} — {regime_line} regime</b> "
            f"(qualifying score threshold {e(str(macro.get('score_threshold')))}/100)<br>{e(gate_line)}</p>",
        )

    if near_misses:
        rows = "".join(
            f"<li><b>{e(nm['ticker'])}</b> ({e(mech(nm.get('mechanism')))})"
            + (f" — {e(nm['score'])}" if nm.get("score") else "")
            + "</li>"
            for nm in near_misses
        )
        body_bits.append(f"<p><b>Nearest misses today:</b></p><ul>{rows}</ul>")

    if gates:
        rows = "".join(f"<li>{e(g)}: {n}</li>" for g, n in gates.items())
        body_bits.append(f"<p>Why the rest were screened out:</p><ul>{rows}</ul>")

    html_doc = f"""<div style="font-family:system-ui,sans-serif;max-width:560px;margin:auto;color:#1a1a1a">
<h2 style="margin-bottom:0">Take the <span style="color:#059669">LEAP</span></h2>
<p style="color:#666;margin-top:4px">{date} · daily verdict</p>
<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:12px;font-size:13px;margin:12px 0">
<b>⚠️ {DISCLAIMER}</b></div>
{''.join(body_bits)}
<p><a href="{site}/dashboard">View the full record →</a></p>
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
<p style="font-size:12px;color:#888">{DISCLAIMER} You are receiving this because you
subscribed at {site}. <a href="{{{{{{RESEND_UNSUBSCRIBE_URL}}}}}}">Unsubscribe</a> any time.</p>
</div>"""
    print(json.dumps({"subject": subject, "html": html_doc}))


if __name__ == "__main__":
    main()
