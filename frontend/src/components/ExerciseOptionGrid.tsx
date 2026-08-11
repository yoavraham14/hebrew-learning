import type { ExerciseOption } from "../types";
import { isHebrewText } from "../lib/text";

// Shared by all four multiple-choice exercise types (levels 1-4). Whenever
// an option's text is Hebrew script, its phonetic transliteration is
// rendered right alongside it at real visual weight — never a small gray
// afterthought — because for the Spanish-native learner this line, not the
// script, is what they can actually act on. That pairing is guaranteed by
// the backend (ExerciseOption.phonetic is only ever null when the viewing
// profile can read the script natively); this component just never
// suppresses it.
export function ExerciseOptionGrid({
  options,
  selectedId,
  correctId,
  locked = false,
  onSelect,
}: {
  options: ExerciseOption[];
  selectedId: number | null;
  correctId: number | null;
  // True while an answer request is in flight, in addition to once
  // correctId is known — prevents a second tap racing the first.
  locked?: boolean;
  onSelect: (wordPairId: number) => void;
}) {
  const answered = correctId !== null;
  const disabled = answered || locked;

  return (
    <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
      {options.map((opt) => {
        const isCorrect = answered && opt.word_pair_id === correctId;
        const isWrongPick = answered && opt.word_pair_id === selectedId && opt.word_pair_id !== correctId;
        const isDimmed = answered && !isCorrect && !isWrongPick;

        return (
          <button
            key={opt.word_pair_id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(opt.word_pair_id)}
            className={[
              "rounded-2xl border-2 p-4 text-left transition-all disabled:cursor-not-allowed",
              !answered && "border-parchment/15 bg-surfacemuted hover:border-bridge/50 active:scale-[0.98]",
              isCorrect && "border-known bg-known/15",
              isWrongPick && "border-danger bg-danger/15 animate-incorrect-shake",
              isDimmed && "border-parchment/10 bg-surfacemuted/50 opacity-50",
              isCorrect && opt.word_pair_id === selectedId && "animate-correct-glow",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span
              dir={isHebrewText(opt.text) ? "rtl" : "ltr"}
              className={`block break-words text-xl font-semibold ${
                isCorrect ? "text-known" : isWrongPick ? "text-danger" : "text-parchment"
              }`}
            >
              {opt.text}
            </span>
            {opt.phonetic && (
              <span className="mt-1 block font-mono text-base tracking-wide text-bridge">{opt.phonetic}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
