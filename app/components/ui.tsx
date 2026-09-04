import { DISCLAIMER_LONG, isV2, type Mechanism, type PublicDaily } from "@/lib/data";

// ---------------------------------------------------------------------------
// Legacy v6.1 (schema_version 1) components — kept verbatim for the 5 archived
// real days ("legacy mode", migration plan Phase 7). Never used for new days.
// ---------------------------------------------------------------------------
const verdictStyles: Record<string, string> = {
  "RISK-ON": "bg-emerald-500/15 text-emerald-400 border-emerald-500/40",
  NEUTRAL: "bg-amber-500/15 text-amber-400 border-amber-500/40",
  "RISK-OFF": "bg-orange-500/15 text-orange-400 border-orange-500/40",
  STRESSED: "bg-red-500/15 text-red-400 border-red-500/40",
};

export function RegimeBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className={`inline-block rounded-full border px-3 py-0.5 text-sm font-semibold tracking-wide ${
        verdictStyles[verdict] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/40"
      }`}
    >
      {verdict}
    </span>
  );
}

// ---------------------------------------------------------------------------
// v7 (schema_version 2) components. No regime verdict — the macro layer is a
// gate + throttle (R 0-4, RESTRICTED or not), never a qualitative "mood."
// ---------------------------------------------------------------------------
const MECHANISM_LABELS: Record<Mechanism, string> = {
  M1: "bottleneck ownership",
  M2: "AI demand multiplier",
  M3: "narrative reversal",
  M4: "sanctioned secondary",
};

const MECHANISM_STYLES: Record<Mechanism, string> = {
  M1: "bg-cyan-500/15 text-cyan-400 border-cyan-500/40",
  M2: "bg-violet-500/15 text-violet-400 border-violet-500/40",
  M3: "bg-fuchsia-500/15 text-fuchsia-400 border-fuchsia-500/40",
  M4: "bg-lime-500/15 text-lime-400 border-lime-500/40",
};

export function MechanismTag({ mechanism }: { mechanism: Mechanism | null }) {
  if (!mechanism) return null;
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${MECHANISM_STYLES[mechanism]}`}
      title={MECHANISM_LABELS[mechanism]}
    >
      {mechanism} · {MECHANISM_LABELS[mechanism]}
    </span>
  );
}

export function MacroBadge({ macro }: { macro: { R: number; restricted: boolean; score_threshold: number } }) {
  return (
    <span
      className={`inline-block rounded-full border px-3 py-0.5 text-sm font-semibold tracking-wide ${
        macro.restricted
          ? "bg-orange-500/15 text-orange-400 border-orange-500/40"
          : "bg-emerald-500/15 text-emerald-400 border-emerald-500/40"
      }`}
      title={`Qualifying score threshold: ${macro.score_threshold}/100`}
    >
      R={macro.R} {macro.restricted ? "· RESTRICTED" : "· normal"}
    </span>
  );
}

export function ResultBadge({ result }: { result: PublicDailyV2Result }) {
  const styles: Record<PublicDailyV2Result, string> = {
    NO_TRADE: "text-emerald-400",
    CANDIDATE: "text-sky-400",
    HOLIDAY: "text-zinc-400",
    DATA_INSUFFICIENT: "text-amber-400",
  };
  const labels: Record<PublicDailyV2Result, string> = {
    NO_TRADE: "✅ 0 trades — discipline held",
    CANDIDATE: "CANDIDATE",
    HOLIDAY: "market closed",
    DATA_INSUFFICIENT: "⚠️ data insufficient",
  };
  return <span className={`text-sm font-semibold ${styles[result]}`}>{labels[result]}</span>;
}

type PublicDailyV2Result = "NO_TRADE" | "CANDIDATE" | "HOLIDAY" | "DATA_INSUFFICIENT";

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------
export function Disclaimer() {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm leading-relaxed text-amber-200/90">
      <p className="mb-1 font-bold uppercase tracking-wider text-amber-400">
        ⚠️ Not financial advice — read this
      </p>
      {DISCLAIMER_LONG}
    </div>
  );
}

export function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 text-center">
      <div className="text-3xl font-bold text-zinc-100">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wider text-zinc-500">{label}</div>
    </div>
  );
}

export function ReportCard({ day }: { day: PublicDaily }) {
  if (isV2(day)) {
    return (
      <article className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
        <header className="mb-3 flex flex-wrap items-center gap-3">
          <h3 className="font-mono text-lg font-semibold text-zinc-100">{day.date}</h3>
          {day.macro && <MacroBadge macro={day.macro} />}
          <ResultBadge result={day.result} />
        </header>

        {day.notable_finding && (
          <p className="mb-3 text-sm leading-relaxed text-zinc-400">{day.notable_finding}</p>
        )}

        {day.candidates.length > 0 && (
          <ul className="mb-3 space-y-2">
            {day.candidates.map((c) => (
              <li key={c.ticker} className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono font-bold text-sky-300">{c.ticker}</span>
                  <MechanismTag mechanism={c.mechanism} />
                  {c.score && <span className="text-sm text-zinc-300">{c.score}</span>}
                </div>
                {c.one_line && <p className="mt-1 text-sm text-zinc-400">{c.one_line}</p>}
              </li>
            ))}
          </ul>
        )}

        {day.nearest_misses.length > 0 && (
          <ul className="mb-3 space-y-2">
            {day.nearest_misses.map((nm) => (
              <li key={nm.ticker} className="rounded-lg border border-zinc-700/50 bg-zinc-800/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono font-semibold text-zinc-200">{nm.ticker}</span>
                  <MechanismTag mechanism={nm.mechanism} />
                  {nm.score && <span className="text-xs text-zinc-500">{nm.score}</span>}
                </div>
                {nm.note && <p className="mt-1 text-xs text-zinc-500">{nm.note}</p>}
              </li>
            ))}
          </ul>
        )}

        <footer className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
          {day.candidates_examined != null && <span>{day.candidates_examined} names screened</span>}
          {Object.entries(day.gates_summary).map(([g, n]) => (
            <span key={g}>
              {g}: {n}
            </span>
          ))}
        </footer>
      </article>
    );
  }

  // Legacy v6.1 rendering — untouched from the original component.
  const isZero = day.report_type === "ZERO_TRADE";
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="font-mono text-lg font-semibold text-zinc-100">{day.date}</h3>
        {day.regime && <RegimeBadge verdict={day.regime.verdict} />}
        <span
          className={`text-sm font-semibold ${
            isZero ? "text-emerald-400" : day.report_type === "CANDIDATE" ? "text-sky-400" : "text-zinc-400"
          }`}
        >
          {isZero ? "✅ 0 trades — discipline held" : day.report_type}
        </span>
      </header>

      {day.regime && <p className="mb-3 text-sm leading-relaxed text-zinc-400">{day.regime.reasoning}</p>}

      {day.candidates.length > 0 && (
        <ul className="mb-3 space-y-2">
          {day.candidates.map((c) => (
            <li key={c.ticker} className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3">
              <span className="font-mono font-bold text-sky-300">{c.ticker}</span>
              <span className="ml-2 text-sm text-zinc-300">
                {c.score}/100 · {c.tier}
              </span>
              {c.one_line && <p className="mt-1 text-sm text-zinc-400">{c.one_line}</p>}
            </li>
          ))}
        </ul>
      )}

      <footer className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
        <span>{day.screened.total} names screened</span>
        {Object.entries(day.screened.gates).map(([g, n]) => (
          <span key={g}>
            {g}: {n}
          </span>
        ))}
        {day.nearest_miss?.ticker && (
          <span className="text-zinc-400">
            nearest miss: <span className="font-mono">{day.nearest_miss.ticker}</span> ({day.nearest_miss.gate})
          </span>
        )}
      </footer>
    </article>
  );
}
