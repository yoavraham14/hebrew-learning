import { useState } from "react";
import type { RatingResult, RevealCardOut } from "../types";
import { AudioButton } from "./AudioButton";
import { CardHeader } from "./CardHeader";
import { RatingButtons } from "./RatingButtons";

// Level 0 — the original passive reveal-and-self-rate card. Unchanged in
// substance from before the exercise ladder; just extracted out of
// StudyCard.tsx so that file can dispatch across all five exercise shapes.
export function RevealExercise({
  card,
  onRate,
  rating,
}: {
  card: RevealCardOut;
  onRate: (result: RatingResult) => void;
  rating: boolean;
}) {
  const [revealed, setRevealed] = useState(false);

  return (
    <div className="w-full rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <CardHeader topic={card.topic} cefrLevel={card.cefr_level} isReview={card.is_review} />

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
            <p dir={card.reveal_target_lang === "he" ? "rtl" : "ltr"} className="text-4xl font-bold text-ember">
              {card.reveal_target_word}
            </p>
            <AudioButton
              text={card.reveal_target_word}
              lang={card.reveal_target_lang}
              wordPairId={card.word_pair_id}
            />
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
