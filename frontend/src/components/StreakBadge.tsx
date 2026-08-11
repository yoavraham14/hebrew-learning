export function StreakBadge({ streak }: { streak: number }) {
  return (
    <div className="flex items-center gap-1.5 rounded-full bg-surfacemuted px-3 py-1.5 text-sm font-semibold text-ember">
      <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden="true">
        <path d="M12 2c1 3-2 4-2 7a3 3 0 0 0 6 0c0-1-.5-2-.5-2 2 1 3.5 3.5 3.5 6a7 7 0 1 1-14 0c0-4 3-6 4-8 .5-1 .8-2 3-3z" />
      </svg>
      <span>{streak}</span>
    </div>
  );
}
