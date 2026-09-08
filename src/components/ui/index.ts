// index.ts (ui/)
// -----------------------------------------------------------------------------
// Barrel file: lets other folders write
//   import { Tag, ToggleGroup, SearchInput, FilterPill } from "@/components/ui";
// instead of importing each file by its own path. Purely a convenience layer
// — it re-exports, it doesn't add any logic of its own.

export { Tag, outcomeTone } from "./Tag";
export type { TagTone } from "./Tag";

export { ToggleGroup } from "./ToggleGroup";

export { SearchInput } from "./SearchInput";

export { FilterPill, ClearLink } from "./FilterPill";
