// Mirrors backend/app/schemas.py's _HEBREW_RANGE — used purely to pick RTL
// vs LTR direction for a piece of display text we didn't otherwise get a
// `lang` tag for (e.g. individual ExerciseOption.text values).
const HEBREW_RANGE = /[֐-׿]/;

export function isHebrewText(text: string): boolean {
  return HEBREW_RANGE.test(text);
}
