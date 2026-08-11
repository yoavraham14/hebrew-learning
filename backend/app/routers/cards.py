from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentProfile, DbSession
from app.schemas import AnswerRequest, AnswerResponse, CardResponse, RateRequest, RateResponse
from app.services.cards import answer_word, get_next_card, rate_word

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("/next", response_model=CardResponse)
def next_card(profile: CurrentProfile, db: DbSession) -> CardResponse:
    card = get_next_card(db, profile)
    if card is None:
        # Bank is completely empty — bootstrap/top-up hasn't produced
        # anything yet (e.g. first ever startup, still generating).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No words available yet — the word bank is still being generated. Try again shortly.",
        )
    return card


@router.post("/{word_pair_id}/rate", response_model=RateResponse)
def rate_card(word_pair_id: int, payload: RateRequest, profile: CurrentProfile, db: DbSession) -> RateResponse:
    return rate_word(db, profile, word_pair_id, payload.result)


@router.post("/{word_pair_id}/answer", response_model=AnswerResponse)
def answer_card(
    word_pair_id: int, payload: AnswerRequest, profile: CurrentProfile, db: DbSession
) -> AnswerResponse:
    return answer_word(db, profile, word_pair_id, payload.selected_word_pair_id)
