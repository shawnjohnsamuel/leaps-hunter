# LEAPS Hunter · Take the LEAP

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
- Survivability (deep ITM, ≥60Δ hard floor, long duration) beats maximum leverage.
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
| [framework/v6.md](framework/v6.md) | The operating spec (v6.1) — gates, scoring bands, tool contract |
| [framework/v4.md](framework/v4.md) / [v5.md](framework/v5.md) | The two predecessor frameworks, preserved as design history |
| [docs/audit-v4-vs-v5.md](docs/audit-v4-vs-v5.md) | The head-to-head audit that justified v6 |
| [docs/decisions/](docs/decisions/) | ADRs — including two written *after* production runs changed the rules |
| [docs/storage-schema.md](docs/storage-schema.md) | Private + public data contracts |
| [scripts/](scripts/) | Sanitizer (allowlist + leak tripwires) and email renderer |
| [public-data/](public-data/) | Sanitized daily artifacts — the only screener output that exists publicly |
| [app/](app/) | Take the LEAP — Next.js site (Vercel) |
| [data-demo/](data-demo/) | Synthetic sample days (fictional tickers) covering every report type |
| [.claude/skills/](.claude/skills/) | `daily-screener` (runs v6 end-to-end) and `quick-eval` (gate-check) |

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
