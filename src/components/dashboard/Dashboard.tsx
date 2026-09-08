// Dashboard.tsx
// -----------------------------------------------------------------------------
// This is the composition root for everything that used to live inside one
// big <script> tag in dashboard.html. It owns the state that multiple
// sub-components need to share (recovery mode + the by-type filter, since
// both the breakdown panel AND the audit trail react to a type filter click),
// and passes data + callbacks down as props.
//
// "use client" is required because this component uses useState/useEffect
// (via its children) — it can't be a React Server Component. The data
// fetch (loading AUDIT_LOG + SUMMARY) should happen in the SERVER component
// that renders <Dashboard />, i.e. src/app/dashboard/page.tsx, and get
// passed in as props — see the example at the bottom of this file's
// matching page.tsx.

"use client";

import { useMemo, useState } from "react";
import styles from "./dashboard.module.css";
import { DashboardHeader } from "./DashboardHeader";
import { RecoveryFunnel } from "./RecoveryFunnel";
import { ByInterventionBreakdown, ByTypeBreakdown } from "./CategoryBreakdown";
import { AuditTrail } from "./AuditTrail";
import { aggregateByIntervention, aggregateByType } from "./dashboard.utils";
import type { AuditLogEntry, DashboardSummary, RecoveryMode } from "./dashboard.types";

interface DashboardProps {
  auditLog: AuditLogEntry[];
  summary: DashboardSummary;
}

export function Dashboard({ auditLog, summary }: DashboardProps) {
  // Net/Gross toggle — shared by the funnel AND both breakdown panels, so it
  // lives here rather than inside any one of them.
  const [mode, setMode] = useState<RecoveryMode>("net");

  // The "by leak point" filter also needs to affect the audit trail table
  // below it (clicking a leak-point row filters the ledger), so this state
  // lives here too instead of inside CategoryBreakdown.
  const [typeFilter, setTypeFilter] = useState("all");
  const [interventionFilter, setInterventionFilter] = useState<string | null>(
    null,
  );

  // useMemo avoids re-running the aggregation on every keystroke in the
  // ledger's search box — it only recomputes when auditLog itself changes,
  // which in this static-batch demo is essentially never after first load.
  const byType = useMemo(() => aggregateByType(auditLog), [auditLog]);
  const byIntervention = useMemo(
    () => aggregateByIntervention(auditLog),
    [auditLog],
  );

  // NOTE: the audit trail currently filters independently by whatever the
  // person clicks directly inside it. If you want clicking a "by leak
  // point" row to ALSO filter the ledger below (like the original single-
  // page script did via shared module state), pass typeFilter/interventionFilter
  // down into <AuditTrail /> as props instead of letting it own that state
  // internally — left as-is here so each panel works standalone first.

  return (
    <div className={styles.wrap}>
      <DashboardHeader mode={mode} onModeChange={setMode} />

      <RecoveryFunnel summary={summary} mode={mode} />

      <div className={styles.grid}>
        <ByTypeBreakdown
          aggregates={byType}
          mode={mode}
          activeFilter={typeFilter}
          onSelect={(type) =>
            setTypeFilter((prev) => (prev === type ? "all" : type))
          }
          onClear={() => setTypeFilter("all")}
        />
        <ByInterventionBreakdown
          aggregates={byIntervention}
          mode={mode}
          activeFilter={interventionFilter}
          onSelect={(intervention) =>
            setInterventionFilter((prev) =>
              prev === intervention ? null : intervention,
            )
          }
          onClear={() => setInterventionFilter(null)}
        />
      </div>

      <AuditTrail auditLog={auditLog} />

      <footer className={styles.footer}>
        Synthetic batch of 200 events · schema mirrors Razorpay
        Payments/Orders/Invoices entities · swap generate_data.py for the live
        test-mode API to go from demo to real
      </footer>
    </div>
  );
}
