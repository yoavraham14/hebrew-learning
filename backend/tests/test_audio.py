import pytest

from app.models import WordPair
from app.services import audio as audio_service


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


# ---------------------------------------------------------------------------
# app.services.audio — pure unit tests, no subprocess required
# ---------------------------------------------------------------------------


def test_synthesize_hebrew_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr(audio_service, "ESPEAK_BINARY", None)
    with pytest.raises(audio_service.AudioGenerationUnavailable):
        audio_service.synthesize_hebrew("חלון")


@pytest.mark.skipif(audio_service.ESPEAK_BINARY is None, reason="espeak-ng not installed on this machine")
def test_synthesize_hebrew_produces_nonempty_wav_bytes():
    result = audio_service.synthesize_hebrew("חלון")
    assert isinstance(result, bytes)
    assert len(result) > 0
    assert result[:4] == b"RIFF"  # WAV container magic bytes


# ---------------------------------------------------------------------------
# GET /api/audio/word-pairs/{id} — router behavior, synthesis mocked so
# these run identically whether or not espeak-ng is actually installed.
# ---------------------------------------------------------------------------


def test_audio_endpoint_generates_and_caches_on_first_request(client, db_session, monkeypatch):
    word = _word(db_session)
    calls = []

    def fake_synth(text: str) -> bytes:
        calls.append(text)
        return b"FAKEWAVDATA"

    monkeypatch.setattr("app.routers.audio.synthesize_hebrew", fake_synth)

    resp = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp.status_code == 200
    assert resp.content == b"FAKEWAVDATA"
    assert resp.headers["content-type"] == "audio/wav"
    assert "immutable" in resp.headers["cache-control"]
    assert calls == ["חלון"]

    # Second request must be served from the cached column, not re-synthesized.
    resp2 = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp2.status_code == 200
    assert resp2.content == b"FAKEWAVDATA"
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
        raise audio_service.AudioGenerationUnavailable("espeak-ng not installed")

    monkeypatch.setattr("app.routers.audio.synthesize_hebrew", raise_unavailable)

    resp = client.get(f"/api/audio/word-pairs/{word.id}")
    assert resp.status_code == 404
