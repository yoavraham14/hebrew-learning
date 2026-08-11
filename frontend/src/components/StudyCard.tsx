import { useEffect, useState } from "react";
import type { CardOut, RatingResult } from "../types";
import { AudioButton } from "./AudioButton";
import { RatingButtons } from "./RatingButtons";

export function StudyCard({
  card,
  onRate,
  rating,
}: {
  card: CardOut;
  onRate: (result: RatingResult) => void;
  rating: boolean;
}) {
  const [revealed, setRevealed] = useState(false);

  // A new card arrived — collapse back to the un-revealed prompt state.
  useEffect(() => {
    setRevealed(false);
  }, [card.word_pair_id]);

  return (
    <div className="w-full rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <div className="mb-6 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-bridge">{card.topic}</span>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-surfacemuted px-2.5 py-1 text-xs text-parchment/70">
            {card.cefr_level}
          </span>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              card.is_review ? "bg-bridge/20 text-bridge" : "bg-ember/20 text-ember"
            }`}
          >
            {card.is_review ? "Review" : "New"}
          </span>
        </div>
      </div>

      <div className="flex flex-col items-center gap-2 py-6 text-center">
        <p className="text-sm font-medium text-parchment/50">{card.part_of_speech}</p>
        <p
          dir={card.prompt_lang === "he" ? "rtl" : "ltr"}
          className="break-words text-5xl font-bold leading-tight sm:text-6xl"
        >
          {card.prompt}
        </p>
      </div>

      {!revealed ? (
        <button
          type="button"
          onClick={() => setRevealed(true)}
          className="mt-4 w-full rounded-2xl bg-ember py-4 text-lg font-bold text-ink transition-transform active:scale-[0.98]"
        >
          Reveal
        </button>
      ) : (
        <div className="mt-2 flex flex-col gap-5">
          <div className="flex animate-reveal-glow items-center justify-center gap-3 rounded-2xl bg-ink/40 p-5">
            <p
              dir={card.reveal_target_lang === "he" ? "rtl" : "ltr"}
              className="text-4xl font-bold text-ember"
            >
              {card.reveal_target_word}
            </p>
            <AudioButton text={card.reveal_target_word} lang={card.reveal_target_lang} />
          </div>

          {card.reveal_phonetic && (
            <p className="animate-reveal-rise text-center font-mono text-lg tracking-wide text-bridge">
              {card.reveal_phonetic}
            </p>
          )}

          <div className="flex animate-reveal-rise justify-center" style={{ animationDelay: "60ms" }}>
            <span className="rounded-full bg-surfacemuted px-3 py-1 text-sm text-parchment/80">
              English: {card.reveal_english}
            </span>
          </div>

          <div
            className="flex animate-reveal-rise flex-col gap-2 border-t border-parchment/10 pt-4"
            style={{ animationDelay: "100ms" }}
          >
            <p dir={card.reveal_target_lang === "he" ? "rtl" : "ltr"} className="text-parchment/90">
              {card.example_target}
            </p>
            <p dir={card.prompt_lang === "he" ? "rtl" : "ltr"} className="text-sm text-parchment/50">
              {card.example_native}
            </p>
          </div>

          <RatingButtons onRate={onRate} disabled={rating} />
        </div>
      )}
    </div>
  );
}
