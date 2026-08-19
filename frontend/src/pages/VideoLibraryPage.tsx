import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { YouTubePlayer } from "../components/YouTubePlayer";
import type { Video } from "../types";

const ALL_LEVELS = "All";

function VideoCard({ video, onOpen }: { video: Video; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex flex-col items-start gap-2 rounded-2xl bg-surface p-4 text-left transition-colors hover:bg-surfacemuted"
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="rounded-full bg-surfacemuted px-2.5 py-1 text-xs text-parchment/70">{video.level}</span>
        {video.watched && (
          <span className="rounded-full bg-known/15 px-2.5 py-1 text-xs font-semibold text-known">✓ Watched</span>
        )}
      </div>
      <p className="font-semibold leading-snug">{video.title}</p>
      <p className="text-xs text-parchment/50">{video.topic}</p>
    </button>
  );
}

function VideoModal({ video, onClose, onEnded }: { video: Video; onClose: () => void; onEnded: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="w-full max-w-2xl rounded-3xl bg-surface p-4 shadow-2xl shadow-black/50 sm:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <p className="font-semibold leading-snug">{video.title}</p>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surfacemuted text-sm font-bold text-parchment/70 hover:text-parchment"
          >
            ✕
          </button>
        </div>
        <YouTubePlayer videoId={video.youtube_video_id} onEnded={onEnded} />
      </div>
    </div>
  );
}

export function VideoLibraryPage() {
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<string>(ALL_LEVELS);
  const [openVideo, setOpenVideo] = useState<Video | null>(null);

  useEffect(() => {
    api
      .getVideos()
      .then(setVideos)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load videos."));
  }, []);

  // Distinct levels in the order they first appear (i.e. ordering order,
  // since videos is already sorted that way by the API) — the "group/
  // filter by the level tags" requirement, without inventing a stage
  // grouping the source list doesn't itself define.
  const levels = useMemo(() => {
    if (!videos) return [];
    const seen = new Set<string>();
    const result: string[] = [];
    for (const v of videos) {
      if (!seen.has(v.level)) {
        seen.add(v.level);
        result.push(v.level);
      }
    }
    return result;
  }, [videos]);

  const visibleVideos = useMemo(() => {
    if (!videos) return [];
    return levelFilter === ALL_LEVELS ? videos : videos.filter((v) => v.level === levelFilter);
  }, [videos, levelFilter]);

  const handleEnded = async () => {
    if (!openVideo) return;
    const watchedVideo = openVideo;
    try {
      const updated = await api.markVideoWatched(watchedVideo.id);
      setVideos((prev) => (prev ? prev.map((v) => (v.id === updated.id ? updated : v)) : prev));
    } catch {
      // Non-fatal — the video still played; the watched flag just won't
      // update until the page is reloaded. No error surfaced mid-video.
    }
  };

  return (
    <div className="flex w-full flex-col items-center gap-4 px-4 py-6 sm:py-10">
      <div className="flex w-full max-w-2xl flex-col gap-4">
        <h1 className="text-center text-2xl font-bold">Video library</h1>
        <p className="text-center text-sm text-parchment/50">
          A standalone collection of Hebrew-learning videos — watch at your own pace, in any order.
        </p>

        {error && <p className="text-center text-danger">{error}</p>}

        {videos && (
          <>
            <div className="flex flex-wrap justify-center gap-2">
              {[ALL_LEVELS, ...levels].map((level) => (
                <button
                  key={level}
                  type="button"
                  onClick={() => setLevelFilter(level)}
                  className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                    levelFilter === level
                      ? "bg-ember text-ink"
                      : "bg-surface text-parchment/60 hover:text-parchment"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {visibleVideos.map((video) => (
                <VideoCard key={video.id} video={video} onOpen={() => setOpenVideo(video)} />
              ))}
            </div>

            {visibleVideos.length === 0 && (
              <p className="text-center text-sm text-parchment/50">No videos at this level.</p>
            )}
          </>
        )}
      </div>

      {openVideo && (
        <VideoModal video={openVideo} onClose={() => setOpenVideo(null)} onEnded={handleEnded} />
      )}
    </div>
  );
}
