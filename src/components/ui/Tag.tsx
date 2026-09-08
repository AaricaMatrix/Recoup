// Tag.tsx
// -----------------------------------------------------------------------------
// Small colored status pill. In your original HTML this was three hardcoded
// <span class="tag win|loss|hold"> variants. Pulling it into ui/ (instead of
// leaving it inside the dashboard folder) matches Revyn's pattern of putting
// generic, reusable visual primitives in ui/ and page-specific composition in
// dashboard/ — this Tag has no idea what a "recovery" or "risk" is, it just
// renders a labeled pill in one of three tones.

import styles from "./ui.module.css";

// The three tones your CSS already defines (.tag.win / .tag.loss / .tag.hold).
// A union type here means passing tone="wins" (typo) fails at compile time
// instead of silently rendering an unstyled pill.
export type TagTone = "win" | "loss" | "hold";

interface TagProps {
  tone: TagTone; // which color variant to render
  children: React.ReactNode; // the label text, e.g. "recovered"
}

export function Tag({ tone, children }: TagProps) {
  // `styles.tag` is the base class, `styles[tone]` picks the tone-specific
  // class (tag.win / tag.loss / tag.hold) — same two-class approach as your
  // original `class="tag win"` markup, just composed via CSS Modules.
  return <span className={`${styles.tag} ${styles[tone]}`}>{children}</span>;
}

// Small pure helper so callers don't have to know your outcome logic —
// mirrors the `outcomeTag(e)` function from the original inline script.
export function outcomeTone(
  outcomeRecovered: boolean,
  stoppingRuleApplied: boolean,
): { tone: TagTone; label: string } {
  if (stoppingRuleApplied) return { tone: "hold", label: "held" };
  return outcomeRecovered
    ? { tone: "win", label: "recovered" }
    : { tone: "loss", label: "no win" };
}
