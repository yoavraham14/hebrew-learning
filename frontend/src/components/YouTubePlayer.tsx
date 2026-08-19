import { useEffect, useRef } from "react";
import { loadYouTubeIframeApi } from "../lib/youtube";

// Mounts a YT.Player for one video. Fires onEnded exactly once per mount
// when playback reaches YT.PlayerState.ENDED — the auto-mark-watched
// signal (see VideoLibraryPage), no self-report prompt needed.
export function YouTubePlayer({ videoId, onEnded }: { videoId: string; onEnded: () => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YT.Player | null>(null);
  const onEndedRef = useRef(onEnded);
  onEndedRef.current = onEnded;

  useEffect(() => {
    let cancelled = false;

    loadYouTubeIframeApi().then(() => {
      if (cancelled || !containerRef.current || !window.YT) return;
      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId,
        width: "100%",
        height: "100%",
        events: {
          onStateChange: (event) => {
            if (event.data === window.YT?.PlayerState.ENDED) {
              onEndedRef.current();
            }
          },
        },
      });
    });

    return () => {
      cancelled = true;
      playerRef.current?.destroy();
      playerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  return <div className="aspect-video w-full overflow-hidden rounded-2xl bg-black" ref={containerRef} />;
}
