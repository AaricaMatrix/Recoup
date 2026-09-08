// css-modules.d.ts
// -----------------------------------------------------------------------------
// Tells TypeScript what `import styles from "./foo.module.css"` resolves to.
// Next.js's own build pipeline already understands CSS Modules at runtime —
// this file only exists so `tsc`/your editor's type-checker doesn't error on
// the import. If your project already has a declaration like this
// (sometimes bundled inside next-env.d.ts or a global.d.ts), you don't need
// to add this file — just confirm the same declaration exists somewhere.
declare module "*.module.css" {
  const classes: { readonly [className: string]: string };
  export default classes;
}
