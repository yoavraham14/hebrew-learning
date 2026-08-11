import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { StudyCard } from "../components/StudyCard";
import type { CardOut, RatingResult } from "../types";

export function StudyPage() {
  const [card, setCard] = useState<CardOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchNext = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.nextCard();
      setCard(next);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't load the next word. Check your connection and try again.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNext();
  }, [fetchNext]);

  const handleRate = async (result: RatingResult) => {
    if (!card) return;
    setRating(true);
    try {
      await api.rateCard(card.word_pair_id, result);
    } catch {
      // Non-fatal — still advance to the next card rather than getting stuck.
    } finally {
      setRating(false);
      await fetchNext();
    }
  };

  return (
    <div className="flex w-full flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-md">
        {loading && !card && <p className="py-16 text-center text-parchment/50">Loading your next word…</p>}

        {error && !card && (
          <div className="rounded-2xl bg-danger/15 px-5 py-6 text-center">
            <p className="mb-4 text-danger">{error}</p>
            <button
              type="button"
              onClick={fetchNext}
              className="rounded-xl bg-ember px-5 py-2.5 font-semibold text-ink"
            >
              Try again
            </button>
          </div>
        )}

        {card && <StudyCard card={card} onRate={handleRate} rating={rating} />}
      </div>
    </div>
  );
}
