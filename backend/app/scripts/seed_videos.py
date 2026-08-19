"""One-time (or re-run-to-update) import of the video library catalog.

Run with:  python -m app.scripts.seed_videos

Source: hebrew-videos.md, verified against YouTube's oEmbed endpoint before
import (see the video-library plan) — 38 of the original 40 candidates
survived: #19 (8kyHoiArSNs) pointed at a completely different video than
claimed, #31 (QvgZ517eXEo) returned 401 (embedding disabled) from oEmbed.
`ordering` keeps the source list's original # column, so there are
intentional gaps at 19 and 31 — harmless, it's a sort key, not a dense
sequence.

Safe to re-run: upserts by youtube_video_id (creates if missing, updates
title/level/topic/ordering if already present), same idempotent shape as
scripts/seed_profiles.py.
"""

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.logging_config import configure_logging, get_logger
from app.models import Video

logger = get_logger(__name__)

# (ordering, title, youtube_video_id, level, topic)
VIDEOS: list[tuple[int, str, str, str, str]] = [
    (1, "Hebrew Alphabet Song", "u_EvzURStlc", "A0", "alphabet"),
    (2, "Hebrew Alphabet - Learn to Read and Write Hebrew", "uiGXh2BFKUo", "A0", "alphabet, reading, writing"),
    (3, "Learn how to write Hebrew Alphabet (PRINT version)", "-JVp2CBnFUE", "A0", "writing"),
    (4, "Hebrew Alphabet Made Easy: Alef and Beit", "JBVpQzvrJ4w", "A0", "writing"),
    (5, "Hebrew Alphabet Made Easy: Gimel, Dalet and Kamats", "tN6Mf7fxxS4", "A0", "writing, niqqud"),
    (6, "Hebrew Pronunciation - Hebrew Vowels", "GrRuqF21myQ", "A0", "vowels, pronunciation"),
    (7, "Hebrew in Three Minutes - Diphthongs / Pronunciation", "mcMFk-9yGLg", "A0", "pronunciation"),
    (8, "How to Pronounce Hebrew Like a Native Speaker", "hyhiDDq0HDE", "A0/A1", "pronunciation"),
    (9, "10 Hardest Hebrew Words to Pronounce", "cD2-KykFSX8", "A1", "pronunciation"),
    (10, "How to Introduce Yourself in Hebrew", "V5cdDZRxLeI", "A1", "introductions"),
    (11, "How to Greet People in Hebrew", "aAEc3q7af4k", "A1", "greetings"),
    (12, "10 Ways to Say Hello in Hebrew", "D-O2k5KZcjU", "A1", "greetings"),
    (13, "Top 15 Questions You Should Know in Hebrew", "W-xL_yFGzpQ", "A1", "questions"),
    (14, "Top 25 Must-Know Hebrew Phrases", "PgDtKfjXYc0", "A1", "phrases"),
    (15, "Top 25 Must-Know Hebrew Nouns", "fk22A3X9Jtw", "A1", "nouns"),
    (16, "Top 25 Must-Know Hebrew Verbs", "Y4YqPP3NaKI", "A1", "verbs"),
    (17, "Top 25 Must-Know Hebrew Adjectives", "LwncuVy2dlg", "A1", "adjectives"),
    (18, 'Top 10 Responses to "How are you?" in Hebrew', "UKqCnJpz1kI", "A1", "conversation"),
    # #19 dropped — verification showed it points at an unrelated video.
    (20, "Top 15 Favorite Hebrew Words", "hVf6gNCULps", "A1", "vocabulary"),
    (21, "Top 20 Travel Phrases You Should Know in Hebrew", "lCdPQ4x7Mgs", "A1/A2", "travel"),
    (22, "Top 15 Must-Know Hebrew Family Words", "8vwlknc8FZA", "A1", "family"),
    (23, "10 Must-Know Particles for Hebrew Learners", "nIOig5jqLjA", "A2", "grammar"),
    (24, "Top 15 Phrases to Go Shopping in Israel", "KT1pTPoGLmw", "A1/A2", "shopping"),
    (25, "Weekly Hebrew Words - Rooms", "p7cs0FpDZOU", "A1/A2", "home"),
    (26, "Weekly Hebrew Words - Clothing Actions", "VDI0b7qXVs8", "A1/A2", "clothing, verbs"),
    (27, "Weekly Hebrew Words - Clothing and Accessories", "MLgsS_zUgiU", "A1/A2", "clothing"),
    (28, "200 Hebrew Words for Everyday Life", "vtNCLAjn-Hk", "A2", "vocabulary"),
    (29, "100 Hebrew Words You'll Use Every Day", "glrW0YQIpBQ", "A2", "vocabulary"),
    (30, "100 Phrases Every Hebrew Beginner Must-Know", "dKPKtvrXEfM", "A2", "phrases"),
    # #31 dropped — verification returned 401 (embedding disabled).
    (32, "10 Ways to Practice Your Hebrew Reading", "9eiRmenhP-o", "A2", "reading"),
    (33, "8 Ways to Practice Hebrew Writing", "UlsgcSWU_6g", "A2", "writing"),
    (34, "Hebrew Listening Practice - Getting Directions", "kZstcBngNfk", "A2", "listening"),
    (35, "Hebrew Listening Practice - Talking About Your Age", "voD_Mnmv_dQ", "A2", "listening"),
    (36, "Learn HEBREW - Easy Listening Practice for Beginners", "XKfM1PccZ3A", "A2/B1", "listening"),
    (37, "Learn HEBREW With Our FULL VAN TOUR", "u4uNNSIR-2U", "A2/B1", "listening, natural speech"),
    (38, "Learn Hebrew in 4 Hours - ALL the Hebrew Basics", "iu7R3-84ZnU", "A2", "review (4+ hours)"),
    (39, "50 Hebrew Phrases to Use in a Conversation", "mvgCHWF0QWA", "A2/B1", "conversation"),
    (40, "20 Minutes of Hebrew Conversation Practice", "EGYTgTfI-OY", "A2/B1", "conversation"),
]


def main() -> int:
    configure_logging()
    db = SessionLocal()
    created = 0
    updated = 0
    try:
        for ordering, title, youtube_video_id, level, topic in VIDEOS:
            existing = db.scalar(select(Video).where(Video.youtube_video_id == youtube_video_id))
            if existing is None:
                db.add(
                    Video(
                        title=title,
                        youtube_video_id=youtube_video_id,
                        level=level,
                        topic=topic,
                        ordering=ordering,
                    )
                )
                created += 1
            else:
                existing.title = title
                existing.level = level
                existing.topic = topic
                existing.ordering = ordering
                updated += 1

        db.commit()
        logger.info(
            "seeded video library", extra={"extra_fields": {"created": created, "updated": updated}}
        )
        print(f"Videos: {created} created, {updated} updated.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
