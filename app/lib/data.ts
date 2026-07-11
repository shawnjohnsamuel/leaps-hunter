import fs from "node:fs";
import path from "node:path";

// The app lives inside the leaps-hunter repo; sanitized artifacts sit one level up.
// Vercel checks out the whole repo, so this resolves at build time there too.
const DATA_DIR = path.join(process.cwd(), "..", "public-data");

export type PublicDaily = {
  schema_version: number;
  kind: "public-daily";
  disclaimer: string;
  date: string;
  report_type: "ZERO_TRADE" | "CANDIDATE" | "DEGRADED" | "HOLIDAY";
  framework_version: string;
  regime: {
    verdict: "RISK-ON" | "NEUTRAL" | "RISK-OFF" | "STRESSED";
    confidence: string;
    reasoning: string;
    effective_threshold: number;
  } | null;
  rotation_watch: { summary: string; confidence: string } | null;
  thesis: { name: string; status: string } | null;
  screened: { total: number; gates: Record<string, number> };
  candidates: { ticker: string; score: number; tier: string; one_line: string | null }[];
  watch_only: string[];
  nearest_miss: { ticker: string | null; gate: string } | null;
  degraded: boolean;
};

export function getAllDays(): PublicDaily[] {
  const dir = path.join(DATA_DIR, "daily");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .reverse()
    .map((f) => JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")) as PublicDaily);
}

export function getLatest(): PublicDaily | null {
  const p = path.join(DATA_DIR, "latest.json");
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf8")) as PublicDaily;
}

export type DisciplineStats = {
  sessions: number;
  tradingDays: number;
  candidatesSurfaced: number;
  zeroTradeDays: number;
  gatesFired: number;
  topGates: [string, number][];
};

export function getDisciplineStats(days: PublicDaily[]): DisciplineStats {
  const tradingDays = days.filter((d) => d.report_type !== "HOLIDAY");
  const gates: Record<string, number> = {};
  let gatesFired = 0;
  for (const d of tradingDays) {
    for (const [k, v] of Object.entries(d.screened?.gates ?? {})) {
      if (k === "scored below threshold") continue;
      gates[k] = (gates[k] ?? 0) + v;
      gatesFired += v;
    }
  }
  return {
    sessions: days.length,
    tradingDays: tradingDays.length,
    candidatesSurfaced: tradingDays.reduce((n, d) => n + d.candidates.length, 0),
    zeroTradeDays: tradingDays.filter((d) => d.report_type === "ZERO_TRADE").length,
    gatesFired,
    topGates: Object.entries(gates).sort((a, b) => b[1] - a[1]).slice(0, 4),
  };
}

export const DISCLAIMER_LONG =
  "Take the LEAP publishes the output of a rules-based AI research system. It is NOT " +
  "financial advice, and nothing here creates an advisory or client relationship. The " +
  "system can be wrong — often, and confidently. Signals are hypothetical research " +
  "output, not recommendations to buy or sell any security. Options are leveraged " +
  "instruments that can lose 100% of the premium paid. Hypothetical performance does " +
  "not reflect real trading (no slippage, assignment, or taxes) and past results never " +
  "guarantee future returns. Do your own research and consult a licensed professional " +
  "before making any investment decision.";
