export type Lang = "he" | "es";

export type RatingResult = "knew_it" | "almost" | "didnt_know";

export type ExerciseType = "reveal" | "multiple_choice" | "reverse" | "audio_only" | "fill_blank";

export interface ProfilePublic {
  slug: string;
  display_name: string;
  native_lang: Lang;
  target_lang: Lang;
}

// Level 0 — the original passive reveal-and-self-rate card.
export interface RevealCardOut {
  exercise_type: "reveal";
  word_pair_id: number;
  is_review: boolean;
  part_of_speech: string;
  cefr_level: string;
  topic: string;
  prompt: string;
  prompt_lang: Lang;
  reveal_english: string;
  reveal_target_word: string;
  reveal_target_lang: Lang;
  reveal_phonetic: string | null;
  example_target: string;
  example_native: string;
}

export interface ExerciseOption {
  word_pair_id: number;
  text: string;
  // Set only when `text` is Hebrew script and the viewing profile can't
  // read it — script and transliteration are always shown together, never
  // script alone. See ExerciseOptionGrid.
  phonetic: string | null;
}

// Levels 1-4 — always multiple-choice, never free text.
export interface MultipleChoiceCardOut {
  exercise_type: "multiple_choice" | "reverse" | "audio_only" | "fill_blank";
  word_pair_id: number;
  is_review: boolean;
  part_of_speech: string;
  cefr_level: string;
  topic: string;

  prompt_text: string | null;
  prompt_lang: Lang | null;
  prompt_phonetic: string | null;

  audio_text: string | null;
  audio_lang: Lang | null;

  fill_blank_sentence: string | null;

  options: ExerciseOption[];
}

export type CardResponse = RevealCardOut | MultipleChoiceCardOut;

export interface RoundOut {
  kind: "recovery" | "mixed";
  cards: MultipleChoiceCardOut[];
}

export interface RateResponse {
  box: number;
  next_review_at: string;
  exercise_level: number;
  round_due: RoundOut | null;
}

export interface AnswerResponse {
  correct: boolean;
  correct_word_pair_id: number;
  correct_text: string;
  box: number;
  exercise_level: number;
  round_due: RoundOut | null;
}

export interface ProgressOut {
  words_seen: number;
  words_known: number;
  current_streak: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  profile: ProfilePublic;
}
