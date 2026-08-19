import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { ActivityCalendar } from "../components/ActivityCalendar";
import { FluencyProgressBar } from "../components/FluencyProgressBar";
import { MilestoneCelebration } from "../components/MilestoneCelebration";
import { isHebrewText } from "../lib/text";
import type { ActivityDay, ProgressOut, WordProgress } from "../types";

function StatTile({
  label,
  value,
  accent,
  sublabel,
  onClick,
}: {
  label: string;
  value: string | number;
  accent: string;
  sublabel?: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className={`text-4xl font-bold tabular-nums ${accent}`}>{value}</span>
      <span className="text-sm text-parchment/60">{label}</span>
      {sublabel && <span className="text-xs text-parchment/40">{sublabel}</span>}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="flex flex-col items-center gap-1 rounded-2xl bg-surface px-4 py-6 text-center transition-colors hover:bg-surfacemuted"
      >
        {content}
      </button>
    );
  }

  return <div className="flex flex-col items-center gap-1 rounded-2xl bg-surface px-4 py-6 text-center">{content}</div>;
}

function GoalTile({ label, current, goal }: { label: string; current: number; goal: number }) {
  const pct = goal > 0 ? Math.min(100, Math.round((current / goal) * 100)) : 0;
  const met = current >= goal;
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl bg-surface px-4 py-6 text-center">
      <span className={`text-4xl font-bold tabular-nums ${met ? "text-known" : "text-ember"}`}>
        {current}/{goal}
      </span>
      <span className="text-sm text-parchment/60">{label}</span>
      <div className="mt-1 h-1.5 w-full max-w-20 overflow-hidden rounded-full bg-surfacemuted">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ease-out ${met ? "bg-known" : "bg-ember"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const MIN_TIMES_SEEN_FOR_HARDEST = 3;

function HardestWordsCard({ words }: { words: WordProgress[] }) {
  const hardest = [...words]
    .filter((w) => w.times_seen >= MIN_TIMES_SEEN_FOR_HARDEST)
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 5);

  return (
    <div className="rounded-2xl bg-surface p-5">
      <p className="text-sm font-semibold uppercase tracking-wider text-bridge">Hardest words</p>
      {hardest.length === 0 ? (
        <p className="mt-3 text-sm text-parchment/50">
          Not enough data yet — words need {MIN_TIMES_SEEN_FOR_HARDEST}+ reviews to show up here.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {hardest.map((w) => (
            <li key={w.word_pair_id} className="flex items-center justify-between text-sm">
              <span dir={isHebrewText(w.hebrew_word) ? "rtl" : "ltr"} className="font-medium">
                {w.hebrew_word} <span className="text-parchment/50">· {w.spanish_word}</span>
              </span>
              <span className="tabular-nums text-danger">{w.accuracy}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProgressPage({
  profileSlug,
  onOpenWords,
  onOpenWeeklySummary,
}: {
  profileSlug: string;
  onOpenWords: () => void;
  onOpenWeeklySummary: () => void;
}) {
  const [progress, setProgress] = useState<ProgressOut | null>(null);
  const [words, setWords] = useState<WordProgress[] | null>(null);
  const [activity, setActivity] = useState<ActivityDay[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getProgress()
      .then(setProgress)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load progress."));
    api.getWords().then(setWords).catch(() => undefined); // hardest-words card just stays empty on failure
    api.getActivity().then(setActivity).catch(() => undefined); // calendar just stays empty on failure
  }, []);

  return (
    <div className="flex w-full flex-col items-center gap-4 px-4 py-6 sm:py-10">
      <div className="flex w-full max-w-md flex-col gap-4">
        <h1 className="text-center text-2xl font-bold">Your progress</h1>

        {error && <p className="text-center text-danger">{error}</p>}

        {progress && (
          <>
            <MilestoneCelebration fluentCount={progress.words_fluent} profileSlug={profileSlug} />

            <FluencyProgressBar fluent={progress.words_fluent} total={progress.total_verified_words} />

            <div className="grid grid-cols-2 gap-3">
              <StatTile label="Seen" value={progress.words_seen} accent="text-bridge" onClick={onOpenWords} />
              <StatTile label="Due today" value={progress.due_today} accent="text-almost" />
              <StatTile
                label="Streak"
                value={progress.current_streak}
                accent="text-ember"
                sublabel={`Best: ${progress.longest_streak}`}
              />
              <GoalTile label="Daily goal" current={progress.today_review_count} goal={progress.daily_goal} />
              <StatTile label="Videos watched" value={progress.videos_watched} accent="text-bridge" />
              <GoalTile
                label="Weekly video goal"
                current={progress.videos_watched_this_week}
                goal={progress.weekly_video_goal}
              />
            </div>

            <button
              type="button"
              onClick={onOpenWeeklySummary}
              className="rounded-2xl bg-surface px-5 py-4 text-left transition-colors hover:bg-surfacemuted"
            >
              <span className="text-sm font-semibold text-bridge">This week →</span>
              <span className="block text-sm text-parchment/60">See your weekly summary</span>
            </button>

            {activity && <ActivityCalendar days={activity} />}
            {words && <HardestWordsCard words={words} />}
          </>
        )}
      </div>
    </div>
  );
}
