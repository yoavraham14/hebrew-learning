"""Server-side Hebrew pronunciation audio via eSpeak NG — offline, no API
key, no billing account, same zero-cost-risk posture as the rest of this
app's external-service policy (SPEC.md §2.1's ethos generalized beyond just
Gemini). Generated lazily on first request per word and cached in Postgres
(WordPair.hebrew_audio) — see app.routers.audio.

Deliberately shells out to the `espeak-ng` binary rather than a Python
wrapper package: one less pip dependency, and the binary is the thing that
actually needs installing on whatever machine runs the backend (see
README's Prerequisites — `winget install eSpeak-NG.eSpeak-NG` /
`brew install espeak-ng` / `apt-get install espeak-ng`).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from app.logging_config import get_logger

logger = get_logger(__name__)

# Resolved once at import time. Tests monkeypatch this name directly to
# simulate "not installed" without needing the real binary present.
ESPEAK_BINARY: str | None = shutil.which("espeak-ng") or shutil.which("espeak")


class AudioGenerationUnavailable(Exception):
    """eSpeak NG isn't installed on this machine, or the synthesis call
    itself failed. The caller (app.routers.audio) fails soft on this —
    no audio, HTTP 404 — exactly like a missing browser TTS voice failed
    silently before this feature existed. Never a 500: a missing/broken
    local TTS binary is not a server error worth alarming over.
    """


def synthesize_hebrew(text: str) -> bytes:
    """Returns WAV bytes for `text` spoken in Hebrew. Raises
    AudioGenerationUnavailable if eSpeak NG isn't installed or the call
    fails for any reason (bad input, timeout, non-zero exit).
    """
    if not ESPEAK_BINARY:
        raise AudioGenerationUnavailable("espeak-ng is not installed on this machine")

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.wav"
        try:
            subprocess.run(
                [ESPEAK_BINARY, "-v", "he", "-s", "150", "-w", str(out_path), text],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise AudioGenerationUnavailable(f"espeak-ng synthesis failed: {exc}") from exc

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise AudioGenerationUnavailable("espeak-ng produced no audio output")

        return out_path.read_bytes()
