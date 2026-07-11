import { getAllDays, getDisciplineStats } from "@/lib/data";
import { Disclaimer, ReportCard, Stat } from "@/components/ui";

export const metadata = { title: "Dashboard — Take the LEAP" };

export default function Dashboard() {
  const days = getAllDays();
  const stats = getDisciplineStats(days);

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="mb-8 text-3xl font-black tracking-tight text-zinc-100">The record</h1>

      <section className="mb-10 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat value={stats.tradingDays} label="sessions run" />
        <Stat value={stats.candidatesSurfaced} label="trades surfaced" />
        <Stat value={stats.gatesFired} label="gates fired" />
        <Stat value={`${stats.zeroTradeDays}/${stats.tradingDays}`} label="zero-trade days" />
      </section>

      <section className="mb-10 rounded-xl border border-zinc-800 bg-zinc-900/60 p-6">
        <h2 className="mb-2 text-lg font-bold text-zinc-100">The LEAP Ledger</h2>
        {stats.candidatesSurfaced === 0 ? (
          <div className="text-sm leading-relaxed text-zinc-400">
            <p>
              No hypothetical positions yet — every name screened so far died at a gate
              before deployment. That is the system working:
            </p>
            <ul className="mt-3 space-y-1">
              {stats.topGates.map(([gate, n]) => (
                <li key={gate} className="flex justify-between border-b border-zinc-800/60 pb-1">
                  <span className="capitalize">{gate}</span>
                  <span className="font-mono text-zinc-500">×{n}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-zinc-500">
              When a candidate scores 75+, a hypothetical $10,000 entry (charged at the
              ask) appears here, marked daily against the same $10,000 in SPY.
            </p>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">Equity curve coming soon.</p>
        )}
      </section>

      <section className="space-y-4">
        {days.map((d) => (
          <ReportCard key={d.date} day={d} />
        ))}
      </section>

      <div className="mt-10">
        <Disclaimer />
      </div>
    </main>
  );
}
