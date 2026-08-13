import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { Direction, ProfilePublic } from "../types";

function AddProfileCard({ onSwitchProfile }: { onSwitchProfile: (slug: string, pin: string) => Promise<void> }) {
  const [displayName, setDisplayName] = useState("");
  const [pin, setPin] = useState("");
  const [direction, setDirection] = useState<Direction>("hebrew_learner");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<ProfilePublic | null>(null);
  const [switching, setSwitching] = useState(false);
  // Kept only long enough to offer "switch to it now" — cleared from the
  // visible input immediately either way, so it doesn't linger on screen.
  const [createdPin, setCreatedPin] = useState("");

  const canCreate = displayName.trim().length > 0 && pin.length >= 4 && !creating;

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const profile = await api.createProfile(displayName.trim(), pin, direction);
      setCreated(profile);
      setCreatedPin(pin);
      setDisplayName("");
      setPin("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the profile — try again.");
    } finally {
      setCreating(false);
    }
  };

  const handleSwitch = async () => {
    if (!created) return;
    setSwitching(true);
    try {
      await onSwitchProfile(created.slug, createdPin);
    } catch {
      setError("Created, but couldn't switch to it automatically — log in as it from the profile picker instead.");
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="mt-6 rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <h2 className="text-xl font-bold">Add a profile</h2>
      <p className="mt-1 text-sm text-parchment/50">
        Create another PIN-protected profile — useful for a third learner, or a fresh start alongside an existing
        one.
      </p>

      <div className="mt-4 flex flex-col gap-3">
        <label className="block">
          <span className="text-sm font-medium text-parchment/70">Name</span>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. Alex"
            className="mt-1 w-full rounded-xl border border-parchment/15 bg-surfacemuted px-4 py-2.5 text-parchment placeholder:text-parchment/40 focus:border-bridge/50 focus:outline-none"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-parchment/70">PIN (4+ digits)</span>
          <input
            type="password"
            inputMode="numeric"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            className="mt-1 w-full rounded-xl border border-parchment/15 bg-surfacemuted px-4 py-2.5 text-parchment focus:border-bridge/50 focus:outline-none"
          />
        </label>

        <div>
          <span className="text-sm font-medium text-parchment/70">Learning direction</span>
          <div className="mt-1 grid grid-cols-2 gap-2">
            {(
              [
                { value: "hebrew_learner", label: "Hebrew learner" },
                { value: "spanish_learner", label: "Spanish learner" },
              ] as const
            ).map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setDirection(opt.value)}
                className={`rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  direction === opt.value ? "bg-ember text-ink" : "bg-surfacemuted text-parchment/60"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className="mt-4 text-danger">{error}</p>}

      {created && (
        <div className="mt-4 rounded-xl bg-known/15 p-4 text-sm text-known">
          <p className="font-semibold">"{created.display_name}" created.</p>
          <button
            type="button"
            onClick={handleSwitch}
            disabled={switching}
            className="mt-2 rounded-lg bg-known/20 px-3 py-1.5 text-xs font-semibold text-known hover:bg-known/30 disabled:opacity-40"
          >
            {switching ? "Switching…" : "Switch to it now"}
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={handleCreate}
        disabled={!canCreate}
        className="mt-4 w-full rounded-2xl bg-ember py-3.5 font-bold text-ink transition-transform active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
      >
        {creating ? "Creating…" : "Create profile"}
      </button>
    </div>
  );
}

function DangerZoneCard({ profileSlug }: { profileSlug: string }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const canReset = password.length > 0 && confirmation === "RESET" && !resetting;

  const handleReset = async () => {
    if (!window.confirm("This permanently deletes all progress for this profile. Are you absolutely sure?")) {
      return;
    }
    setResetting(true);
    setError(null);
    try {
      await api.resetProfile(profileSlug, password, confirmation);
      setDone(true);
      setPassword("");
      setConfirmation("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed — check the password and try again.");
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="mt-6 rounded-3xl border-2 border-danger/30 bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
      <h2 className="text-xl font-bold text-danger">Danger zone</h2>
      <p className="mt-1 text-sm text-parchment/50">
        Permanently erases all progress for this profile — every word's learning state, your streak, and your
        activity history. This cannot be undone. Your PIN and settings are not affected.
      </p>

      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-4 rounded-xl bg-danger/15 px-4 py-2.5 text-sm font-semibold text-danger hover:bg-danger/25"
        >
          Reset this profile's progress
        </button>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          <label className="block">
            <span className="text-sm font-medium text-parchment/70">Reset password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-xl border border-danger/30 bg-surfacemuted px-4 py-2.5 text-parchment focus:border-danger/60 focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-parchment/70">
              Type <span className="font-mono text-danger">RESET</span> to confirm
            </span>
            <input
              type="text"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
              className="mt-1 w-full rounded-xl border border-danger/30 bg-surfacemuted px-4 py-2.5 font-mono text-parchment focus:border-danger/60 focus:outline-none"
            />
          </label>

          {error && <p className="text-danger">{error}</p>}
          {done && <p className="text-known">Reset complete — this profile's progress is gone.</p>}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setPassword("");
                setConfirmation("");
                setError(null);
              }}
              className="rounded-xl bg-surfacemuted px-4 py-2.5 text-sm font-semibold text-parchment/70"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReset}
              disabled={!canReset}
              className="flex-1 rounded-xl bg-danger px-4 py-2.5 text-sm font-bold text-ink disabled:cursor-not-allowed disabled:opacity-40"
            >
              {resetting ? "Resetting…" : "Permanently reset"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Grown across the progress-page feature pass's stages — fluency threshold
// (stage B), daily goal (stage C), add-user + reset (stage G).
export function SettingsPage({
  profile,
  onUpdate,
  onSwitchProfile,
}: {
  profile: ProfilePublic;
  onUpdate: (updated: ProfilePublic) => void;
  onSwitchProfile: (slug: string, pin: string) => Promise<void>;
}) {
  const [threshold, setThreshold] = useState(profile.fluency_threshold);
  const [dailyGoal, setDailyGoal] = useState(profile.daily_goal);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty = threshold !== profile.fluency_threshold || dailyGoal !== profile.daily_goal;

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.updateSettings({ fluency_threshold: threshold, daily_goal: dailyGoal });
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
      <div className="w-full max-w-md">
        <div className="rounded-3xl bg-surface p-6 shadow-2xl shadow-black/30 sm:p-8">
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

          <div className="mt-6 border-t border-parchment/10 pt-6">
            <label htmlFor="daily-goal" className="block text-sm font-medium text-parchment/70">
              Daily goal
            </label>
            <p className="mt-1 text-sm text-parchment/50">
              Target number of reviews per day — shown as a progress card on the Progress tab.
            </p>
            <input
              id="daily-goal"
              type="number"
              min={1}
              max={200}
              value={dailyGoal}
              onChange={(e) => setDailyGoal(Number(e.target.value))}
              className="mt-3 w-24 rounded-xl border border-parchment/15 bg-surfacemuted px-4 py-2.5 text-lg font-semibold text-parchment focus:border-bridge/50 focus:outline-none"
            />
          </div>

          {error && <p className="mt-4 text-danger">{error}</p>}
          {saved && !error && <p className="mt-4 text-known">Saved.</p>}

          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !dirty}
            className="mt-6 w-full rounded-2xl bg-ember py-4 text-lg font-bold text-ink transition-transform active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>

        <AddProfileCard onSwitchProfile={onSwitchProfile} />
        <DangerZoneCard profileSlug={profile.slug} />
      </div>
    </div>
  );
}
