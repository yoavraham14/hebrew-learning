import { useEffect, useState } from "react";
import { api } from "./api/client";
import { StreakBadge } from "./components/StreakBadge";
import { useAuth } from "./hooks/useAuth";
import { ProfilePicker } from "./pages/ProfilePicker";
import { ProgressPage } from "./pages/ProgressPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudyPage } from "./pages/StudyPage";
import { WordTablePage } from "./pages/WordTablePage";
import type { ProfilePublic } from "./types";

// "words" is reached by clicking the Seen stat tile, not from the main
// nav — it behaves like a drill-down (has its own Back button) rather
// than a peer tab.
type View = "study" | "progress" | "settings" | "words";

function AuthenticatedApp({
  profile,
  onLogout,
  onUpdateProfile,
}: {
  profile: ProfilePublic;
  onLogout: () => void;
  onUpdateProfile: (updated: ProfilePublic) => void;
}) {
  const [view, setView] = useState<View>("study");
  const [streak, setStreak] = useState<number | null>(null);

  useEffect(() => {
    // Refresh the nav streak badge whenever the visible tab changes — cheap
    // and keeps it reasonably fresh without prop-drilling every rating.
    api
      .getProgress()
      .then((p) => setStreak(p.current_streak))
      .catch(() => undefined);
  }, [view]);

  return (
    <div className="mx-auto flex min-h-full max-w-2xl flex-col">
      <header className="flex items-center justify-between px-4 py-4 sm:px-6">
        <div>
          <p className="text-sm text-parchment/50">Studying as</p>
          <p className="font-semibold">{profile.display_name}</p>
        </div>
        <div className="flex items-center gap-3">
          {streak !== null && <StreakBadge streak={streak} />}
          <button
            type="button"
            onClick={onLogout}
            className="rounded-full bg-surfacemuted px-3 py-1.5 text-sm text-parchment/70 hover:text-parchment"
          >
            Log out
          </button>
        </div>
      </header>

      <nav className="flex gap-2 px-4 pb-2 sm:px-6">
        {(["study", "progress", "settings"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => setView(v)}
            className={`rounded-full px-4 py-2 text-sm font-medium capitalize transition-colors ${
              view === v ? "bg-ember text-ink" : "bg-surface text-parchment/60 hover:text-parchment"
            }`}
          >
            {v}
          </button>
        ))}
      </nav>

      <main className="flex flex-1 flex-col">
        {view === "study" && <StudyPage />}
        {view === "progress" && <ProgressPage onOpenWords={() => setView("words")} />}
        {view === "settings" && <SettingsPage profile={profile} onUpdate={onUpdateProfile} />}
        {view === "words" && <WordTablePage onBack={() => setView("progress")} />}
      </main>
    </div>
  );
}

export default function App() {
  const { profile, login, logout, updateProfile, isAuthenticated } = useAuth();

  if (!isAuthenticated || !profile) {
    return <ProfilePicker onLogin={login} />;
  }

  return <AuthenticatedApp profile={profile} onLogout={logout} onUpdateProfile={updateProfile} />;
}
