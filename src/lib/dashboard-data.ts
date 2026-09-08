// dashboard-data.ts
// -----------------------------------------------------------------------------
// Your old dashboard_data.js declared `const AUDIT_LOG = [...]` and
// `const SUMMARY = {...}` as GLOBAL variables, loaded via a plain
// <script src="dashboard_data.js"> tag — that pattern doesn't work in
// Next.js (there's no global `window` during server rendering, and nothing
// would import those globals anyway). This file is the direct replacement:
// same two constants, now as proper `export`s with types attached.
//
// WHAT TO DO: open your existing dashboard_data.js, copy the array/object
// literals for AUDIT_LOG and SUMMARY, and paste them in below in place of
// the placeholder empty array/object. Everything else (the type imports,
// the export statements) can stay as-is.

import type { AuditLogEntry, DashboardSummary } from "@/components/dashboard";

// TODO: paste your real AUDIT_LOG array from dashboard_data.js here.
// TypeScript will flag any entry that's missing a field or has the wrong
// type — that's a feature, not a hurdle, it catches data-shape drift early.
export const AUDIT_LOG: AuditLogEntry[] = [];

// TODO: paste your real SUMMARY object from dashboard_data.js here.
export const SUMMARY: DashboardSummary = {
  total_amount_at_risk: 0,
  total_gross_recovered: 0,
  total_net_recovered: 0,
  events_acted_on: 0,
  events_written_off_by_stopping_rules: 0,
  win_rate_pct_of_acted_on: 0,
};
