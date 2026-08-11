import pytest

from app.models import WordPair
from app.services import audio as audio_service
from app.services.audio import _strip_niqqud


def _word(db_session, **overrides) -> WordPair:
    data = dict(
        hebrew_word="חלון", phonetic_en="chalon", phonetic_es="jalón",
        spanish_word="ventana", english_word="window", part_of_speech="noun",
        cefr_level="A1", topic="home", example_sentence_he="x", example_sentence_es="x",
        verified=True,
    )
    data.update(overrides)
    w = WordPair(**data)
    db_session.add(w)
    db_session.commit()
    return w


def _synthesize_or_skip(text: str) -> bytes:
    """gTTS needs a live network call to an unofficial, third-party
    endpoint — skip rather than fail if this sandbox/CI run has no network
    access or Google is (temporarily or permanently) blocking it, same
    spirit as the old eSpeak-binary-presence skip this replaced.
    """
    try:
        return audio_service.synthesize_hebrew(text)
    except audio_service.AudioGenerationUnavailable as exc:
        pytest.skip(f"gTTS unavailable in this environment: {exc}")


# ---------------------------------------------------------------------------
# app.services.audio — pure unit tests
# ---------------------------------------------------------------------------


def test_synthesize_hebrew_raises_when_gtts_fails(monkeypatch):
    def _raise(*args, **kwargs):
        raise audio_service.gTTSError("simulated failure")

    monkeypatch.setattr(audio_service, "gTTS", _raise)
    with pytest.raises(audio_service.AudioGenerationUnavailable):
        audio_service.synthesize_hebrew("חלון")


def test_synthesize_hebrew_produces_nonempty_mp3_bytes():
    result = _synthesize_or_skip("חלון")
    assert isinstance(result, bytes)
    assert len(result) > 0
    assert result[:2] == b"\xff\xf3" or result[:3] == b"ID3"  # MP3 frame sync or ID3 tag


def test_synthesize_hebrew_output_actually_varies_with_input_text():
    short = _synthesize_or_skip("חלון")
    long = _synthesize_or_skip("שלום עולם זה משפט ארוך יותר מהמילה הקודמת")
    assert short != long
    assert len(long) > len(short) * 2  # a much longer sentence must produce meaningfully more audio


def test_strip_niqqud_removes_vowel_points_keeps_letters():
    assert _strip_niqqud("חָלוֹן") == "חלון"
    assert _strip_niqqud("לְהִתְאַרְגֵּן") == "להתארגן"
    assert _strip_niqqud("שלום") == "שלום"  # no niqqud present — no-op


def test_synthesize_hebrew_with_niqqud_stays_a_reasonably_short_clip():
    """Regression guard for the failure mode caught with the previous
    (eSpeak NG) engine: niqqud being misread as extra content and ballooning
    a single short word into a multi-second ramble. gTTS itself already
    handles niqqud gracefully, but this keeps the guarantee explicit in
    case that ever changes.
    """
    result = _synthesize_or_skip("לְהִתְאַרְגֵּן")
    assert len(result) < 50_000  # a single short word, not a ramble


# ---------------------------------------------------------------------------
# GET /api/audio/word-pairs/{id} — router behavior, synthesis mocked so
# these never depend on network access.
# ---------------------------------------------------------------------------


def test_audio_endpoint_generates_and_caches_on_first_request(client, db_session, monkeypatch):
    word = _word(db_session)
    calls = []

    def fake_synth(text: str) -> bytes:
        calls.append(text)
        return b"FAKEMP3DATA"

    monkeypatch.setattr("app.routers.audio.synthesize_hebrew", fake_synth)

    resp = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp.status_code == 200
    assert resp.content == b"FAKEMP3DATA"
    assert resp.headers["content-type"] == "audio/mpeg"
    assert "immutable" in resp.headers["cache-control"]
    assert calls == ["חלון"]

    # Second request must be served from the cached column, not re-synthesized.
    resp2 = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp2.status_code == 200
    assert resp2.content == b"FAKEMP3DATA"
    assert calls == ["חלון"]  # still only called once


def test_audio_endpoint_requires_no_auth(client, db_session, monkeypatch):
    word = _word(db_session)
    monkeypatch.setattr("app.routers.audio.synthesize_hebrew", lambda text: b"X")
    resp = client.get(f"/api/audio/word-pairs/{word.id}")  # no Authorization header
    assert resp.status_code == 200


def test_audio_endpoint_404s_for_unknown_word(client, db_session):
    resp = client.get("/api/audio/word-pairs/999999")
    assert resp.status_code == 404


def test_audio_endpoint_404s_when_generation_unavailable(client, db_session, monkeypatch):
    word = _word(db_session)

    def raise_unavailable(text: str) -> bytes:
        raise audio_service.AudioGenerationUnavailable("gTTS unreachable")

    monkeypatch.setattr("app.routers.audio.synthesize_hebrew", raise_unavailable)

    resp = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp.status_code == 404
