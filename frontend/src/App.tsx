import { useEffect, useState } from "react";
import { api } from "./api/client";
import { StreakBadge } from "./components/StreakBadge";
import { useAuth } from "./hooks/useAuth";
import { HelpPage } from "./pages/HelpPage";
import { ProfilePicker } from "./pages/ProfilePicker";
import { ProgressPage } from "./pages/ProgressPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StudyPage } from "./pages/StudyPage";
import { VideoLibraryPage } from "./pages/VideoLibraryPage";
import { WeeklySummaryPage } from "./pages/WeeklySummaryPage";
import { WordTablePage } from "./pages/WordTablePage";
import type { ProfilePublic } from "./types";

// "words" and "weekly" are reached by drilling down from Progress, not
// from the main nav — they behave like detail screens (their own Back
// button) rather than peer tabs. "help" is reached from the header's "?".
// "videos" IS a peer tab — the video library is a standalone destination,
// not a Progress sub-page.
type View = "study" | "progress" | "videos" | "settings" | "words" | "weekly";

function AuthenticatedApp({
  profile,
  onLogout,
  onUpdateProfile,
  onSwitchProfile,
}: {
  profile: ProfilePublic;
  onLogout: () => void;
  onUpdateProfile: (updated: ProfilePublic) => void;
  onSwitchProfile: (slug: string, pin: string) => Promise<void>;
}) {
  const [view, setView] = useState<View>("study");
  const [showHelp, setShowHelp] = useState(false);
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
            onClick={() => setShowHelp(true)}
            aria-label="Help"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-surfacemuted text-sm font-bold text-parchment/70 hover:text-parchment"
          >
            ?
          </button>
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
        {(["study", "progress", "videos", "settings"] as const).map((v) => (
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
        {view === "progress" && (
          <ProgressPage
            profileSlug={profile.slug}
            onOpenWords={() => setView("words")}
            onOpenWeeklySummary={() => setView("weekly")}
          />
        )}
        {view === "videos" && <VideoLibraryPage />}
        {view === "settings" && (
          <SettingsPage profile={profile} onUpdate={onUpdateProfile} onSwitchProfile={onSwitchProfile} />
        )}
        {view === "words" && <WordTablePage onBack={() => setView("progress")} />}
        {view === "weekly" && <WeeklySummaryPage onBack={() => setView("progress")} />}
      </main>

      {showHelp && <HelpPage onClose={() => setShowHelp(false)} />}
    </div>
  );
}

export default function App() {
  const { profile, login, logout, updateProfile, isAuthenticated } = useAuth();

  if (!isAuthenticated || !profile) {
    return <ProfilePicker onLogin={login} />;
  }

  return (
    <AuthenticatedApp profile={profile} onLogout={logout} onUpdateProfile={updateProfile} onSwitchProfile={login} />
  );
}
