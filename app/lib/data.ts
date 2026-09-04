import fs from "node:fs";
import path from "node:path";

// The app lives inside the leaps-hunter repo; sanitized artifacts sit one level up.
// Vercel checks out the whole repo, so this resolves at build time there too.
const DATA_DIR = path.join(process.cwd(), "..", "public-data");

// ---------------------------------------------------------------------------
// Legacy v6.1 shape (schema_version 1). Five real days were published under this
// schema before the v7 migration; they are static, already-sanitized files that
// will never be re-generated. Kept verbatim so they keep rendering ("legacy mode",
// migration plan Phase 7) rather than being reshaped to fit v7's schema.
// ---------------------------------------------------------------------------
export type PublicDailyV1 = {
  schema_version: 1;
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

// ---------------------------------------------------------------------------
// v7 shape (schema_version 2). No regime verdict, no thesis, no tiers — v7 has
// no equivalent concepts (mechanism taxonomy + macro hard-gates/R-throttle
// replace them entirely). See docs/storage-schema-v7.md and ADR 0002/0014.
// ---------------------------------------------------------------------------
export type Mechanism = "M1" | "M2" | "M3" | "M4";

export type PublicDailyV2 = {
  schema_version: 2;
  kind: "public-daily";
  disclaimer: string;
  date: string;
  framework_version: string;
  result: "NO_TRADE" | "CANDIDATE" | "HOLIDAY" | "DATA_INSUFFICIENT";
  macro: {
    R: number;
    restricted: boolean;
    score_threshold: number;
    hard_gate_active: boolean;
    hard_gate_names: string[];
  } | null;
  candidates_examined: number | null;
  candidates_clearing_gates: number | null;
  candidates: { ticker: string; mechanism: Mechanism | null; score: string | null; one_line: string | null }[];
  nearest_misses: { ticker: string; mechanism: Mechanism | null; category: string; score: string | null; note: string | null }[];
  gates_summary: Record<string, number>;
  notable_finding: string | null;
};

export type PublicDaily = PublicDailyV1 | PublicDailyV2;

export function isV2(d: PublicDaily): d is PublicDailyV2 {
  return d.schema_version === 2;
}

function readDay(file: string): PublicDaily {
  return JSON.parse(fs.readFileSync(file, "utf8")) as PublicDaily;
}

export function getAllDays(): PublicDaily[] {
  const dir = path.join(DATA_DIR, "daily");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .reverse()
    .map((f) => readDay(path.join(dir, f)));
}

export function getLatest(): PublicDaily | null {
  const p = path.join(DATA_DIR, "latest.json");
  if (!fs.existsSync(p)) return null;
  return readDay(p);
}

export type DisciplineStats = {
  sessions: number;
  tradingDays: number;
  candidatesSurfaced: number;
  zeroTradeDays: number;
  gatesFired: number;
  topGates: [string, number][];
};

const NON_GATE_BUCKETS = new Set(["scored below threshold", "cleared"]);

export function getDisciplineStats(days: PublicDaily[]): DisciplineStats {
  const tradingDays = days.filter((d) =>
    isV2(d) ? d.result !== "HOLIDAY" : d.report_type !== "HOLIDAY"
  );
  const gates: Record<string, number> = {};
  let gatesFired = 0;
  for (const d of tradingDays) {
    const bucket = isV2(d) ? d.gates_summary : d.screened?.gates ?? {};
    for (const [k, v] of Object.entries(bucket)) {
      if (NON_GATE_BUCKETS.has(k)) continue;
      gates[k] = (gates[k] ?? 0) + v;
      gatesFired += v;
    }
  }
  return {
    sessions: days.length,
    tradingDays: tradingDays.length,
    candidatesSurfaced: tradingDays.reduce((n, d) => n + d.candidates.length, 0),
    zeroTradeDays: tradingDays.filter((d) => (isV2(d) ? d.result === "NO_TRADE" : d.report_type === "ZERO_TRADE")).length,
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
