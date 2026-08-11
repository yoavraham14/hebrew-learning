import type { AnswerResponse, CardResponse, RatingResult } from "../types";
import { MultipleChoiceExercise } from "./MultipleChoiceExercise";
import { RevealExercise } from "./RevealExercise";

// Dispatches across all five exercise shapes on card.exercise_type. Level 0
// (reveal) is self-rated; levels 1-4 are all objectively-checked multiple
// choice sharing one component (see MultipleChoiceExercise).
export function StudyCard({
  card,
  onRate,
  rating,
  onAnswer,
  onContinue,
}: {
  card: CardResponse;
  onRate: (result: RatingResult) => void;
  rating: boolean;
  onAnswer: (selectedWordPairId: number) => Promise<AnswerResponse>;
  onContinue: () => void;
}) {
  if (card.exercise_type === "reveal") {
    return <RevealExercise card={card} onRate={onRate} rating={rating} />;
  }
  return <MultipleChoiceExercise card={card} onAnswer={onAnswer} onContinue={onContinue} />;
}
