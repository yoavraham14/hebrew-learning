import { useEffect, useState } from "react";

// The emotional centerpiece of the progress page (per the ui-design skill's
// "spend real visual boldness here" call) — how much of the whole word bank
// this profile has actually made fluent. Signature interaction: the fill
// animates in from 0 on mount rather than appearing instantly, with a
// glowing leading edge, echoing the reveal-glow motif that's this app's
// existing signature element elsewhere.
export function FluencyProgressBar({ fluent, total }: { fluent: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((fluent / total) * 100)) : 0;
  const [displayPct, setDisplayPct] = useState(0);

  useEffect(() => {
    // One tick so the browser paints the 0% state first, then transitions
    // to the real value — CSS transition, not a DOM-swap.
    const id = requestAnimationFrame(() => setDisplayPct(pct));
    return () => cancelAnimationFrame(id);
  }, [pct]);

  return (
    <div className="w-full rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-semibold uppercase tracking-wider text-bridge">Fluency</p>
        <p className="text-sm text-parchment/50">
          {fluent} of {total} words
        </p>
      </div>

      <p className="mt-2 text-6xl font-bold tabular-nums text-parchment sm:text-7xl">{displayPct}%</p>

      <div className="relative mt-5 h-4 overflow-visible rounded-full bg-surfacemuted">
        <div
          className="relative h-full rounded-full bg-gradient-to-r from-ember/70 to-ember transition-[width] duration-[1100ms] ease-out"
          style={{ width: `${displayPct}%` }}
        >
          {displayPct > 0 && (
            <span
              className="absolute right-0 top-1/2 h-4 w-4 -translate-y-1/2 translate-x-1/2 rounded-full bg-ember shadow-[0_0_16px_4px_rgba(242,153,74,0.65)]"
              aria-hidden="true"
            />
          )}
        </div>
      </div>

      <p className="mt-3 text-sm text-parchment/50">
        Words become fluent once you've marked them "knew it" enough times — see Settings to change the threshold.
      </p>
    </div>
  );
}
