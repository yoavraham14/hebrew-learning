import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { StarButton } from "../components/StarButton";
import { isHebrewText } from "../lib/text";
import type { WordProgress } from "../types";

type SortKey = "hebrew_word" | "status" | "times_seen" | "accuracy";
type SortDir = "asc" | "desc";

const STATUS_LABEL: Record<WordProgress["status"], string> = {
  new: "New",
  learning: "Learning",
  fluent: "Fluent",
};

const STATUS_ACCENT: Record<WordProgress["status"], string> = {
  new: "text-parchment/60",
  learning: "text-almost",
  fluent: "text-known",
};

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "hebrew_word", label: "Word" },
  { key: "status", label: "Status" },
  { key: "times_seen", label: "Seen" },
  { key: "accuracy", label: "Accuracy" },
];

function WordRow({
  word,
  busy,
  onMarkFluent,
  onReset,
}: {
  word: WordProgress;
  busy: boolean;
  onMarkFluent: () => void;
  onReset: () => void;
}) {
  return (
    <div className="rounded-2xl bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <StarButton wordPairId={word.word_pair_id} starred={word.starred} className="!p-1" />
          <div>
            <p dir={isHebrewText(word.hebrew_word) ? "rtl" : "ltr"} className="text-lg font-bold">
              {word.hebrew_word}
            </p>
            <p className="font-mono text-sm text-bridge">{word.phonetic_es}</p>
            <p className="text-sm text-parchment/50">
              {word.spanish_word} · {word.english_word}
            </p>
          </div>
        </div>
        <span className={`shrink-0 text-sm font-semibold ${STATUS_ACCENT[word.status]}`}>
          {STATUS_LABEL[word.status]}
        </span>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-sm tabular-nums text-parchment/60">
          {word.times_seen > 0 ? `${word.times_correct}/${word.times_seen} correct · ${word.accuracy}%` : "Not yet reviewed"}
        </span>
        <div className="flex shrink-0 gap-2">
          {word.status !== "fluent" && (
            <button
              type="button"
              disabled={busy}
              onClick={onMarkFluent}
              className="rounded-lg bg-known/15 px-2.5 py-1 text-xs font-semibold text-known hover:bg-known/25 disabled:opacity-40"
            >
              Mark fluent
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={onReset}
            className="rounded-lg bg-surfacemuted px-2.5 py-1 text-xs font-semibold text-parchment/70 hover:text-parchment disabled:opacity-40"
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}

export function WordTablePage({ onBack }: { onBack: () => void }) {
  const [words, setWords] = useState<WordProgress[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [starredOnly, setStarredOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("hebrew_word");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = () => {
    api
      .getWords()
      .then(setWords)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load your words."));
  };

  useEffect(load, []);

  const handleSortClick = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const visible = useMemo(() => {
    if (!words) return [];
    const needle = search.trim().toLowerCase();
    let rows = words.filter((w) => {
      if (starredOnly && !w.starred) return false;
      if (!needle) return true;
      return (
        w.hebrew_word.includes(needle) ||
        w.spanish_word.toLowerCase().includes(needle) ||
        w.english_word.toLowerCase().includes(needle) ||
        w.phonetic_es.toLowerCase().includes(needle)
      );
    });
    rows = [...rows].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortKey === "hebrew_word") return a.hebrew_word.localeCompare(b.hebrew_word) * dir;
      if (sortKey === "status") return a.status.localeCompare(b.status) * dir;
      if (sortKey === "times_seen") return (a.times_seen - b.times_seen) * dir;
      return (a.accuracy - b.accuracy) * dir;
    });
    return rows;
  }, [words, search, starredOnly, sortKey, sortDir]);

  const handleMarkFluent = async (wordPairId: number) => {
    setBusyId(wordPairId);
    try {
      const updated = await api.markWordFluent(wordPairId);
      setWords((prev) => prev?.map((w) => (w.word_pair_id === wordPairId ? updated : w)) ?? prev);
    } catch {
      // Non-fatal — the row just doesn't update; user can retry.
    } finally {
      setBusyId(null);
    }
  };

  const handleReset = async (wordPairId: number, label: string) => {
    if (!window.confirm(`Reset "${label}" back to unlearned? This clears its progress (not its star).`)) return;
    setBusyId(wordPairId);
    try {
      const updated = await api.resetWord(wordPairId);
      setWords((prev) => prev?.map((w) => (w.word_pair_id === wordPairId ? updated : w)) ?? prev);
    } catch {
      // Non-fatal — the row just doesn't update; user can retry.
    } finally {
      setBusyId(null);
    }
  };

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
          <h1 className="text-2xl font-bold">Your words</h1>
        </div>

        {error && <p className="text-danger">{error}</p>}

        {words && (
          <>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="w-full rounded-xl border border-parchment/15 bg-surfacemuted px-4 py-2.5 text-parchment placeholder:text-parchment/40 focus:border-bridge/50 focus:outline-none"
            />

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs uppercase tracking-wider text-parchment/40">Sort:</span>
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => handleSortClick(opt.key)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    sortKey === opt.key ? "bg-ember text-ink" : "bg-surfacemuted text-parchment/60 hover:text-parchment"
                  }`}
                >
                  {opt.label} {sortKey === opt.key && (sortDir === "asc" ? "↑" : "↓")}
                </button>
              ))}
              <label className="ml-auto flex items-center gap-1.5 text-xs text-parchment/70">
                <input
                  type="checkbox"
                  checked={starredOnly}
                  onChange={(e) => setStarredOnly(e.target.checked)}
                  className="h-3.5 w-3.5 accent-almost"
                />
                Starred only
              </label>
            </div>

            <div className="mt-4 flex flex-col gap-2.5">
              {visible.map((w) => (
                <WordRow
                  key={w.word_pair_id}
                  word={w}
                  busy={busyId === w.word_pair_id}
                  onMarkFluent={() => handleMarkFluent(w.word_pair_id)}
                  onReset={() => handleReset(w.word_pair_id, w.hebrew_word)}
                />
              ))}
              {visible.length === 0 && <p className="py-8 text-center text-parchment/50">No words match.</p>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
