import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProfilePublic } from "../types";

const SCRIPT_LABEL: Record<string, string> = {
  es: "Español",
  he: "עברית",
};

export function ProfilePicker({ onLogin }: { onLogin: (slug: string, pin: string) => Promise<void> }) {
  const [profiles, setProfiles] = useState<ProfilePublic[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ProfilePublic | null>(null);
  const [pin, setPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProfiles()
      .then(setProfiles)
      .catch((err: unknown) => setLoadError(err instanceof ApiError ? err.message : "Couldn't reach the server."));
  }, []);

  const handleSelect = (profile: ProfilePublic) => {
    setSelected(profile);
    setPin("");
    setLoginError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || pin.length === 0) return;
    setSubmitting(true);
    setLoginError(null);
    try {
      await onLogin(selected.slug, pin);
    } catch (err) {
      setLoginError(err instanceof ApiError ? err.message : "Something went wrong.");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-5 py-10">
      <div className="w-full max-w-sm">
        <h1 className="mb-1 text-center text-3xl font-bold">Lingua</h1>
        <p className="mb-8 text-center text-parchment/60">
          {selected ? `Enter the PIN for ${selected.display_name}` : "Who's studying?"}
        </p>

        {loadError && (
          <p className="rounded-xl bg-danger/15 px-4 py-3 text-center text-sm text-danger">{loadError}</p>
        )}

        {!selected && profiles && (
          <div className="flex flex-col gap-3">
            {profiles.map((p) => (
              <button
                key={p.slug}
                type="button"
                onClick={() => handleSelect(p)}
                className="rounded-2xl border border-parchment/10 bg-surface px-5 py-4 text-left transition-colors hover:border-ember/40 hover:bg-surfacemuted"
              >
                <p className="text-lg font-semibold">{p.display_name}</p>
                <p dir="rtl" className="text-sm text-parchment/50">
                  {SCRIPT_LABEL[p.native_lang] ?? p.native_lang} → {SCRIPT_LABEL[p.target_lang] ?? p.target_lang}
                </p>
              </button>
            ))}
          </div>
        )}

        {!selected && !profiles && !loadError && (
          <p className="text-center text-parchment/50">Loading profiles…</p>
        )}

        {selected && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <input
              type="password"
              inputMode="numeric"
              autoFocus
              autoComplete="off"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="PIN"
              className="rounded-2xl border border-parchment/15 bg-surface px-5 py-4 text-center text-2xl tracking-[0.5em] text-parchment placeholder:tracking-normal placeholder:text-parchment/30"
            />
            {loginError && <p className="text-center text-sm text-danger">{loginError}</p>}
            <button
              type="submit"
              disabled={submitting || pin.length === 0}
              className="rounded-2xl bg-ember py-3.5 font-bold text-ink transition-transform active:scale-[0.98] disabled:opacity-40"
            >
              {submitting ? "Checking…" : "Continue"}
            </button>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-center text-sm text-parchment/50 hover:text-parchment/80"
            >
              ← Choose a different profile
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
