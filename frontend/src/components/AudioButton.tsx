import type { Lang } from "../types";

const SPEECH_LOCALE: Record<Lang, string> = {
  he: "he-IL",
  es: "es-ES",
};

// Vite only exposes VITE_-prefixed vars, read at build time.
const API_URL = import.meta.env.VITE_API_URL as string;

export function speak(text: string, lang: Lang): void {
  if (!("speechSynthesis" in window)) return; // no fallback/detection for missing browser voices
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = SPEECH_LOCALE[lang];
  window.speechSynthesis.cancel(); // interrupt anything already playing
  window.speechSynthesis.speak(utterance);
}

// Hebrew pronunciation depends on a per-device installed voice when using
// the browser's speechSynthesis API — many devices simply don't have one,
// and there's no reliable way to detect that in advance. For Hebrew, prefer
// the backend's server-generated audio (eSpeak NG, cached per word — see
// app/services/audio.py) which sounds the same on every device. Falls back
// to speechSynthesis if that request ever fails (e.g. eSpeak NG isn't
// installed on the backend host either) — same behavior as before this
// feature existed, never a dead end.
function playHebrewAudio(wordPairId: number, fallbackText: string): void {
  let fellBack = false;
  const fallback = () => {
    if (fellBack) return;
    fellBack = true;
    speak(fallbackText, "he");
  };

  const audioEl = new Audio(`${API_URL}/api/audio/word-pairs/${wordPairId}`);
  audioEl.addEventListener("error", fallback);
  audioEl.play().catch(fallback);
}

export function playPronunciation(text: string, lang: Lang, wordPairId?: number): void {
  if (lang === "he" && wordPairId != null) {
    playHebrewAudio(wordPairId, text);
  } else {
    speak(text, lang);
  }
}

export function AudioButton({
  text,
  lang,
  wordPairId,
  className = "",
}: {
  text: string;
  lang: Lang;
  // When set and lang === "he", plays the backend's cached pronunciation
  // instead of relying on a device-installed browser voice. Omit for
  // Spanish (Latin-script TTS voices are near-universal) or when no
  // word_pair_id is available.
  wordPairId?: number;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => playPronunciation(text, lang, wordPairId)}
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
