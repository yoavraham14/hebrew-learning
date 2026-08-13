import { useEffect, useMemo, useRef } from "react";
import type { ActivityDay } from "../types";

const WEEKS_VISIBLE = 20;
const DAY_MS = 24 * 60 * 60 * 1000;

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function intensity(count: number): string {
  if (count === 0) return "bg-surfacemuted";
  if (count < 5) return "bg-ember/30";
  if (count < 10) return "bg-ember/60";
  if (count < 20) return "bg-ember/85";
  return "bg-ember";
}

// GitHub-style contribution grid. A true 2D grid doesn't collapse into a
// stacked mobile layout the way the word table did — this is the case
// where a contained horizontal scroll (not viewport overflow) is the
// right call, not a workaround. Auto-scrolled to show the most recent
// weeks on mount.
export function ActivityCalendar({ days }: { days: ActivityDay[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const byDate = useMemo(() => {
    const map = new Map<string, ActivityDay>();
    for (const d of days) map.set(d.activity_date, d);
    return map;
  }, [days]);

  const weeks = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    // Align the grid's last column to the end of the current week (Saturday).
    // getDay() is 0 (Sun) .. 6 (Sat), so this is always 0-6, never negative.
    const daysUntilSaturday = 6 - today.getDay();
    const gridEnd = new Date(today.getTime() + daysUntilSaturday * DAY_MS);
    const totalDays = WEEKS_VISIBLE * 7;
    const gridStart = new Date(gridEnd.getTime() - (totalDays - 1) * DAY_MS);

    const cols: { date: Date; count: number }[][] = [];
    for (let w = 0; w < WEEKS_VISIBLE; w++) {
      const col: { date: Date; count: number }[] = [];
      for (let d = 0; d < 7; d++) {
        const date = new Date(gridStart.getTime() + (w * 7 + d) * DAY_MS);
        const entry = byDate.get(isoDate(date));
        col.push({ date, count: entry?.review_count ?? 0 });
      }
      cols.push(col);
    }
    return cols;
  }, [byDate]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [weeks]);

  const today = isoDate(new Date());

  return (
    <div className="rounded-2xl bg-surface p-5">
      <p className="text-sm font-semibold uppercase tracking-wider text-bridge">Activity</p>
      <div ref={scrollRef} className="mt-3 overflow-x-auto pb-1">
        <div className="flex gap-1">
          {weeks.map((col, wi) => (
            <div key={wi} className="flex flex-col gap-1">
              {col.map((cell, di) => {
                const iso = isoDate(cell.date);
                const isFuture = iso > today;
                return (
                  <div
                    key={di}
                    title={`${iso}: ${cell.count} review${cell.count === 1 ? "" : "s"}`}
                    className={`h-3 w-3 rounded-sm ${isFuture ? "bg-transparent" : intensity(cell.count)}`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-xs text-parchment/40">
        <span>Less</span>
        <span className="h-3 w-3 rounded-sm bg-surfacemuted" />
        <span className="h-3 w-3 rounded-sm bg-ember/30" />
        <span className="h-3 w-3 rounded-sm bg-ember/60" />
        <span className="h-3 w-3 rounded-sm bg-ember/85" />
        <span className="h-3 w-3 rounded-sm bg-ember" />
        <span>More</span>
      </div>
    </div>
  );
}
