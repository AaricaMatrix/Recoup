// ToggleGroup.tsx
// -----------------------------------------------------------------------------
// Generic two-or-more-option pill switch. Your original HTML had exactly one
// use of this pattern (#gn-toggle with Net/Gross buttons), but the markup and
// CSS (.toggle / .toggle button / .toggle button.active) are generic enough
// that Revyn's structure would put this in ui/, not dashboard/, so it can be
// reused anywhere else you need a segmented control later.

import styles from "./ui.module.css";

// One button inside the toggle. `value` is the underlying data value (e.g.
// "net"), `label` is what gets displayed (e.g. "Net") — kept separate in
// case you ever want display text that differs from the stored value.
interface ToggleOption<T extends string> {
  value: T;
  label: string;
}

interface ToggleGroupProps<T extends string> {
  options: ToggleOption<T>[];
  value: T; // the currently active value
  onChange: (value: T) => void; // called with the new value on click
}

// Generic over T so this same component works for RecoveryMode ("net"|"gross")
// today and any other string union you need later, without a rewrite.
export function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
}: ToggleGroupProps<T>) {
  return (
    <div className={styles.toggle}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          // Only one class toggles here — `active` — matching the original
          // script's `[...btn.parentElement.children].forEach(b=>b.classList.remove('active'))`
          // followed by `btn.classList.add('active')`.
          className={value === option.value ? styles.active : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
