import { DISCLAIMER_LONG, type PublicDaily } from "@/lib/data";

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
