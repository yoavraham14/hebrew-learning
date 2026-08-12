import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProfilePublic } from "../types";

// Minimal for now (Stage B of the progress-page feature pass) — just the
// fluency threshold. Later stages (daily goal, add-user, reset) extend
// this same screen rather than scattering settings across the app.
export function SettingsPage({
  profile,
  onUpdate,
}: {
  profile: ProfilePublic;
  onUpdate: (updated: ProfilePublic) => void;
}) {
  const [threshold, setThreshold] = useState(profile.fluency_threshold);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.updateSettings({ fluency_threshold: threshold });
      onUpdate(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save — check your connection and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex w-full flex-col items-center px-4 py-6 sm:py-10">
      <div className="w-full max-w-md rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
        <h1 className="text-2xl font-bold">Settings</h1>

        <div className="mt-6">
          <label htmlFor="fluency-threshold" className="block text-sm font-medium text-parchment/70">
            Fluency threshold
          </label>
          <p className="mt-1 text-sm text-parchment/50">
            How many times you need to mark a word "knew it" before it counts as fluent and stops showing up in
            regular study. Fluent words still resurface occasionally in mixed review rounds.
          </p>
          <input
            id="fluency-threshold"
            type="number"
            min={1}
            max={50}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="mt-3 w-24 rounded-xl border border-parchment/15 bg-surfacemuted px-4 py-2.5 text-lg font-semibold text-parchment focus:border-bridge/50 focus:outline-none"
          />
        </div>

        {error && <p className="mt-4 text-danger">{error}</p>}
        {saved && !error && <p className="mt-4 text-known">Saved.</p>}

        <button
          type="button"
          onClick={handleSave}
          disabled={saving || threshold === profile.fluency_threshold}
          className="mt-6 w-full rounded-2xl bg-ember py-4 text-lg font-bold text-ink transition-transform active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
