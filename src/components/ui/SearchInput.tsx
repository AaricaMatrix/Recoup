// SearchInput.tsx
// -----------------------------------------------------------------------------
// The `.search input` box with the "⌕" glyph from your original CSS
// (`.search::before{content:"⌕"...}`). This is a generic text-search field
// with no knowledge of "event ids" — the ledger passes in its own
// placeholder text, keeping this component reusable outside the dashboard.

import styles from "./ui.module.css";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder,
}: SearchInputProps) {
  return (
    // The wrapping <div> carries the `::before` pseudo-element glyph in CSS —
    // it has to be a separate element from the <input> because CSS pseudo
    // elements can't attach directly to a native <input>.
    <div className={styles.search}>
      <input
        value={value}
        // e.target.value is already the "next" string value — no need to
        // lower-case here, the ledger component does that once, so this
        // stays a dumb, reusable text field.
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}
