export type Lang = "he" | "es";

export type RatingResult = "knew_it" | "almost" | "didnt_know";

export interface ProfilePublic {
  slug: string;
  display_name: string;
  native_lang: Lang;
  target_lang: Lang;
}

export interface CardOut {
  word_pair_id: number;
  prompt: string;
  prompt_lang: Lang;
  reveal_english: string;
  reveal_target_word: string;
  reveal_target_lang: Lang;
  reveal_phonetic: string | null;
  example_target: string;
  example_native: string;
  part_of_speech: string;
  cefr_level: string;
  topic: string;
  is_review: boolean;
}

export interface RateResponse {
  box: number;
  next_review_at: string;
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
