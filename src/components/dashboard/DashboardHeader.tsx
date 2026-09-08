// DashboardHeader.tsx
// -----------------------------------------------------------------------------
// Ports the `.top` block from dashboard.html: the "Recoup · AI Revenue
// Recovery agent" brand strip, the h1/sub copy, the buildathon tape-tag, and
// the Net/Gross ToggleGroup (imported from ui/ instead of being redefined
// here — same primitive, dashboard just wires it up with real data).

import styles from "./dashboard.module.css";
import { ToggleGroup } from "../ui";
import type { RecoveryMode } from "./dashboard.types";

interface DashboardHeaderProps {
  mode: RecoveryMode;
  onModeChange: (mode: RecoveryMode) => void;
}

export function DashboardHeader({ mode, onModeChange }: DashboardHeaderProps) {
  return (
    <div className={styles.top}>
      <div>
        {/* Brand strip: colored dot + "Recoup" in bold + description,
            matches <div class="brand"><span class="dot"></span>... */}
        <div className={styles.brand}>
          <span className={styles.dot}></span>
          <b className={styles.brandName}>Recoup</b> · AI Revenue Recovery
          agent
        </div>
        <h1 className={styles.heading}>
          Where the money went, and what got it back.
        </h1>
        <div className={styles.subheading}>
          One batch, run once, numbers untouched afterward — every action
          below has a reason attached, logged before the outcome was known.
        </div>
      </div>
      <div className={styles.topRight}>
        <div className={styles.tapeTag}>Razorpay Buildathon · Track 03</div>
        <ToggleGroup<RecoveryMode>
          value={mode}
          onChange={onModeChange}
          options={[
            { value: "net", label: "Net" },
            { value: "gross", label: "Gross" },
          ]}
        />
      </div>
    </div>
  );
}
