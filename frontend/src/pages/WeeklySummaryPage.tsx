import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { WeeklySummary } from "../types";

function encouragement(s: WeeklySummary): string {
  if (s.days_studied === 0) return "No study days yet this week — even one short session counts.";
  if (s.days_studied >= 6) return "Excellent week — you studied nearly every day.";
  if (s.words_became_fluent > 0) return "Great progress — you made real words stick this week.";
  return "Good work — keep the streak going.";
}

export function WeeklySummaryPage({ onBack }: { onBack: () => void }) {
  const [summary, setSummary] = useState<WeeklySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getWeeklySummary()
      .then(setSummary)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load your summary."));
  }, []);

  const trend =
    summary && summary.accuracy_last_week > 0
      ? summary.accuracy_this_week - summary.accuracy_last_week
      : null;

  return (
    <div className="flex w-full flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-md">
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="rounded-full bg-surfacemuted px-3 py-1.5 text-sm text-parchment/70 hover:text-parchment"
          >
            ← Back
          </button>
          <h1 className="text-2xl font-bold">This week</h1>
        </div>

        {error && <p className="text-danger">{error}</p>}

        {summary && (
          <div className="flex flex-col gap-4">
            <div className="rounded-3xl bg-surface p-6 text-center shadow-2xl shadow-black/30">
              <p className="text-4xl font-bold text-ember">{summary.days_studied}/7</p>
              <p className="mt-1 text-sm text-parchment/60">days studied</p>
              <p className="mt-4 text-parchment/80">{encouragement(summary)}</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-2xl bg-surface px-4 py-6 text-center">
                <p className="text-3xl font-bold tabular-nums text-bridge">{summary.words_added}</p>
                <p className="text-sm text-parchment/60">Words added</p>
              </div>
              <div className="rounded-2xl bg-surface px-4 py-6 text-center">
                <p className="text-3xl font-bold tabular-nums text-known">{summary.words_became_fluent}</p>
                <p className="text-sm text-parchment/60">Became fluent</p>
              </div>
              <div className="rounded-2xl bg-surface px-4 py-6 text-center">
                <p className="text-3xl font-bold tabular-nums text-almost">{summary.reviews_this_week}</p>
                <p className="text-sm text-parchment/60">Reviews</p>
              </div>
              <div className="rounded-2xl bg-surface px-4 py-6 text-center">
                <p className="text-3xl font-bold tabular-nums text-parchment">
                  {summary.reviews_this_week > 0 ? `${summary.accuracy_this_week}%` : "—"}
                </p>
                <p className="text-sm text-parchment/60">
                  Accuracy
                  {trend !== null && (
                    <span className={trend >= 0 ? "text-known" : "text-danger"}>
                      {" "}
                      {trend >= 0 ? "↑" : "↓"} {Math.abs(trend).toFixed(1)}%
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
