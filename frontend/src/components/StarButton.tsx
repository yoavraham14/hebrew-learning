import { useState } from "react";
import { api } from "../api/client";

// Usable from a study card (here) or the word table — both just call the
// same POST .../star endpoint, which lazily creates a progress row if the
// word doesn't have one yet (e.g. starring a brand-new, never-rated card).
export function StarButton({
  wordPairId,
  starred: initialStarred,
  onChange,
  className = "",
}: {
  wordPairId: number;
  starred: boolean;
  onChange?: (starred: boolean) => void;
  className?: string;
}) {
  const [starred, setStarred] = useState(initialStarred);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    if (busy) return;
    const next = !starred;
    setStarred(next); // optimistic — starring is low-stakes, worth the snappy feel
    setBusy(true);
    try {
      const result = await api.setStarred(wordPairId, next);
      setStarred(result.starred);
      onChange?.(result.starred);
    } catch {
      setStarred(!next); // revert on failure
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={starred ? "Unstar this word" : "Star this word"}
      aria-pressed={starred}
      className={`inline-flex items-center justify-center rounded-full p-2 transition-colors ${
        starred ? "text-almost" : "text-parchment/30 hover:text-parchment/60"
      } ${className}`}
    >
      <svg viewBox="0 0 24 24" fill={starred ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" className="h-5 w-5" aria-hidden="true">
        <path
          strokeLinejoin="round"
          strokeLinecap="round"
          d="M12 3.5l2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6-4.5-4.2 6.1-.7L12 3.5z"
        />
      </svg>
    </button>
  );
}
