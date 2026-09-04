# LEAPS Hunter · Take the LEAP

> ✅ **Migrated to framework v7.0** (2026-09-03 to 2026-09-04, all 7 phases complete). v7
> replaces v6 wholesale — mechanism taxonomy instead of named theses, arithmetic macro gates,
> an executable option model, and robust fractional Kelly sizing. The public plane (this
> section, the dashboard, the email) now runs on v7's schema; the 5 real v6.1 days stay
> published as a static archive, rendered in legacy mode. See the
> [migration plan](docs/v7-migration-plan.md) for the full build record.


A disciplined, AI-assisted options-screening system that hunts for deep-ITM, long-dated
LEAPS calls on large-cap quality names caught in **panic-driven (not fundamental)
selloffs** — and, on most days, correctly recommends **nothing at all**. Its public face
is **Take the LEAP**: a daily email verdict plus a dashboard where the restraint itself
is the product.

> Built with [Claude Code](https://claude.com/claude-code) as a working example of
> AI-assisted development. The commit history — audit → synthesis → production lessons →
> spec amendments — is part of the point.

## The record so far

Three production runs, zero forced trades, three *different* hard gates each catching a
would-be trade:

| Run | Nearest miss | Killed by | What changed |
|---|---|---|---|
| 2026-07-08 | INTU (~74 informal) | portfolio-correlation gate | Gate was too strict — amended same day ([ADR 0006](docs/decisions/0006-crowding-counts-options-only.md), spec → v6.1) |
| 2026-07-09 | INTU again | liquidity floors, re-verified intraday | "Closing spreads over-reject" hypothesis tested and **refuted** — rejection is structural |
| 2026-07-10 | TRI (~76–78 informal) | option duration (no LEAPS past Jan-2027) | Best raw setup yet; un-ownable in the mandated structure |

## The core idea

- Asymmetry comes from mispricing, not momentum — buy panic, never euphoria.
- Multiple independent catalysts beat any single dependency.
- Survivability beats maximum leverage — structure emerges from the net-return and
  portfolio-risk model, bounded by delta guardrails ([ADR 0007](docs/decisions/0007-delta-policy-supersedes-hard-floor.md)).
- Macro acts as a **veto, never as points** ([ADR 0001](docs/decisions/0001-macro-as-veto-not-additive-points.md)).
- **The modal correct output is zero trades**, reported in full — never silence.

## Architecture

```
daily screener run (Claude session — desktop or cloud — with read-only brokerage access)
  ├─ live chains/Greeks/positions: Robinhood MCP (sole live source, ADR 0004)
  ├─ historical contract OHLC: Massive Market Data     ├─ macro/news: web search
  ▼
private report → leaps-hunter-data (private repo: full detail, positions-derived data)
  ▼
scripts/sanitize.py — strict ALLOWLIST (ADR 0002 + CI leak tripwire)
  ▼
public-data/daily/*.json (this repo)
  ├─ triggers .github/workflows/broadcast.yml → Resend email to subscribers
  └─ app/ — Next.js "Take the LEAP": landing + signup, dashboard, LEAP Ledger
```

## Repository guide

| Path | What it is |
|---|---|
| [framework/v7.md](framework/v7.md) | **The governing spec (v7.0)** — mechanisms, macro gates, entry patterns, option model, Kelly sizing |
| [framework/v6.md](framework/v6.md) | The previous production spec (v6.1), superseded — kept as design history |
| [docs/annex-read-only.md](docs/annex-read-only.md) | Operating annex A — the enumerated read-only tool contract (binding) |
| [framework/v4.md](framework/v4.md) / [v5.md](framework/v5.md) | The two predecessor frameworks, preserved as design history |
| [docs/audit-v4-vs-v5.md](docs/audit-v4-vs-v5.md) | The head-to-head audit that justified v6 |
| [docs/decisions/](docs/decisions/) | ADRs — including two written *after* production runs changed the rules |
| [docs/storage-schema.md](docs/storage-schema.md) | v6.1 data contracts, superseded — kept as reference for the 5 archived legacy days |
| [scripts/](scripts/) | Sanitizer v2 (allowlist + leak tripwires, `scripts/tests/` for the leak-test suite) and email renderer, both targeting v7's schema |
| [public-data/](public-data/) | Sanitized daily artifacts — the only screener output that exists publicly. Currently the 5 real v6.1 archive days; no real v7 day has been published yet |
| [app/](app/) | Take the LEAP — Next.js site (Vercel). Renders v6.1 and v7 days side by side ("legacy-mode rendering") |
| [data-demo/](data-demo/) | Synthetic sample days (fictional tickers) covering every report type, both v6.1 and v7 shapes |
| [.claude/skills/](.claude/skills/) | `weekly-review`, `daily-screen`, `bench-check` (Phase 5), and `macro-refresh` (Phase 6, desktop-only — see [ADR 0014](docs/decisions/0014-macro-fetch-desktop-only.md)) |
| [engine/](engine/) | The v7 deterministic core — config, sources, macro, patterns, gates, optmodel, sizing, portfolio, scoring. 164 tests, zero third-party dependencies |
| [docs/storage-schema-v7.md](docs/storage-schema-v7.md) | The v7 schema — both `state/*.json` (private repo) and `public-data/*.json` (Phase 7) |

## Safety and boundaries

- **Read-only by construction.** The framework enumerates allowed brokerage tools and
  denylists order placement/review/cancellation *by name* (v6 §2). All actual trades are
  placed manually by a human.
- **Two-plane data design** ([ADR 0002](docs/decisions/0002-two-repo-public-private-boundary.md)):
  real outputs live in a separate private repo; this repo receives only allowlist-sanitized
  artifacts, with a held-ticker tripwire at generation time and a CI leak-check on every push.
- **Serious disclaimers, structurally:** every email and page carries it — rules-based AI
  research output, **not financial advice**, options can lose 100% of premium, DYOR.

## License

TBD.
