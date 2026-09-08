// useCountUp.ts
// -----------------------------------------------------------------------------
// React-ified version of the original countUp(el, target, fmt) function.
// The original directly mutated `el.textContent` inside a requestAnimationFrame
// loop — that's a direct-DOM pattern that doesn't fit React's render model, so
// instead this hook returns a *number* that updates on every animation frame,
// and the component re-renders with that number formatted by whatever
// function you pass in (formatINR, Math.round, etc).

import { useEffect, useRef, useState } from "react";

// Reads the same media query your original script checked once at the top
// level (`window.matchMedia('(prefers-reduced-motion: reduce)').matches`).
// Wrapped in a function (not a top-level constant) because `window` doesn't
// exist during Next.js server-side rendering — calling this only inside
// useEffect (client-only) avoids a "window is not defined" crash.
function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// `target` is the final number to count up to. Returns the current animated
// value, starting at 0 and easing up to `target` over ~900ms — same duration
// and the same cubic ease-out curve (`1 - Math.pow(1-p, 3)`) as the original.
export function useCountUp(target: number): number {
  const [value, setValue] = useState(0);
  // A ref (not state) for the requestAnimationFrame id, so cancelling it on
  // unmount/re-run doesn't itself trigger a re-render.
  const frameRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    // Respect the user's OS-level "reduce motion" setting — jump straight to
    // the final value instead of animating, exactly like the original.
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }

    const start = performance.now();
    const duration = 900; // milliseconds, matches the original `dur = 900`

    function step(now: number) {
      const progress = Math.min(1, (now - start) / duration);
      // Cubic ease-out: fast at first, settling in gently at the end.
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      }
    }
    frameRef.current = requestAnimationFrame(step);

    // Cleanup: if `target` changes again before the animation finishes (e.g.
    // the user flips Net/Gross mid-animation), cancel the stale frame loop
    // so two animations never fight over the same state.
    return () => {
      if (frameRef.current !== undefined) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [target]);

  return value;
}
