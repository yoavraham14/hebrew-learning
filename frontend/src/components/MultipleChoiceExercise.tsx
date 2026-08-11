import { useEffect, useState } from "react";
import type { AnswerResponse, MultipleChoiceCardOut } from "../types";
import { AudioButton, speak } from "./AudioButton";
import { CardHeader } from "./CardHeader";
import { ExerciseOptionGrid } from "./ExerciseOptionGrid";
import { isHebrewText } from "../lib/text";

// Levels 1-4 (multiple_choice / reverse / audio_only / fill_blank) — all
// objectively-checked multiple choice, sharing one answer/feedback flow.
// They differ only in the prompt area above the options grid.
export function MultipleChoiceExercise({
  card,
  onAnswer,
  onContinue,
}: {
  card: MultipleChoiceCardOut;
  onAnswer: (selectedWordPairId: number) => Promise<AnswerResponse>;
  onContinue: () => void;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [answering, setAnswering] = useState(false);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // audio_only has no visible prompt at all — the audio itself IS the
  // prompt, so it plays automatically the moment the card appears. (Tap-to-
  // replay via AudioButton still works if the browser blocks autoplay
  // before any user gesture this session — e.g. iOS Safari's first play.)
  useEffect(() => {
    if (card.exercise_type === "audio_only" && card.audio_text && card.audio_lang) {
      speak(card.audio_text, card.audio_lang);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card.word_pair_id, card.exercise_type]);

  const handleSelect = async (id: number) => {
    if (answering || result) return;
    setSelectedId(id);
    setAnswering(true);
    setError(null);
    try {
      const res = await onAnswer(id);
      setResult(res);
    } catch {
      setError("Couldn't submit your answer. Check your connection and try again.");
      setSelectedId(null);
    } finally {
      setAnswering(false);
    }
  };

  return (
    <div className="w-full rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <CardHeader topic={card.topic} cefrLevel={card.cefr_level} isReview={card.is_review} />

      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <p className="text-sm font-medium text-parchment/50">{card.part_of_speech}</p>

        {card.exercise_type === "audio_only" ? (
          <div className="flex flex-col items-center gap-3 py-2">
            <AudioButton
              text={card.audio_text ?? ""}
              lang={card.audio_lang ?? "he"}
              className="!p-6 [&_svg]:h-8 [&_svg]:w-8"
            />
            <p className="text-sm text-parchment/50">Tap to hear the word</p>
          </div>
        ) : card.exercise_type === "fill_blank" ? (
          <p
            dir={card.fill_blank_sentence && isHebrewText(card.fill_blank_sentence) ? "rtl" : "ltr"}
            className="break-words text-3xl font-bold leading-snug sm:text-4xl"
          >
            {card.fill_blank_sentence}
          </p>
        ) : (
          <div className="flex items-center gap-3">
            <p
              dir={card.prompt_lang === "he" ? "rtl" : "ltr"}
              className="break-words text-5xl font-bold leading-tight sm:text-6xl"
            >
              {card.prompt_text}
            </p>
            {card.exercise_type === "reverse" && card.audio_text && card.audio_lang && (
              <AudioButton text={card.audio_text} lang={card.audio_lang} />
            )}
          </div>
        )}

        {card.prompt_phonetic && card.exercise_type !== "audio_only" && (
          <p className="font-mono text-lg tracking-wide text-bridge">{card.prompt_phonetic}</p>
        )}
      </div>

      <ExerciseOptionGrid
        options={card.options}
        selectedId={selectedId}
        correctId={result ? result.correct_word_pair_id : null}
        locked={answering}
        onSelect={handleSelect}
      />

      <div aria-live="polite" className="mt-4 min-h-6 text-center">
        {result &&
          (result.correct ? (
            <p className="font-semibold text-known">Correct!</p>
          ) : (
            <p className="font-semibold text-danger">
              Not quite — the answer was <span className="font-mono">{result.correct_text}</span>
            </p>
          ))}
        {error && <p className="text-danger">{error}</p>}
      </div>

      {result && (
        <button
          type="button"
          onClick={onContinue}
          className="mt-2 w-full animate-reveal-rise rounded-2xl bg-ember py-4 text-lg font-bold text-ink transition-transform active:scale-[0.98]"
        >
          Continue
        </button>
      )}
    </div>
  );
}
