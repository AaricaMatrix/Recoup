// CategoryBreakdown.tsx
// -----------------------------------------------------------------------------
// Ports renderByType() and renderByIntervention() from the original inline
// script into two React components that share one <Panel> wrapper. The
// original built these as raw innerHTML strings; here each "row" is a real
// component so click-to-filter and the active-row highlight are just props
// instead of manual DOM class toggling.

import { useEffect, useState } from "react";
import styles from "./dashboard.module.css";
import { ClearLink } from "../ui";
import { pickByMode, TYPE_LABELS, formatINR } from "./dashboard.utils";
import type {
  InterventionAggregate,
  RecoveryMode,
  TypeAggregate,
} from "./dashboard.types";

// Shared panel chrome: the card background, the little "tab" notch on top
// (.panel::before in CSS), the heading, and an optional clear-filter link.
// Both breakdown panels render inside this so the surrounding look stays
// identical even though their row content differs completely.
function Panel({
  title,
  onClear,
  clearVisible,
  children,
}: {
  title: string;
  onClear: () => void;
  clearVisible: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeadRow}>
        <h3>{title}</h3>
        <ClearLink onClick={onClear} visible={clearVisible} />
      </div>
      {children}
    </div>
  );
}

// A progress bar that animates its width in on mount/update instead of
// jumping straight there — replicates the original's
// `requestAnimationFrame(()=> row.querySelector('.bar div').style.width = pct+'%')`
// trick, which forced the browser to paint at width:0 first so the CSS
// transition had something to animate from.
function AnimatedBar({ percent }: { percent: number }) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    // Deferring the width update to the next frame (rather than setting it
    // synchronously) is what makes the CSS `transition: width .8s` actually
    // play instead of snapping instantly to the target width.
    const frame = requestAnimationFrame(() => setWidth(percent));
    return () => cancelAnimationFrame(frame);
  }, [percent]);
  return (
    <div className={styles.bar}>
      <div className={styles.barFill} style={{ width: `${width}%` }} />
    </div>
  );
}

interface ByTypeBreakdownProps {
  aggregates: Record<string, TypeAggregate>;
  mode: RecoveryMode;
  activeFilter: string; // 'all' means nothing is filtered
  onSelect: (type: string) => void;
  onClear: () => void;
}

// "By leak point" — left panel. Clicking a row toggles that type as the
// active filter (clicking the already-active row clears it), same
// click-to-toggle behaviour as the original `row.onclick`.
export function ByTypeBreakdown({
  aggregates,
  mode,
  activeFilter,
  onSelect,
  onClear,
}: ByTypeBreakdownProps) {
  return (
    <Panel
      title="By leak point"
      onClear={onClear}
      clearVisible={activeFilter !== "all"}
    >
      {Object.entries(aggregates).map(([type, agg]) => {
        const amount = pickByMode(mode, agg.net, agg.gross);
        // Math.max(0, ...) guards against a negative percentage if net
        // recovered somehow exceeds at-risk after cost deductions — same
        // defensive clamp as the original `Math.max(0, Math.round(...))`.
        const percent = Math.max(0, Math.round((100 * amount) / agg.at_risk));
        const isActive = activeFilter === type;
        return (
          <div
            key={type}
            className={`${styles.row} ${styles.clickableRow} ${
              isActive ? styles.clickableRowActive : ""
            }`}
            onClick={() => onSelect(type)}
          >
            <div style={{ flex: 1 }}>
              <div className={styles.rowName}>{TYPE_LABELS[type] ?? type}</div>
              <AnimatedBar percent={percent} />
            </div>
            <div className={styles.rowMeta} style={{ textAlign: "right" }}>
              {formatINR(amount)} / {formatINR(agg.at_risk)}
            </div>
          </div>
        );
      })}
    </Panel>
  );
}

interface ByInterventionBreakdownProps {
  aggregates: Record<string, InterventionAggregate>;
  mode: RecoveryMode;
  activeFilter: string | null;
  onSelect: (intervention: string) => void;
  onClear: () => void;
}

// "By intervention" — right panel. Rows are sorted by recovered amount
// (net or gross, depending on mode) descending, same as the original
// `.sort((a,b)=> (mode==='net'?...) - (mode==='net'?...))`.
export function ByInterventionBreakdown({
  aggregates,
  mode,
  activeFilter,
  onSelect,
  onClear,
}: ByInterventionBreakdownProps) {
  const sortedEntries = Object.entries(aggregates).sort(
    ([, a], [, b]) => pickByMode(mode, b.net, b.gross) - pickByMode(mode, a.net, a.gross),
  );

  return (
    <Panel
      title="By intervention"
      onClear={onClear}
      clearVisible={activeFilter !== null}
    >
      {sortedEntries.map(([intervention, agg]) => {
        const winRate = agg.attempts ? Math.round((100 * agg.wins) / agg.attempts) : 0;
        const isActive = activeFilter === intervention;
        return (
          <div
            key={intervention}
            className={`${styles.row} ${styles.clickableRow} ${
              isActive ? styles.clickableRowActive : ""
            }`}
            onClick={() => onSelect(intervention)}
          >
            {/* replaceAll('_',' ') matches the original's underscore-to-space
                display formatting for intervention names like send_payment_link */}
            <div className={styles.rowName}>
              {intervention.replaceAll("_", " ")}
            </div>
            <div className={styles.rowMeta}>
              {agg.wins}/{agg.attempts} won · {winRate}%
            </div>
          </div>
        );
      })}
    </Panel>
  );
}
