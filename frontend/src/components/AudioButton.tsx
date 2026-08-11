import type { Lang } from "../types";

const SPEECH_LOCALE: Record<Lang, string> = {
  he: "he-IL",
  es: "es-ES",
};

function speak(text: string, lang: Lang): void {
  if (!("speechSynthesis" in window)) return; // no fallback/detection in v1 — see SPEC.md §6
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = SPEECH_LOCALE[lang];
  window.speechSynthesis.cancel(); // interrupt anything already playing
  window.speechSynthesis.speak(utterance);
}

export function AudioButton({ text, lang, className = "" }: { text: string; lang: Lang; className?: string }) {
  return (
    <button
      type="button"
      onClick={() => speak(text, lang)}
      aria-label="Play pronunciation"
      className={`inline-flex items-center justify-center rounded-full bg-ember/15 text-ember hover:bg-ember/25 active:scale-95 transition-all p-2.5 ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
        <path
          d="M4 9v6h4l5 5V4L8 9H4z"
          fill="currentColor"
        />
        <path
          d="M16.5 8.5a5 5 0 0 1 0 7"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path
          d="M18.8 6a8.5 8.5 0 0 1 0 12"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          opacity="0.6"
        />
      </svg>
    </button>
  );
}
