# LEAPS Hunter

A disciplined, AI-assisted options-screening system that hunts for deep-ITM, long-dated
LEAPS calls on large-cap quality names caught in **panic-driven (not fundamental) selloffs** —
and, on most days, correctly recommends **nothing at all**.

> **Status:** in active development. This repo currently contains the framework's design
> history and the audit that produced v6; the screener skill, storage layer, and dashboard
> land in subsequent commits. Built with [Claude Code](https://claude.com/claude-code) as a
> working example of AI-assisted development — the commit history is part of the point.

## The core idea

Most option screeners optimize for activity. This one optimizes for **restraint**:

- Asymmetry comes from mispricing, not momentum — buy panic, never euphoria.
- Multiple independent catalysts beat any single dependency.
- Survivability (deep ITM, long duration, hard delta floor) beats maximum leverage.
- **The modal correct output is zero trades.** A zero-trade day is a successful run,
  reported in full — not a silent or broken one.

## How it works (architecture at a glance)

```
                       ┌──────────────────────────────┐
  7:30am ET weekdays → │  Daily screener (Claude Code │
  (scheduled task)     │  skill, framework v6)        │
                       └──────────────┬───────────────┘
        Robinhood MCP (read-only) ────┤   live chains, Greeks, OI, spreads,
        Massive Market Data ──────────┤   historical contract OHLC (backtest layer)
        Web search ───────────────────┤   macro regime, fundamentals, news
                                      ▼
                       dated JSON + markdown reports
                       (private data repo — never here)
                                      ▼
                       ┌──────────────────────────────┐
                       │  Dashboard (static React)     │
                       │  regime verdict · scores ·    │
                       │  history · quick-eval panel   │
                       └──────────────────────────────┘
```

Key design decisions are recorded as short ADRs in [docs/decisions/](docs/decisions/),
including why macro acts as a **veto, not additive points**, and why the public/private
boundary is **two repos, not a .gitignore**.

## Design history

The framework is on its sixth major revision. Two independently developed predecessors —
**v4** (developed with Claude, production-tested) and **v5** (developed with ChatGPT,
never run live) — were audited head-to-head before synthesis:

- [framework/v4.md](framework/v4.md) — the production incumbent
- [framework/v5.md](framework/v5.md) — the independent challenger
- [docs/audit-v4-vs-v5.md](docs/audit-v4-vs-v5.md) — the full comparative audit and verdict
- [framework/CHANGELOG.md](framework/CHANGELOG.md) — version lineage

## Safety and boundaries

- **Read-only by construction.** The screener may only call read-only brokerage tools
  (quotes, chains, positions). Order placement, review, and cancellation tools are
  denylisted by name in the framework spec itself. All actual trades are placed manually
  by a human.
- **No live data in this repo — ever.** Real daily outputs, positions, and anything
  account-adjacent live in a separate private repo. This repo carries only methodology,
  code, and synthetic demo data. A gitleaks pre-commit hook guards the history.
- **Not financial advice.** This is a personal research tool and engineering showcase.

## License

TBD.
