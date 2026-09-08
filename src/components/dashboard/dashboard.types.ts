// dashboard.types.ts
// -----------------------------------------------------------------------------
// Every type here mirrors a field that already exists in your dashboard_data.js
// AUDIT_LOG / SUMMARY objects. I didn't invent new fields — I just gave the
// existing shape names, so TypeScript can catch typos and missing fields
// anywhere you use this data (autocomplete + compile-time checks instead of
// silent `undefined` bugs at runtime).

// The three leak-point categories your funnel + "by leak point" panel group by.
// Using a union type (instead of `string`) means a typo like "payment_faliure"
// is caught at compile time instead of silently rendering as an unlabeled row.
export type RiskType =
  | "payment_failure"
  | "checkout_abandonment"
  | "overdue_invoice";

// One row of the audit trail / ledger table. Field names match AUDIT_LOG
// entries in dashboard_data.js exactly, so you can pass that JSON straight in
// without any renaming step.
export interface AuditLogEntry {
  event_id: string; // unique id shown in the "Event" column
  type: RiskType; // which leak point this event belongs to
  root_cause: string; // e.g. "card_expired" — shown in "Root cause" column
  intervention: string; // e.g. "send_payment_link" — the action taken
  intervention_reasoning: string; // why that action was chosen (shown in "Reasoning")
  diagnosis_reasoning: string; // longer explanation shown only in the expanded row
  amount_at_risk: number; // ₹ amount that was at risk for this event
  gross_amount_recovered: number; // ₹ recovered before subtracting intervention cost
  net_amount_recovered: number; // ₹ recovered after subtracting intervention cost
  intervention_cost: number; // ₹ cost of running the intervention (e.g. discount given)
  outcome_recovered: boolean; // true if the event ended in a recovery
  stopping_rule_applied: boolean; // true if the agent chose NOT to act (held, not a miss)
  timestamp: string; // ISO timestamp string, e.g. "2026-05-01T12:00:00Z"
}

// The top-line summary numbers shown in the funnel (revenue at risk / acted on
// / recovered) and the two tape-stub stats. Matches your SUMMARY object.
export interface DashboardSummary {
  total_amount_at_risk: number;
  total_gross_recovered: number;
  total_net_recovered: number;
  events_acted_on: number;
  events_written_off_by_stopping_rules: number;
  win_rate_pct_of_acted_on: number;
}

// Net vs Gross toggle — kept as a union instead of boolean so the code reads
// as "mode === 'net'" everywhere, matching the data-mode attribute in your
// original HTML toggle buttons.
export type RecoveryMode = "net" | "gross";

// Shape produced by aggregating AUDIT_LOG by `type` — used to render the
// "By leak point" panel and its progress bars.
export interface TypeAggregate {
  count: number;
  at_risk: number;
  gross: number;
  net: number;
}

// Shape produced by aggregating AUDIT_LOG by `intervention` — used to render
// the "By intervention" panel (wins / attempts / win rate).
export interface InterventionAggregate {
  attempts: number;
  wins: number;
  gross: number;
  net: number;
}
