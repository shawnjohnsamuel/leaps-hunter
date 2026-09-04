import Link from "next/link";
import { getAllDays, getDisciplineStats, getLatest, isV2 } from "@/lib/data";
import { Disclaimer, MacroBadge, RegimeBadge, ResultBadge, Stat } from "@/components/ui";
import { SignupForm } from "@/components/signup";

export default function Landing() {
  const days = getAllDays();
  const latest = getLatest();
  const stats = getDisciplineStats(days);

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <section className="mb-16 text-center">
        <h1 className="text-5xl font-black tracking-tight text-zinc-100">
          Take the <span className="text-emerald-400">LEAP</span>
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-lg text-zinc-400">
          A rules-based AI screener hunting rare, asymmetric LEAPS setups in quality
          companies caught in panic — and honest enough to tell you, most days, that the
          right trade is <span className="font-semibold text-zinc-200">no trade</span>.
        </p>
        <div className="mt-8 flex justify-center">
          <SignupForm />
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          One email per market day: the macro read, what got screened out and why, and
          the rare candidate that survives every gate.
        </p>
      </section>

      {latest && isV2(latest) && (
        <section className="mb-12 rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <span className="font-mono text-sm text-zinc-500">{latest.date}</span>
            {latest.macro && <MacroBadge macro={latest.macro} />}
            <ResultBadge result={latest.result} />
          </div>
          {latest.notable_finding && (
            <p className="text-sm leading-relaxed text-zinc-400">{latest.notable_finding}</p>
          )}
          <Link href="/dashboard" className="mt-3 inline-block text-sm font-semibold text-emerald-400 hover:underline">
            See the full record →
          </Link>
        </section>
      )}

      {latest && !isV2(latest) && latest.regime && (
        <section className="mb-12 rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
          <div className="mb-2 flex items-center gap-3">
            <span className="font-mono text-sm text-zinc-500">{latest.date}</span>
            <RegimeBadge verdict={latest.regime.verdict} />
            {latest.report_type === "ZERO_TRADE" && (
              <span className="text-sm font-semibold text-emerald-400">0 trades — discipline held</span>
            )}
          </div>
          <p className="text-sm leading-relaxed text-zinc-400">{latest.regime.reasoning}</p>
          <Link href="/dashboard" className="mt-3 inline-block text-sm font-semibold text-emerald-400 hover:underline">
            See the full record →
          </Link>
        </section>
      )}

      <section className="mb-12 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat value={stats.tradingDays} label="sessions run" />
        <Stat value={stats.candidatesSurfaced} label="trades surfaced" />
        <Stat value={stats.gatesFired} label="gates fired" />
        <Stat value={`${stats.zeroTradeDays}/${stats.tradingDays}`} label="zero-trade days" />
      </section>

      <section className="mb-12 space-y-3 text-sm leading-relaxed text-zinc-400">
        <h2 className="text-xl font-bold text-zinc-100">Why the restraint is the product</h2>
        <p>
          Every session runs a hard gauntlet — a macro throttle, event and quality gates,
          four entry-pattern checks, and an eight-dimension scoring bar — and most names
          die before anything gets priced. A candidate only reaches your inbox by
          surviving all of it, scoring above the bar, and pricing out to a positive
          expected value after real friction.
        </p>
        <p>
          The record so far: {stats.tradingDays} sessions, {stats.candidatesSurfaced} forced
          trades, {stats.gatesFired} gates fired. The methodology, framework versions, and
          every architecture decision are public — this is a working example of disciplined,
          AI-assisted research, not a tip service.
        </p>
      </section>

      <Disclaimer />
    </main>
  );
}
