// page.tsx (src/app/dashboard/)
// -----------------------------------------------------------------------------
// This is a React Server Component (no "use client" here) — it's allowed to
// do server-side work like reading a file, hitting a database, or (in your
// case for now) importing the static AUDIT_LOG/SUMMARY constants, and then
// hands the resulting plain data down as props to the client component that
// actually needs interactivity (<Dashboard />, which owns useState for the
// Net/Gross toggle and filters).
//
// Keeping the split this way (server page fetches data → client component
// renders + reacts to clicks) is the same "detail vs list" separation Next.js
// App Router expects, and matches how Revyn's own dashboard route is
// structured (a thin page.tsx handing data to a components/dashboard tree).

import { Dashboard } from "@/components/dashboard";
import { AUDIT_LOG, SUMMARY } from "@/lib/dashboard-data";

// Every page.tsx in the App Router must have a default export — Next.js
// looks specifically for `export default` to know this is the route's page
// component, a named export won't be picked up.
export default function DashboardPage() {
  return <Dashboard auditLog={AUDIT_LOG} summary={SUMMARY} />;
}
