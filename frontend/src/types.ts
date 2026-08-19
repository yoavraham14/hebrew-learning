export type Lang = "he" | "es";

export type RatingResult = "knew_it" | "almost" | "didnt_know";

export type ExerciseType = "reveal" | "multiple_choice" | "reverse" | "audio_only" | "fill_blank";

export interface ProfilePublic {
  slug: string;
  display_name: string;
  native_lang: Lang;
  target_lang: Lang;
  fluency_threshold: number;
  daily_goal: number;
  weekly_video_goal: number;
}

// Level 0 — the original passive reveal-and-self-rate card.
export interface RevealCardOut {
  exercise_type: "reveal";
  word_pair_id: number;
  is_review: boolean;
  starred: boolean;
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
  starred: boolean;
  part_of_speech: string;
  cefr_level: string;
  topic: string;

  prompt_text: string | null;
  prompt_lang: Lang | null;
  prompt_phonetic: string | null;

  audio_text: string | null;
  audio_lang: Lang | null;

  fill_blank_sentence: string | null;
  fill_blank_sentence_phonetic: string | null;

  options: ExerciseOption[];
}

export type CardResponse = RevealCardOut | MultipleChoiceCardOut;

export interface RoundOut {
  kind: "recovery" | "mixed" | "sentence";
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
  words_fluent: number;
  total_verified_words: number;
  current_streak: number;
  longest_streak: number;
  due_today: number;
  daily_goal: number;
  today_review_count: number;
  videos_watched: number;
  videos_watched_this_week: number;
  weekly_video_goal: number;
}

export interface WordProgress {
  word_pair_id: number;
  hebrew_word: string;
  spanish_word: string;
  english_word: string;
  phonetic_es: string;
  topic: string;
  cefr_level: string;
  status: "new" | "learning" | "fluent";
  starred: boolean;
  times_seen: number;
  times_correct: number;
  accuracy: number;
  fluent_at: string | null;
}

export interface ActivityDay {
  activity_date: string; // YYYY-MM-DD
  review_count: number;
  correct_count: number;
}

export interface WeeklySummary {
  words_added: number;
  words_became_fluent: number;
  days_studied: number;
  reviews_this_week: number;
  accuracy_this_week: number;
  accuracy_last_week: number;
}

export interface Video {
  id: number;
  title: string;
  youtube_video_id: string;
  level: string;
  topic: string;
  ordering: number;
  watched: boolean;
}

export type Direction = "hebrew_learner" | "spanish_learner";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  profile: ProfilePublic;
}
