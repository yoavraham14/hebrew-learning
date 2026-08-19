// Loads YouTube's IFrame Player API script once, however many times
// YouTubePlayer mounts across the app's lifetime — no npm dependency, no
// API key (see youtube-iframe.d.ts for the minimal ambient types this
// relies on).

const SCRIPT_SRC = "https://www.youtube.com/iframe_api";

let apiReadyPromise: Promise<void> | null = null;

export function loadYouTubeIframeApi(): Promise<void> {
  if (apiReadyPromise) return apiReadyPromise;

  apiReadyPromise = new Promise((resolve) => {
    if (window.YT?.Player) {
      resolve();
      return;
    }

    const previousCallback = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previousCallback?.();
      resolve();
    };

    if (!document.querySelector(`script[src="${SCRIPT_SRC}"]`)) {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      document.head.appendChild(script);
    }
  });

  return apiReadyPromise;
}
