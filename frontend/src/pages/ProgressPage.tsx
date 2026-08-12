import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { FluencyProgressBar } from "../components/FluencyProgressBar";
import type { ProgressOut } from "../types";

function StatTile({
  label,
  value,
  accent,
  sublabel,
}: {
  label: string;
  value: string | number;
  accent: string;
  sublabel?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-2xl bg-surface px-4 py-6 text-center">
      <span className={`text-4xl font-bold tabular-nums ${accent}`}>{value}</span>
      <span className="text-sm text-parchment/60">{label}</span>
      {sublabel && <span className="text-xs text-parchment/40">{sublabel}</span>}
    </div>
  );
}

function DailyGoalTile({ today, goal }: { today: number; goal: number }) {
  const pct = goal > 0 ? Math.min(100, Math.round((today / goal) * 100)) : 0;
  const met = today >= goal;
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl bg-surface px-4 py-6 text-center">
      <span className={`text-4xl font-bold tabular-nums ${met ? "text-known" : "text-ember"}`}>
        {today}/{goal}
      </span>
      <span className="text-sm text-parchment/60">Daily goal</span>
      <div className="mt-1 h-1.5 w-full max-w-20 overflow-hidden rounded-full bg-surfacemuted">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ease-out ${met ? "bg-known" : "bg-ember"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function ProgressPage() {
  const [progress, setProgress] = useState<ProgressOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getProgress()
      .then(setProgress)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load progress."));
  }, []);

  return (
    <div className="flex w-full flex-col items-center gap-4 px-4 py-6 sm:py-10">
      <div className="flex w-full max-w-md flex-col gap-4">
        <h1 className="text-center text-2xl font-bold">Your progress</h1>

        {error && <p className="text-center text-danger">{error}</p>}

        {progress && (
          <>
            <FluencyProgressBar fluent={progress.words_fluent} total={progress.total_verified_words} />

            <div className="grid grid-cols-2 gap-3">
              <StatTile label="Seen" value={progress.words_seen} accent="text-bridge" />
              <StatTile label="Due today" value={progress.due_today} accent="text-almost" />
              <StatTile
                label="Streak"
                value={progress.current_streak}
                accent="text-ember"
                sublabel={`Best: ${progress.longest_streak}`}
              />
              <DailyGoalTile today={progress.today_review_count} goal={progress.daily_goal} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
