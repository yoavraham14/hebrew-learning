import type { RoundOut } from "../types";

const COPY: Record<RoundOut["kind"], { title: string; blurb: string }> = {
  recovery: {
    title: "Recovery round",
    blurb: "A quick pass over words you missed recently.",
  },
  mixed: {
    title: "Mixed review",
    blurb: "A broader refresher across everything you've studied.",
  },
};

// Shown once before a review-game round's cards start — a bonus-round
// beat, deliberately distinct from the regular deck (dashed border, no
// topic/level badges) rather than a new palette.
export function RoundBanner({ kind, onStart }: { kind: RoundOut["kind"]; onStart: () => void }) {
  const { title, blurb } = COPY[kind];
  return (
    <div className="w-full animate-reveal-rise rounded-3xl border-2 border-dashed border-bridge/40 bg-surface/60 p-6 text-center sm:p-8">
      <p className="text-xs font-semibold uppercase tracking-wider text-bridge">Bonus round</p>
      <p className="mt-2 text-2xl font-bold">{title}</p>
      <p className="mt-2 text-parchment/70">{blurb}</p>
      <button
        type="button"
        onClick={onStart}
        className="mt-6 w-full rounded-2xl bg-bridge py-4 text-lg font-bold text-ink transition-transform active:scale-[0.98]"
      >
        Start
      </button>
    </div>
  );
}
