// AuditTrail.tsx
// -----------------------------------------------------------------------------
// Ports the `.panel.ledger` block and renderLedger() from the original inline
// script. The biggest behavioural change from the original: instead of
// removing/re-inserting a sibling <tr class="expand"> via raw DOM calls, the
// currently-open row id is just React state, and the expanded detail row is
// rendered conditionally right after its parent row — same visual result,
// no manual DOM surgery.

import { useState } from "react";
import styles from "./dashboard.module.css";
import { FilterPill, SearchInput, Tag, outcomeTone } from "../ui";
import { filterAndSortLedger, formatINR, TYPE_LABELS } from "./dashboard.utils";
import type { AuditLogEntry } from "./dashboard.types";

interface AuditTrailProps {
  auditLog: AuditLogEntry[];
}

export function AuditTrail({ auditLog }: AuditTrailProps) {
  // All five pieces of ledger UI state, matching the original's module-level
  // `let typeFilter='all', intFilter=null, query='', sortDesc=true` plus
  // `let openRow = null` — just as component state instead of closures.
  const [typeFilter, setTypeFilter] = useState("all");
  const [interventionFilter, setInterventionFilter] = useState<string | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [sortDescending, setSortDescending] = useState(true);
  const [openRowId, setOpenRowId] = useState<string | null>(null);

  // Distinct types present in the data, with "all" prepended — matches
  // `const types = ['all', ...new Set(AUDIT_LOG.map(e=>e.type))]`.
  const availableTypes = ["all", ...new Set(auditLog.map((e) => e.type))];

  const rows = filterAndSortLedger(auditLog, {
    typeFilter,
    interventionFilter,
    // Lower-cased once here, matching the original search input handler
    // (`query = e.target.value.toLowerCase()`).
    query: query.toLowerCase(),
    sortDescending,
  });

  return (
    <div className={`${styles.panel}`}>
      <div className={styles.ledgerHead}>
        <div>
          <h3 className={styles.ledgerTitle}>
            {/* Magnifying-glass icon, copied as-is from the original inline SVG */}
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
            >
              <circle cx="10.5" cy="10.5" r="6.5" />
              <line x1="15.5" y1="15.5" x2="21" y2="21" />
            </svg>
            Audit trail
          </h3>
          <div className={styles.ledgerNote}>
            click a row for the full diagnosis and cost breakdown · click a
            stat on the left to filter by it
          </div>
        </div>
      </div>

      <div className={styles.controls}>
        <div className={styles.filtersRow}>
          {availableTypes.map((type) => (
            <FilterPill
              key={type}
              label={type === "all" ? "All" : TYPE_LABELS[type] ?? type}
              active={typeFilter === type}
              onClick={() => setTypeFilter(type)}
            />
          ))}
        </div>
        <button
          type="button"
          className={styles.sortbtn}
          onClick={() => setSortDescending((prev) => !prev)}
        >
          sort: amount {sortDescending ? "↓" : "↑"}
        </button>
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="search event id…"
        />
      </div>

      <div className={styles.scrollbox}>
        <table className={styles.ledgerTable}>
          <thead>
            <tr>
              <th></th>
              <th>Event</th>
              <th>Root cause</th>
              <th>Action</th>
              <th>Reasoning</th>
              <th>Amount</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className={styles.empty}>nothing matches that filter</div>
                </td>
              </tr>
            ) : (
              rows.map((entry) => {
                const isOpen = openRowId === entry.event_id;
                const { tone, label } = outcomeTone(
                  entry.outcome_recovered,
                  entry.stopping_rule_applied,
                );
                return (
                  // React.Fragment lets us render the row AND its optional
                  // expand row as siblings inside <tbody> without an extra
                  // wrapping element (a <tbody> can only directly contain
                  // <tr> children).
                  <FragmentRow key={entry.event_id}>
                    <tr
                      className={styles.evrow}
                      onClick={() =>
                        setOpenRowId(isOpen ? null : entry.event_id)
                      }
                    >
                      <td>
                        <span
                          className={`${styles.chevron} ${
                            isOpen ? styles.chevronOpen : ""
                          }`}
                        >
                          ▸
                        </span>
                      </td>
                      <td>{entry.event_id}</td>
                      <td>{entry.root_cause.replaceAll("_", " ")}</td>
                      <td>{entry.intervention.replaceAll("_", " ")}</td>
                      <td className={styles.reasonCell}>
                        {entry.intervention_reasoning}
                      </td>
                      <td>{formatINR(entry.amount_at_risk)}</td>
                      <td>
                        <Tag tone={tone}>{label}</Tag>
                      </td>
                    </tr>
                    {isOpen && <ExpandedDetailRow entry={entry} />}
                  </FragmentRow>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Tiny wrapper so callers don't need to import React.Fragment directly —
// purely a readability choice, has zero runtime behaviour of its own.
function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// Second <tr> shown under an open row — mirrors the `tr2.innerHTML` block
// from the original renderLedger(), now as real JSX with real props instead
// of a template literal.
function ExpandedDetailRow({ entry }: { entry: AuditLogEntry }) {
  return (
    <tr className={styles.expandRow}>
      <td colSpan={7}>
        <div className={styles.expandInner}>
          <div>
            Diagnosis reasoning: <b>{entry.diagnosis_reasoning}</b>
          </div>
          <div>
            Stopping rule applied: <b>{entry.stopping_rule_applied ? "yes" : "no"}</b>
          </div>
          <div>
            Gross recovered: <b>{formatINR(entry.gross_amount_recovered)}</b>
          </div>
          <div>
            Intervention cost: <b>{formatINR(entry.intervention_cost)}</b>
          </div>
          <div>
            Net recovered: <b>{formatINR(entry.net_amount_recovered)}</b>
          </div>
          <div>
            Logged at:{" "}
            {/* Matches `e.timestamp.replace('T',' ').slice(0,19)` — trims an
                ISO timestamp down to "YYYY-MM-DD HH:MM:SS" and appends UTC,
                same truncation-not-timezone-conversion behaviour as the
                original (deliberately not using new Date() here, since that
                would convert to the viewer's local timezone instead of
                showing the raw UTC value your data is logged in). */}
            <b>{entry.timestamp.replace("T", " ").slice(0, 19)} UTC</b>
          </div>
        </div>
      </td>
    </tr>
  );
}
