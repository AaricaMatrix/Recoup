// RecoveryFunnel.tsx
// -----------------------------------------------------------------------------
// Ports the `.funnel` block: three cells (at risk / acted on / recovered)
// plus the two floating "tape" stubs with a hover tooltip. Numbers animate
// in via useCountUp, same easing/duration as the original countUp().

import styles from "./dashboard.module.css";
import { formatINR, pickByMode, recoveredPercentLabel } from "./dashboard.utils";
import { useCountUp } from "./useCountUp";
import type { DashboardSummary, RecoveryMode } from "./dashboard.types";

interface RecoveryFunnelProps {
  summary: DashboardSummary;
  mode: RecoveryMode;
}

export function RecoveryFunnel({ summary, mode }: RecoveryFunnelProps) {
  // Each stampbox/number gets its own count-up value — mirrors the three
  // separate `countUp(...)` calls in the original renderFunnel().
  const animatedRisk = useCountUp(summary.total_amount_at_risk);
  const animatedActed = useCountUp(summary.events_acted_on);
  const recoveredTarget = pickByMode(
    mode,
    summary.total_net_recovered,
    summary.total_gross_recovered,
  );
  const animatedRecovered = useCountUp(recoveredTarget);

  return (
    <>
      <div className={styles.funnel}>
        {/* Cell 1: revenue at risk — red stampbox styling from .fcell.risk */}
        <div className={`${styles.fcell} ${styles.fcellRisk}`}>
          <div className={styles.fcellLabel}>Revenue at risk</div>
          <div className={styles.stampbox}>{formatINR(animatedRisk)}</div>
        </div>

        {/* Cell 2: plain number, no stampbox border — events acted on */}
        <div className={styles.fcell}>
          <div className={styles.fcellLabel}>Events acted on</div>
          <div className={styles.fcellNum}>{Math.round(animatedActed)}</div>
        </div>

        {/* Cell 3: recovered amount — green stampbox styling from .fcell.recovered.
            The label text itself switches between "Net recovered" and
            "Gross recovered" depending on the toggle, same as the original
            `recovered-label` element's textContent swap. */}
        <div className={`${styles.fcell} ${styles.fcellRecovered}`}>
          <div className={styles.fcellLabel}>
            {recoveredPercentLabel(summary, mode)}
          </div>
          <div className={styles.stampbox}>
            {formatINR(animatedRecovered)}
          </div>
        </div>

        {/* First tape stub: held-by-stopping-rules count, positioned at 33% */}
        <TapeStub
          position="first"
          statLabel="held"
          statValue={summary.events_written_off_by_stopping_rules}
          tooltip="Events written off by the stopping rules never get a nudge — that's the agent choosing not to spam someone, not a miss."
          curveDirection="down"
        />

        {/* Second tape stub: win rate, positioned at 66% */}
        <TapeStub
          position="second"
          statLabel="win rate"
          statValue={`${summary.win_rate_pct_of_acted_on}%`}
          tooltip="Win rate on events the agent actually chose to act on, cost of the intervention already taken out."
          curveDirection="up"
        />
      </div>
      <div className={styles.funnelNote}>
        ↑ hover the tape for what each number means
      </div>
    </>
  );
}

// One hand-drawn "tape" divider with a squiggly connecting line, a stat, and
// a hover tooltip. Both stubs in the original used nearly identical SVG path
// data mirrored vertically — `curveDirection` picks which mirrored path to
// draw instead of duplicating the whole component twice.
interface TapeStubProps {
  position: "first" | "second";
  statLabel: string;
  statValue: number | string;
  tooltip: string;
  curveDirection: "up" | "down";
}

function TapeStub({
  position,
  statLabel,
  statValue,
  tooltip,
  curveDirection,
}: TapeStubProps) {
  const positionClass =
    position === "first" ? styles.tapeFirst : styles.tapeSecond;

  // Exact path data from the original two <svg> blocks — "down" is stub1's
  // path (dips down then curls up into the arrowhead), "up" is stub2's path
  // (mirrored: rises then curls down).
  const pathD =
    curveDirection === "down"
      ? "M1 9 C 8 3, 16 15, 24 8 C 27 6, 29 6.5, 31 9"
      : "M1 9 C 8 15, 16 3, 24 10 C 27 12, 29 11, 31 9";
  const arrowheadD =
    curveDirection === "down"
      ? "M25 5.5 L31 9 L24.5 12"
      : "M25 12.5 L31 9 L24.5 5.5";

  return (
    <div className={`${styles.tape} ${positionClass}`}>
      <svg viewBox="0 0 36 18">
        <path d={pathD} />
        <path d={arrowheadD} />
      </svg>
      <div className={styles.tapeStat}>
        <b>{statValue}</b> {statLabel}
      </div>
      {/* Tooltip is always in the DOM; CSS handles show/hide on :hover via
          `.tape:hover .tip { opacity: 1 }`, same as the original — no JS
          state needed for something CSS already does declaratively. */}
      <div className={styles.tip}>{tooltip}</div>
    </div>
  );
}
