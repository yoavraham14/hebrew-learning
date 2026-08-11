import type { RatingResult } from "../types";

const OPTIONS: { result: RatingResult; label: string; classes: string }[] = [
  {
    result: "didnt_know",
    label: "Didn't know",
    classes: "bg-danger/15 text-danger border-danger/40 hover:bg-danger/25",
  },
  {
    result: "almost",
    label: "Almost",
    classes: "bg-almost/15 text-almost border-almost/40 hover:bg-almost/25",
  },
  {
    result: "knew_it",
    label: "Knew it",
    classes: "bg-known/15 text-known border-known/40 hover:bg-known/25",
  },
];

export function RatingButtons({
  onRate,
  disabled,
}: {
  onRate: (result: RatingResult) => void;
  disabled?: boolean;
}) {
  return (
    <div className="grid grid-cols-3 gap-2.5 w-full animate-reveal-rise" style={{ animationDelay: "150ms" }}>
      {OPTIONS.map((opt) => (
        <button
          key={opt.result}
          type="button"
          disabled={disabled}
          onClick={() => onRate(opt.result)}
          className={`rounded-xl border px-2 py-3.5 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${opt.classes}`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
