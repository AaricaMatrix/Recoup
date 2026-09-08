// dashboard.utils.ts
// -----------------------------------------------------------------------------
// These are the pure, non-visual functions your original <script> block did
// inline (inr formatting + the two reduce/forEach aggregations). Pulling them
// out here means: (1) they're unit-testable on their own with Vitest/Jest,
// no DOM needed, and (2) both server and client components can import them
// without pulling in any React code.

import type {
  AuditLogEntry,
  DashboardSummary,
  InterventionAggregate,
  RecoveryMode,
  TypeAggregate,
} from "./dashboard.types";

// Formats a number as Indian-Rupee currency the same way your original
// `inr = n => '₹' + Math.round(n).toLocaleString('en-IN')` did.
// Kept as a named export (not inline) so it can be reused by any component,
// not just the ones that happen to define it locally.
export function formatINR(amount: number): string {
  // Math.round first — matches your original behaviour of never showing
  // decimals, even mid-animation during the count-up effect.
  return "₹" + Math.round(amount).toLocaleString("en-IN");
}

// Human-readable labels for each RiskType — matches the `typeLabels` object
// in your original script exactly (same keys, same copy).
export const TYPE_LABELS: Record<string, string> = {
  payment_failure: "Payment failures",
  checkout_abandonment: "Checkout abandonment",
  overdue_invoice: "Overdue invoices",
};

// Picks gross vs net recovered amount from an aggregate depending on the
// current toggle mode. Centralising this avoids the `mode === 'net' ? a : b`
// ternary being repeated in three different render functions like it was
// in the original script.
export function pickByMode(
  mode: RecoveryMode,
  net: number,
  gross: number,
): number {
  return mode === "net" ? net : gross;
}

// Rebuilds byTypeAgg from the original script: groups every audit-log entry
// by its `type` field and sums at_risk / gross / net for each group.
// Runs once per render — AUDIT_LOG is small (≤200 rows per your footer note),
// so there's no need for memoisation unless the dataset grows a lot.
export function aggregateByType(
  auditLog: AuditLogEntry[],
): Record<string, TypeAggregate> {
  const result: Record<string, TypeAggregate> = {};
  for (const entry of auditLog) {
    // `??=` creates the bucket the first time we see this type, exactly like
    // `(byTypeAgg[e.type] ??= {...})` did in the original script.
    result[entry.type] ??= { count: 0, at_risk: 0, gross: 0, net: 0 };
    const bucket = result[entry.type];
    bucket.count += 1;
    bucket.at_risk += entry.amount_at_risk;
    bucket.gross += entry.gross_amount_recovered;
    bucket.net += entry.net_amount_recovered;
  }
  return result;
}

// Rebuilds byIntAgg from the original script: groups every audit-log entry
// that WASN'T held by a stopping rule by its `intervention` field, and counts
// attempts vs wins.
export function aggregateByIntervention(
  auditLog: AuditLogEntry[],
): Record<string, InterventionAggregate> {
  const result: Record<string, InterventionAggregate> = {};
  for (const entry of auditLog) {
    // Events the agent chose not to act on are excluded — they were never an
    // "attempt", so counting them would understate the real win rate.
    if (entry.stopping_rule_applied) continue;
    result[entry.intervention] ??= {
      attempts: 0,
      wins: 0,
      gross: 0,
      net: 0,
    };
    const bucket = result[entry.intervention];
    bucket.attempts += 1;
    if (entry.outcome_recovered) {
      bucket.wins += 1;
      bucket.gross += entry.gross_amount_recovered;
      bucket.net += entry.net_amount_recovered;
    }
  }
  return result;
}

// Filters + sorts the ledger rows exactly like renderLedger() did:
// type filter -> intervention filter -> text search -> sort by amount,
// then caps the result at 80 rows so the scrollbox doesn't render an
// unbounded list.
export function filterAndSortLedger(
  auditLog: AuditLogEntry[],
  opts: {
    typeFilter: string; // 'all' means no filter, matches original default
    interventionFilter: string | null;
    query: string; // already lower-cased by the caller
    sortDescending: boolean;
  },
): AuditLogEntry[] {
  const { typeFilter, interventionFilter, query, sortDescending } = opts;

  const filtered = auditLog.filter((entry) => {
    const matchesType = typeFilter === "all" || entry.type === typeFilter;
    const matchesIntervention =
      !interventionFilter || entry.intervention === interventionFilter;
    const matchesQuery =
      !query ||
      entry.event_id.toLowerCase().includes(query) ||
      entry.root_cause.toLowerCase().includes(query);
    return matchesType && matchesIntervention && matchesQuery;
  });

  // Slice a COPY before sorting (`.slice()` with no args) so we never mutate
  // the array the caller passed in — same defensive habit your original
  // script used.
  const sorted = filtered
    .slice()
    .sort((a, b) =>
      sortDescending
        ? b.amount_at_risk - a.amount_at_risk
        : a.amount_at_risk - b.amount_at_risk,
    );

  // Hard cap at 80 rows, matching the original `.slice(0, 80)`.
  return sorted.slice(0, 80);
}

// Builds the "N% of at-risk" label shown under the recovered stamp.
// Guards against division by zero (total_amount_at_risk === 0) which the
// original inline script did not — an empty demo dataset would have shown
// "NaN% of at-risk" without this check.
export function recoveredPercentLabel(
  summary: DashboardSummary,
  mode: RecoveryMode,
): string {
  const shown = pickByMode(
    mode,
    summary.total_net_recovered,
    summary.total_gross_recovered,
  );
  const prefix = mode === "net" ? "Net recovered · " : "Gross recovered · ";
  if (summary.total_amount_at_risk === 0) return prefix + "0% of at-risk";
  const pct = Math.round((100 * shown) / summary.total_amount_at_risk);
  return `${prefix}${pct}% of at-risk`;
}
