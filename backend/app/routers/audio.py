from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.deps import DbSession
from app.logging_config import get_logger
from app.models import WordPair
from app.services.audio import AudioGenerationUnavailable, synthesize_hebrew

logger = get_logger(__name__)

router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.get("/word-pairs/{word_pair_id}")
def get_hebrew_audio(word_pair_id: int, db: DbSession) -> Response:
    """Deliberately unauthenticated — this is just vocabulary pronunciation
    audio, not user data, and plain <audio src="..."> tags can't attach an
    Authorization header. Generated lazily on first request and cached from
    then on; a Cache-Control of `immutable` is safe because the underlying
    word text never changes after insert (verification corrections happen
    before insert, never after — see app.services.word_generator).
    """
    word = db.get(WordPair, word_pair_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="word not found")

    if word.hebrew_audio is None:
        try:
            word.hebrew_audio = synthesize_hebrew(word.hebrew_word)
            db.commit()
        except AudioGenerationUnavailable as exc:
            logger.warning(
                "hebrew audio generation unavailable — frontend will fall back to browser TTS",
                extra={"extra_fields": {"word_pair_id": word_pair_id, "error": str(exc)}},
            )
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="audio unavailable") from exc

    return Response(
        content=word.hebrew_audio,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
