# ADR 0002: Public/private boundary is two repos, not a .gitignore

**Status:** accepted (2026-07-08)

## Context
This project is both a public engineering showcase and a tool that touches a real brokerage
account (read-only) and produces real trade scoring. Git history is permanent: a secret or
real output committed once remains in history even after deletion from HEAD, and scrubbing
requires force-pushing rewritten history to a public repo.

## Decision
Two physically separate repositories:
- **`leaps-hunter` (this repo, to be public):** methodology, framework versions and audit,
  skills, app code, docs, synthetic demo data only.
- **`leaps-hunter-data` (private):** dated daily outputs (JSON + markdown), surfaced-name
  history, positions-derived correlation sets (**tickers only — never sizes or cost basis**).

The app reads the private data path from local config; public code never embeds it. The
public deploy runs exclusively on synthetic demo data.

## Rationale
`.gitignore` is advisory — one `git add -f`, a renamed directory, or a file created before
the ignore rule, and real data is in public history permanently. Physical separation makes
the failure mode structurally impossible rather than procedurally discouraged. Defense in
depth remains anyway: gitleaks pre-commit hook, a boundary-first `.gitignore`, and a
no-`git add -A` convention in the public repo.

## Consequences
Real daily outputs are never demo-able directly; the public dashboard ships with synthetic
days instead. Publishing any real (delayed/redacted) output later is a deliberate decision
with its own review, not a default.
