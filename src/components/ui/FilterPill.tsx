// FilterPill.tsx
// -----------------------------------------------------------------------------
// The rounded `.filters button` chip from your original CSS. Split out as a
// ui/ primitive because the same visual pattern (pill button, active state
// toggles ink-colored background) could be reused for any future filter row,
// not just the leak-point filters on the audit trail.

import styles from "./ui.module.css";

interface FilterPillProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

export function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      // Two classes composed with a template string, same pattern as Tag.tsx —
      // base pill styling always applies, `active` class layers the
      // ink-background/paper-text look on top when selected.
      className={`${styles.filterPill} ${active ? styles.filterPillActive : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

// The underlined "clear ✕" link used next to each panel heading
// (#clear-type / #clear-int in the original markup). Kept as a separate,
// tiny component rather than overloading FilterPill with an `isClearLink`
// prop — the two have different semantics (one selects, one resets).
interface ClearLinkProps {
  onClick: () => void;
  visible: boolean; // mirrors the original `style.display = ... ? 'inline' : 'none'`
}

export function ClearLink({ onClick, visible }: ClearLinkProps) {
  if (!visible) return null;
  return (
    <span className={styles.clearFilter} onClick={onClick}>
      clear ✕
    </span>
  );
}
