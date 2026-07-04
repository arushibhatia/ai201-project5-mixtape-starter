"""
services/debug_service.py — Mixtape

Test/dev-only helpers for setting up listening-streak scenarios without
hand-writing scripts or waiting for real calendar days to line up.

This service doesn't reimplement streak logic — it creates the
supporting User/ListeningEvent rows itself, then delegates the actual
streak math to the existing streak_service.update_listening_streak,
which already accepts an arbitrary `now`.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app import db
from models import User, Song, ListeningEvent
from services.streak_service import update_listening_streak


def create_debug_user(username: str = None) -> User:
    """
    Create a new user for testing, with an auto-generated username/email
    if none is given.

    Args:
        username: Optional username. If omitted, a unique debug username
            is generated.

    Returns:
        The created User instance.
    """
    if not username:
        username = f"debug_user_{uuid.uuid4().hex[:8]}"

    user = User(username=username, email=f"{username}@debug.local")
    db.session.add(user)
    db.session.commit()
    return user


def get_any_song() -> Song:
    """
    Get an arbitrary existing song, so callers don't need to know a song
    id ahead of time.

    Returns:
        A Song instance.

    Raises:
        ValueError: If there are no songs in the database yet.
    """
    song = db.session.query(Song).first()
    if not song:
        raise ValueError("No songs exist yet — seed the database first")
    return song


def _resolve_now(date: str = None, days_ago: int = None) -> datetime:
    """
    Turn a user-friendly date input into a datetime, without requiring
    callers to pass correctly formatted ISO timestamps.

    Args:
        date: An optional "YYYY-MM-DD" string.
        days_ago: An optional integer number of days before today.
            Ignored if `date` is given.

    Returns:
        A timezone-aware datetime. Defaults to the real current time if
        neither argument is given.
    """
    if date:
        parsed = datetime.strptime(date, "%Y-%m-%d")
        return parsed.replace(hour=12, tzinfo=timezone.utc)
    if days_ago is not None:
        return datetime.now(timezone.utc) - timedelta(days=days_ago)
    return datetime.now(timezone.utc)


def simulate_listen(
    user_id: str = None,
    song_id: str = None,
    date: str = None,
    days_ago: int = None,
) -> dict:
    """
    Simulate a user listening to a song on a given (possibly fake) date,
    and update their streak accordingly.

    Args:
        user_id: The user who listened. If omitted, a new debug user is
            created.
        song_id: The song listened to. If omitted, an arbitrary existing
            song is used.
        date: Optional "YYYY-MM-DD" string for when the listen happened.
        days_ago: Optional number of days before today. Ignored if `date`
            is given. If neither is given, the real current time is used.

    Returns:
        A dict with the resulting 'user', 'song', and 'event' state.
    """
    if user_id:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
    else:
        user = create_debug_user()

    if song_id:
        song = db.session.get(Song, song_id)
        if not song:
            raise ValueError(f"Song {song_id} not found")
    else:
        song = get_any_song()

    now = _resolve_now(date=date, days_ago=days_ago)

    event = ListeningEvent(user_id=user.id, song_id=song.id, listened_at=now)
    db.session.add(event)

    update_listening_streak(user, now)

    db.session.commit()

    return {
        "user": user.to_dict(),
        "song": song.to_dict(),
        "event": event.to_dict(),
    }
