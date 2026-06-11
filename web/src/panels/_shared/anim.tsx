/** Motion primitives for the C2 panels. Every JS-driven animation checks
 *  prefers-reduced-motion and degrades to the final value instantly; CSS-driven
 *  ones are additionally neutered by the global reduced-motion rule in tokens.css. */
import { useEffect, useRef, useState } from "react";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Tween a number from 0 (on first appear) or its previous value toward `value`. */
export function useCountUp(value: number, durationMs = 650): number {
  const [display, setDisplay] = useState<number>(() => (prefersReducedMotion() ? value : 0));
  const displayRef = useRef<number>(display);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (prefersReducedMotion() || displayRef.current === value) {
      displayRef.current = value;
      setDisplay(value);
      return;
    }
    const from = displayRef.current;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = from + (value - from) * eased;
      displayRef.current = v;
      setDisplay(v);
      if (t < 1) rafRef.current = requestAnimationFrame(step);
      else displayRef.current = value;
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, durationMs]);

  return display;
}

/** Count-up wrapper that renders a formatted number (e.g. usd, days). */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const n = useCountUp(value);
  return <>{format(n)}</>;
}
