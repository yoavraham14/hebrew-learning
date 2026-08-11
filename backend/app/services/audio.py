"""Server-side Hebrew pronunciation audio via gTTS — a thin wrapper around
Google Translate's own "listen" feature (the same endpoint the speaker icon
on translate.google.com calls). Chosen over eSpeak NG (this app's original,
fully-offline choice) for voice quality: natural-sounding versus eSpeak's
robotic synthesis, at the cost of being an unofficial, undocumented,
reverse-engineered endpoint with no SLA — Google could change or block it
without warning. No API key, no billing account either way, so it doesn't
touch this app's cost-safety policy (SPEC.md §2.1) — the risk here is
availability, not cost.

Generated lazily on first request per word and cached in Postgres
(WordPair.hebrew_audio) — see app.routers.audio — so the network dependency
is a one-time cost per word, not a per-playback one. If gTTS ever fails
(network issue, endpoint blocked/changed), the caller fails soft (404) and
the frontend falls back to the browser's own speechSynthesis, exactly like
before this feature existed — never a dead end.
"""

import io
import re

import requests
from gtts import gTTS
from gtts.tts import gTTSError

from app.logging_config import get_logger

logger = get_logger(__name__)

# Hebrew niqqud (vowel points, U+0591-U+05C7) and cantillation marks.
# gTTS handles niqqud gracefully on its own (confirmed live: identical
# output with or without it) — stripping it here is just defensive
# normalization, not a workaround for a real bug the way it was for the
# eSpeak NG implementation this replaced.
_NIQQUD_RANGE = re.compile(r"[֑-ׇ]")


def _strip_niqqud(text: str) -> str:
    return _NIQQUD_RANGE.sub("", text)


class AudioGenerationUnavailable(Exception):
    """gTTS failed for any reason — network error, the endpoint rejecting
    the request, an empty/unusable response. The caller (app.routers.audio)
    fails soft on this — no audio, HTTP 404 — never a 500: an unofficial
    third-party endpoint being unreachable is not a server error worth
    alarming over.
    """


def synthesize_hebrew(text: str) -> bytes:
    """Returns MP3 bytes for `text` spoken in Hebrew via gTTS. Raises
    AudioGenerationUnavailable on any failure.
    """
    speakable = _strip_niqqud(text) or text  # never synthesize an empty string
    try:
        tts = gTTS(text=speakable, lang="iw")  # "iw" is gTTS/Google's legacy code for Hebrew
        buf = io.BytesIO()
        tts.write_to_fp(buf)
    except (gTTSError, requests.RequestException, ValueError) as exc:
        raise AudioGenerationUnavailable(f"gTTS synthesis failed: {exc}") from exc

    audio_bytes = buf.getvalue()
    if not audio_bytes:
        raise AudioGenerationUnavailable("gTTS produced no audio output")

    return audio_bytes
