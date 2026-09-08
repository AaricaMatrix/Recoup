# layout/

Same situation as `../landing/README.md` — this folder is here so the
overall structure matches Revyn's four-folder pattern, but I don't have your
actual nav/header/footer/sidebar markup to convert yet.

This is typically where the *shared chrome* lives — the parts that wrap
every page, not just the dashboard: a top nav, a site footer, maybe a
dashboard-specific sidebar if `/dashboard/*` has sub-pages like `/risks` or
`/audit`. Your root `src/app/layout.tsx` would import from here, e.g.:

```tsx
import { SiteNav } from "@/components/layout/SiteNav";
import { SiteFooter } from "@/components/layout/SiteFooter";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SiteNav />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
```

Send over whatever nav/footer markup you've already got and I'll split it
into components the same way I did for `dashboard/`.
