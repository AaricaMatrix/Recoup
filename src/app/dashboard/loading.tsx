// loading.tsx (src/app/dashboard/)
// -----------------------------------------------------------------------------
// Next.js automatically renders this while page.tsx (and anything it awaits)
// is still loading — no manual "isLoading" state needed, the App Router
// handles the swap for you via React Suspense under the hood. This is the
// same file-based convention Revyn's own src/app/ uses (loading.tsx sits
// next to page.tsx in the same route folder).
//
// Kept intentionally plain — three pulsing bars roughly where the funnel
// stampboxes will appear — rather than a generic spinner, so the loading
// state doesn't feel visually disconnected from the paper/ledger aesthetic
// underneath it.

import styles from "./loading.module.css";

export default function DashboardLoading() {
  return (
    <div className={styles.wrap}>
      <div className={styles.skeletonRow}>
        <div className={styles.skeletonBox} />
        <div className={styles.skeletonBox} />
        <div className={styles.skeletonBox} />
      </div>
    </div>
  );
}
