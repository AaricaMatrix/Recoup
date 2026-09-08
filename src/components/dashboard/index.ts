// index.ts (dashboard/)
// -----------------------------------------------------------------------------
// Lets src/app/dashboard/page.tsx write:
//   import { Dashboard } from "@/components/dashboard";
// Only the composition root and the types/utils you'd need outside this
// folder are re-exported — the individual sub-components (DashboardHeader,
// RecoveryFunnel, etc.) are implementation details of <Dashboard />, so they
// stay accessible via their own file paths if you ever need to import one
// directly, but aren't cluttered into this barrel.

export { Dashboard } from "./Dashboard";
export type {
  AuditLogEntry,
  DashboardSummary,
  RecoveryMode,
  RiskType,
} from "./dashboard.types";
