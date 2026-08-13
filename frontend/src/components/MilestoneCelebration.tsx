import { useEffect, useState } from "react";

const MILESTONES = [10, 50, 100];

function storageKey(profileSlug: string): string {
  return `lingua_milestone_seen_${profileSlug}`;
}

function highestCrossed(count: number): number | null {
  const crossed = MILESTONES.filter((m) => count >= m);
  return crossed.length > 0 ? crossed[crossed.length - 1] : null;
}

// Watches words_fluent and shows a one-time celebration the moment it
// crosses 10/50/100 — "one-time" tracked in localStorage per profile, not
// re-shown on every subsequent page load. The message itself carries the
// content regardless of motion; the animation is a bonus, not a load-
// bearing way to communicate the milestone (prefers-reduced-motion is
// handled globally in index.css, which collapses this animation to
// effectively instant — no separate handling needed here).
export function MilestoneCelebration({ fluentCount, profileSlug }: { fluentCount: number; profileSlug: string }) {
  const [showing, setShowing] = useState<number | null>(null);

  useEffect(() => {
    const key = storageKey(profileSlug);
    const lastSeen = Number(localStorage.getItem(key) ?? "0");
    const milestone = highestCrossed(fluentCount);
    if (milestone !== null && milestone > lastSeen) {
      setShowing(milestone);
    }
  }, [fluentCount, profileSlug]);

  const dismiss = () => {
    if (showing !== null) {
      localStorage.setItem(storageKey(profileSlug), String(showing));
    }
    setShowing(null);
  };

  if (showing === null) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 px-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Milestone: ${showing} words fluent`}
      onClick={dismiss}
    >
      <div
        className="w-full max-w-xs animate-celebrate-pop rounded-3xl bg-surface p-8 text-center shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-5xl">🎉</p>
        <p className="mt-3 text-3xl font-bold text-ember">{showing} words fluent!</p>
        <p className="mt-2 text-parchment/70">
          {showing === 10 && "A real milestone — the first ten are always the hardest."}
          {showing === 50 && "Halfway to a hundred. Keep going."}
          {showing === 100 && "A hundred words fluent. That's a real vocabulary."}
        </p>
        <button
          type="button"
          onClick={dismiss}
          className="mt-6 w-full rounded-2xl bg-ember py-3 text-lg font-bold text-ink transition-transform active:scale-[0.98]"
        >
          Nice!
        </button>
      </div>
    </div>
  );
}
