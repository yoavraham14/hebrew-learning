import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { RoundBanner } from "../components/RoundBanner";
import { StudyCard } from "../components/StudyCard";
import type { AnswerResponse, CardResponse, RatingResult, RoundOut } from "../types";

interface RoundState {
  kind: RoundOut["kind"];
  cards: RoundOut["cards"];
  // -1 = banner shown, round not started yet. 0..cards.length-1 = current
  // round card. Reaching cards.length falls back to the normal deck.
  index: number;
}

export function StudyPage() {
  const [deckCard, setDeckCard] = useState<CardResponse | null>(null);
  const [round, setRound] = useState<RoundState | null>(null);
  const [loading, setLoading] = useState(true);
  const [rating, setRating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Forces StudyCard to remount (and its children's local answer state to
  // reset) on every new card, whether from the deck or a round step.
  const [cardKey, setCardKey] = useState(0);

  // A round_due captured from an MC answer, applied only once the user
  // taps Continue on that card's feedback — not before.
  const pendingRoundRef = useRef<RoundOut | null>(null);

  const fetchNext = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await api.nextCard();
      setDeckCard(next);
      setCardKey((k) => k + 1);
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

  // A recovery/mixed round triggered mid-round is ignored, not queued —
  // rounds don't nest.
  const maybeStartRound = (roundDue: RoundOut | null): boolean => {
    if (!roundDue || round) return false;
    setRound({ kind: roundDue.kind, cards: roundDue.cards, index: -1 });
    setCardKey((k) => k + 1);
    return true;
  };

  const handleRate = async (result: RatingResult) => {
    if (!deckCard) return;
    setRating(true);
    let startedRound = false;
    try {
      const res = await api.rateCard(deckCard.word_pair_id, result);
      startedRound = maybeStartRound(res.round_due);
    } catch {
      // Non-fatal — still advance to the next card rather than getting stuck.
    } finally {
      setRating(false);
    }
    if (!startedRound) await fetchNext();
  };

  const handleAnswer = async (selectedWordPairId: number): Promise<AnswerResponse> => {
    const activeCard = round && round.index >= 0 ? round.cards[round.index] : deckCard;
    if (!activeCard) throw new Error("no active card to answer");
    const res = await api.answerCard(activeCard.word_pair_id, selectedWordPairId);
    if (!round && res.round_due) {
      pendingRoundRef.current = res.round_due;
    }
    return res;
  };

  const handleContinue = async () => {
    if (round) {
      const nextIndex = round.index + 1;
      if (nextIndex >= round.cards.length) {
        setRound(null);
        await fetchNext();
      } else {
        setRound({ ...round, index: nextIndex });
        setCardKey((k) => k + 1);
      }
      return;
    }

    const roundDue = pendingRoundRef.current;
    pendingRoundRef.current = null;
    if (roundDue) {
      setRound({ kind: roundDue.kind, cards: roundDue.cards, index: -1 });
      setCardKey((k) => k + 1);
    } else {
      await fetchNext();
    }
  };

  const handleStartRound = () => {
    if (!round) return;
    setRound({ ...round, index: 0 });
    setCardKey((k) => k + 1);
  };

  const activeCard: CardResponse | null = round ? (round.index >= 0 ? round.cards[round.index] : null) : deckCard;
  const showingBanner = round !== null && round.index === -1;

  return (
    <div className="flex w-full flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-md">
        {loading && !activeCard && !showingBanner && (
          <p className="py-16 text-center text-parchment/50">Loading your next word…</p>
        )}

        {error && !activeCard && !showingBanner && (
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

        {showingBanner && round && <RoundBanner kind={round.kind} onStart={handleStartRound} />}

        {activeCard && !showingBanner && (
          <StudyCard
            key={cardKey}
            card={activeCard}
            onRate={handleRate}
            rating={rating}
            onAnswer={handleAnswer}
            onContinue={handleContinue}
          />
        )}
      </div>
    </div>
  );
}
