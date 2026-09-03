# ADR 0010: The model sources evidence; deterministic code decides

**Status:** accepted (2026-09-03)

## Context
v6 was a rubric a language model followed end to end: it read bands, judged which applied, and
wrote a score. v7 §6, §10, §12, §14 and §15 are not rubrics. They are arithmetic on named
inputs — percentile thresholds, drawdown windows, Black-Scholes repricing with a stressed exit,
a 10,000-draw Kelly optimization, a covariance matrix and an expected-shortfall test.

Asking a model to perform that in prose invites three failures at once: silent arithmetic
error, unreproducible results, and a per-run token cost proportional to the work.

## Decision
Implement §6, §10, §12, §13.3, §14 and §15 as a standard-library Python package (`engine/`).
**§20's YAML config is the only place any threshold exists**; both the spec prose and the code
read it. The model's remaining work is what only it can do:

- mapping evidence to a §5 mechanism, with sources
- judging the §8 AI-substitution gate
- scoring the qualitative dimensions of §11
- writing the report with §2's `[FACT]` / `[ASSUMPTION]` / `[RULE]` labels intact

## Rationale
Correctness and cost point the same way. A deterministic gate produces the same verdict from
the same inputs, which is the precondition for §17's walk-forward calibration — a rule that
cannot be replayed cannot be validated. Single-sourcing thresholds in §20 is what makes §21's
version control enforceable rather than aspirational: a threshold change becomes a code change
with a diff, a rationale and a date.

Standard library only, no numpy: the engine then runs identically on the laptop and in the
cloud sandbox, and 10,000 Kelly draws are fast enough in pure Python.

## Consequences
- The spec and the engine must be kept in sync deliberately. The release script (Phase 6) copies
  a versioned pair into the private data repo, so each run records the engine version that
  produced it.
- Every deterministic output is reproducible from the run's recorded inputs, which is what
  §17's backtest and §21's audit trail both require.
- A threshold that appears in code but not in §20's YAML is a defect, not a shortcut.
