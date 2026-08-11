export function CardHeader({
  topic,
  cefrLevel,
  isReview,
}: {
  topic: string;
  cefrLevel: string;
  isReview: boolean;
}) {
  return (
    <div className="mb-6 flex items-center justify-between gap-2">
      <span className="text-xs font-semibold uppercase tracking-wider text-bridge">{topic}</span>
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-surfacemuted px-2.5 py-1 text-xs text-parchment/70">{cefrLevel}</span>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            isReview ? "bg-bridge/20 text-bridge" : "bg-ember/20 text-ember"
          }`}
        >
          {isReview ? "Review" : "New"}
        </span>
      </div>
    </div>
  );
}
