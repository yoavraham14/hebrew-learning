import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProgressOut } from "../types";

function StatTile({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-2xl bg-surface px-4 py-6">
      <span className={`text-4xl font-bold ${accent}`}>{value}</span>
      <span className="text-sm text-parchment/60">{label}</span>
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
    <div className="flex w-full flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-md">
        <h1 className="mb-6 text-center text-2xl font-bold">Your progress</h1>

        {error && <p className="text-center text-danger">{error}</p>}

        {progress && (
          <div className="grid grid-cols-3 gap-3">
            <StatTile label="Seen" value={progress.words_seen} accent="text-bridge" />
            <StatTile label="Known" value={progress.words_known} accent="text-known" />
            <StatTile label="Streak" value={progress.current_streak} accent="text-ember" />
          </div>
        )}
      </div>
    </div>
  );
}
