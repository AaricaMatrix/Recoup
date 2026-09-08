# landing/

This folder exists so `src/components/` matches the same four-folder pattern
as 26Naitik/Revyn's structure (`dashboard/`, `landing/`, `layout/`, `ui/`).

I didn't have your actual landing-page markup/copy to convert (only
`dashboard.html` was shared with me), so there's nothing to port in here yet
— I didn't want to invent placeholder hero/copy content and hand it to you
as if it were real.

When you're ready to convert your landing page here, apply the same pattern
used in `../dashboard/`:

1. One component per visual section (e.g. `Hero.tsx`, `ProblemSection.tsx`,
   `HowItWorks.tsx`, `GuardrailsSection.tsx`) instead of one giant page file.
2. Shared bits that aren't landing-specific (buttons, badges, pills) go in
   `../ui/`, not duplicated here.
3. One CSS Module per component or one shared `landing.module.css` — your
   call, based on how much styling is actually shared across sections.
4. A `page.tsx` in `src/app/` imports the composed result, same as
   `src/app/dashboard/page.tsx` does for `<Dashboard />`.

Paste your existing landing page's HTML/JSX here (or start a new chat message
with it) and I'll do the same file-by-file breakdown for it.
